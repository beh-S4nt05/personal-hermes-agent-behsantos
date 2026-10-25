"""Canal Telegram — v4.2.0 (PR #5).

Long-polling local (getUpdates) com a Bot API; token em
``secrets/telegram.key`` (600, via helpers de secrets); allowlist de
chat_ids em ``<data_dir>/telegram-chats.txt`` (um por linha).
Zero dependência nova (requests já é do projeto).
"""
from __future__ import annotations

import threading

from .llm_providers import api_key, salvar_key
from .contratos import acao_de

_API = "https://api.telegram.bot"


def token(cfg) -> str:
    return api_key(cfg, "telegram")


def salvar_token(cfg, tok: str):
    return salvar_key(cfg, "telegram", tok.strip())


def chats_autorizados(cfg) -> set[str]:
    from pathlib import Path
    p = Path(cfg.data_dir) / "telegram-chats.txt"
    try:
        return {l.strip() for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip()}
    except OSError:
        return set()


def autorizar_chat(cfg, chat_id: str) -> None:
    from pathlib import Path
    p = Path(cfg.data_dir) / "telegram-chats.txt"
    atuais = chats_autorizados(cfg)
    atuais.add(str(chat_id))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(sorted(atuais)) + "\n", encoding="utf-8")


class CanalTelegram:
    """Loop de polling; injetável em testes via _http/_sleep."""

    def __init__(self, cfg, _http=None, _sleep=None):
        self.cfg = cfg
        self._http = _http or self._http_padrao
        self._sleep = _sleep or (lambda s: None)
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._gw = None
        self._offset = 0

    def disponivel(self) -> bool:
        return bool(token(self.cfg))

    @staticmethod
    def _http_padrao(url: str, payload=None):
        import requests
        if payload is None:
            r = requests.get(url, timeout=25)
        else:
            r = requests.post(url, json=payload, timeout=25)
        return r.json() if r.status_code == 200 else {}

    def autorizado(self, remetente: str) -> bool:
        return str(remetente) in chats_autorizados(self.cfg)

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        """Push para TODOS os chats autorizados (ou um específico)."""
        tok = token(self.cfg)
        alvos = [chat_id] if chat_id else sorted(chats_autorizados(self.cfg))
        for cid in alvos:
            try:
                self._http(f"{_API}/{tok}/sendMessage",
                           {"chat_id": cid, "text": texto})
            except Exception:  # noqa: BLE001
                pass

    def _processar_updates(self, updates: list[dict]) -> None:
        for u in updates or []:
            self._offset = max(self._offset,
                               int(u.get("update_id", 0)) + 1)
            msg = u.get("message") or u.get("edited_message") or {}
            chat = msg.get("chat") or {}
            cid = str(chat.get("id", ""))
            texto = str(msg.get("text", ""))
            if not texto:
                continue
            if self._gw is None:
                continue
            resp = self._gw.receber(self, cid, texto)
            if resp:
                self.enviar(resp, chat_id=cid)

    def _loop(self) -> None:
        tok = token(self.cfg)
        while not self._parar.is_set():
            try:
                dados = self._http(
                    f"{_API}/{tok}/getUpdates"
                    f"?timeout=10&offset={self._offset}") or {}
                self._processar_updates(dados.get("result") or [])
            except Exception:  # noqa: BLE001
                self._sleep(3)

    def iniciar(self, gw) -> None:
        self._gw = gw
        if self._thread is None and not self._parar.is_set():
            self._thread = threading.Thread(target=self._loop,
                                            daemon=True)
            self._thread.start()

    def parar(self) -> None:
        self._parar.set()


def cmd(args, cfg) -> None:
    """`betterme telegram status|start|stop|chat-id|autorizar`."""
    acao = acao_de(args)
    if acao == "status":
        tem = bool(token(cfg))
        ligado = str(getattr(cfg, "telegram_on", False)).lower() in \
            ("true", "1", "yes")
        print(f"\n📱 Telegram: {'token OK' if tem else 'sem token'} · "
              f"gateway {'LIGADO' if ligado else 'desligado'}")
        chats = chats_autorizados(cfg)
        print(f"   chats autorizados: {', '.join(sorted(chats)) or '(nenhum)'}")
        if not tem:
            print("\n   1) crie o bot com @BotFather e copie o token\n"
                  "   2) betterme telegram start  (cola o token)\n"
                  "   3) mande /start pro bot e rode "
                  "betterme telegram chat-id")
        return
    if acao == "start":
        if not token(cfg):
            import getpass
            tok = getpass.getpass("token do bot (@BotFather): ").strip()
            if not tok:
                print("✖ token vazio — nada feito")
                raise SystemExit(1)
            salvar_token(cfg, tok)
        cfg.update({"telegram_on": True})
        print("✔ Telegram ligado — reinicie o server "
              "(betterme server) para ativar o gateway")
        return
    if acao == "stop":
        cfg.update({"telegram_on": False})
        print("✔ Telegram desligado (token e allowlist preservados)")
        return
    if acao == "chat-id":
        print("⏳ aguardando você mandar qualquer mensagem pro bot "
              "(30 s)…")
        canal = CanalTelegram(cfg)
        import time as _t
        deadline = _t.time() + 30
        while _t.time() < deadline and not canal._parar.is_set():
            dados = canal._http(
                f"{_API}/{token(cfg)}/getUpdates?timeout=5") or {}
            for u in dados.get("result") or []:
                msg = u.get("message") or {}
                cid = str((msg.get("chat") or {}).get("id", ""))
                if cid:
                    autorizar_chat(cfg, cid)
                    print(f"✔ chat autorizado: {cid}")
                    return
        print("✖ nenhuma mensagem recebida em 30 s")
        raise SystemExit(1)
    if acao == "autorizar":
        cid = str(getattr(args, "id", "") or "").strip()
        if not cid:
            print("uso: betterme telegram autorizar <chat_id>")
            raise SystemExit(1)
        autorizar_chat(cfg, cid)
        print(f"✔ chat autorizado: {cid}")
        return
    print(f"✖ ação inválida: {acao!r}")
    raise SystemExit(1)
