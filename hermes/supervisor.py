"""Supervisor MCP: mantém os servidores MCP vivos (auto-restart com backoff).

Roda como thread dentro do `hermes server`: a cada 60s verifica os servidores
que ESTAVAM ativos; se um processo morreu, reinicia com backoff exponencial
(60s, 120s, 240s… teto 10 min) e registra notificação para o operador.
"""
from __future__ import annotations

import threading
import time

CHECK_INTERVAL_S = 60
BACKOFF_CAP_S = 600


class McpSupervisor:
    def __init__(self, cfg):
        self.cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fails: dict[str, int] = {}
        self._next_try: dict[str, float] = {}

    # ------------------------------------------------------------- ciclo
    def start(self) -> None:
        if not getattr(self.cfg, "mcp_autorestart", True):
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="hermes-mcp-supervisor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_INTERVAL_S):
            try:
                self.check_once()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------- verificação
    def check_once(self) -> list[dict]:
        """Reinicia servidores mortos; devolve [{name, restarted, error}]."""
        from .mcp_client import get_manager
        from . import notify

        events = []
        try:
            mgr = get_manager(self.cfg)
            for st in mgr.status():
                name = st["name"]
                if st["state"] != "ativo":
                    continue  # nunca ligado/erro de config: o operador decide
                if time.time() < self._next_try.get(name, 0):
                    continue  # backoff
                # estava ativo mas o processo morreu?
                alive = False
                try:
                    alive = mgr._servers.get(name) is not None and \
                        mgr._servers[name].alive()
                except Exception:  # noqa: BLE001
                    alive = False
                if alive:
                    self._fails[name] = 0
                    continue
                # morto -> tenta renascer
                try:
                    mgr.restart_server(name)
                    self._fails[name] = 0
                    self._next_try.pop(name, None)
                    events.append({"name": name, "restarted": True, "error": None})
                    notify.push(self.cfg, "mcp",
                                f"Servidor MCP '{name}' reiniciado",
                                "O processo tinha morrido; o supervisor o trouxe de volta.")
                    try:
                        from . import activity
                        activity.log(self.cfg, "mcp",
                                     f"🩺 '{name}' reiniciado pelo supervisor "
                                     f"(o processo tinha morrido)")
                    except Exception:  # noqa: BLE001
                        pass
                except Exception as exc:  # noqa: BLE001
                    n = self._fails.get(name, 0) + 1
                    self._fails[name] = n
                    delay = min(60 * (2 ** (n - 1)), BACKOFF_CAP_S)
                    self._next_try[name] = time.time() + delay
                    events.append({"name": name, "restarted": False,
                                   "error": str(exc)[:200]})
        except Exception:  # noqa: BLE001
            pass
        return events
