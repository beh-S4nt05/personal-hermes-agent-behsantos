"""Log de atividades: TUDO que acontece no `hermes server` aparece no log
ao vivo do painel.

Histórico do problema (v3.1.1): o "📡 Log ao vivo" faz tail de
data/logs/agent.log, mas só o DAEMON escrevia nele — chat, ferramentas,
agendador, MCP, Ollama e ajustes ficavam invisíveis. Este módulo é a
caneta única: linha `[ts] [fonte] mensagem`, thread-safe, rotação em 5 MB
(mantém agent.log.1). Nunca lança exceção — log não pode derrubar nada.
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def log(cfg, source: str, message: str, max_bytes: int | None = None) -> None:
    """Anexa uma linha de atividade ao agent.log (best-effort)."""
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{source}] {message}\n"
        limite = max_bytes if max_bytes is not None else MAX_BYTES
        with _LOCK:
            path = cfg.logfile
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if path.exists() and path.stat().st_size > limite:
                    rot = path.with_suffix(".log.1")
                    rot.unlink(missing_ok=True)
                    path.replace(rot)
            except OSError:
                pass
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:  # noqa: BLE001
        pass
