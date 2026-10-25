"""Gateway de mensagens — v4.2.0 (PR #5): núcleo compartilhado.

Canais (Telegram nativo; WhatsApp via Playwright) dão ao operador o
controle do Betterme pelo celular: ver status, listar tarefas, APROVAR
missões e conversar.

Regras duras do gateway:
- Canal de CONTROLE, não de dados: nas notificações vai id + objetivo
  TRUNCADO — nunca conteúdo de arquivos, memória ou segredos.
- Allowlist: só o dono comanda (chat_id / número cadastrado).
- Credenciais (token do bot) em secrets/ 600, fora de config/logs.
"""
from __future__ import annotations

import threading


# ------------------------------------------------------------ comandos
AJUDA = (
    "🤖 Betterme — comandos:\n"
    "/status — estado do agente\n"
    "/tarefas — aprovações pendentes\n"
    "/aprovar <id> — aprova uma tarefa\n"
    "/rejeitar <id> — cancela uma tarefa\n"
    "/autonomia [cauteloso|padrao|autonomo]\n"
    "/perguntar <texto> — conversa com o cérebro\n"
    "/ajuda — esta lista"
)


def processar_comando(cfg, texto: str, remetente: str, decidir, runner,
                      autorizado: bool) -> str | None:
    """Parser compartilhado dos canais. Devolve a resposta (ou None se
    não for comando). `decidir(tid, acao) -> bool` e
    `runner(pergunta) -> str` são injetáveis (testes/produção)."""
    t = (texto or "").strip()
    if not t.startswith("/"):
        return None
    partes = t.split(None, 1)
    cmd = partes[0].lower()
    args = partes[1].strip() if len(partes) > 1 else ""
    if not autorizado:
        return ("⛔ não autorizado — este agente atende apenas o dono "
                "(cadastre o contato na allowlist).")
    if cmd in ("/ajuda", "/help", "/start"):
        return AJUDA
    if cmd in ("/status", "/estado"):
        from .autonomy import nivel
        from .config import VERSION
        prov = str(getattr(cfg, "llm_provider", "local"))
        return (f"🤖 Betterme v{VERSION}\n🎚 autonomia: {nivel(cfg)}\n"
                f"🔌 provedor: {prov}\n"
                f"📁 dados: {cfg.data_dir}")
    if cmd in ("/tarefas", "/pendencias"):
        from .orchestrator import list_pending
        pend = list_pending(cfg)
        if not pend:
            return "☑ nenhuma aprovação pendente."
        linhas = [f"🔒 {p.get('id')} · {p.get('kind', '?')} · "
                  f"{str(p.get('objetivo', ''))[:110]}" for p in pend[:10]]
        return ("📋 pendências:\n" + "\n".join(linhas)
                + "\n(responda /aprovar <id> ou /rejeitar <id>)")
    if cmd in ("/aprovar", "/rejeitar", "/cancelar"):
        tid = args.split()[0] if args else ""
        if not tid:
            return "uso: /aprovar <id> (veja ids em /tarefas)"
        acao = ("cancelar" if cmd in ("/rejeitar", "/cancelar")
                else "aprovar")
        return ("✔ decidido: " + tid if decidir(tid, acao)
                else f"✖ {tid} não está aguardando decisão (expirou ou "
                     f"já foi resolvida) — veja /tarefas")
    if cmd in ("/autonomia", "/autonomy"):
        from .autonomy import NIVEIS, nivel, DESCRICOES
        alvo = args.lower()
        if alvo and alvo in NIVEIS:
            cfg.update({"autonomia": alvo})
            return f"🎚 autonomia agora: {alvo.upper()} — {DESCRICOES[alvo]}"
        if alvo:
            return f"✖ nível inválido — use: {', '.join(NIVEIS)}"
        return f"🎚 autonomia atual: {nivel(cfg).upper()}"
    if cmd in ("/perguntar", "/ask"):
        if not args:
            return "uso: /perguntar <sua pergunta>"
        try:
            return "🧠 " + runner(args)[:3000]
        except Exception as exc:  # noqa: BLE001
            return f"✖ falha ao processar: {exc.__class__.__name__}"
    return None


# ------------------------------------------------------------ decisão
def decidir_via_server(cfg, tid: str, acao: str, http_post=None) -> bool:
    """Decide uma pendência: 1) approve() local (mesmo processo do
    server); 2) HTTP para o server local (gateway standalone)."""
    try:
        from .orchestrator import approve
        if approve(tid, acao):
            return True
    except Exception:  # noqa: BLE001
        pass
    porta = int(getattr(cfg, "server_port", 8080) or 8080)
    if http_post is None:
        import requests

        def http_post(url, payload):
            r = requests.post(url, json=payload, timeout=10)
            return r.status_code
    try:
        code = http_post(f"http://127.0.0.1:{porta}/api/chat/approve",
                         {"id": tid, "action": acao})
        return code == 200
    except Exception:  # noqa: BLE001
        return False


def _runner_padrao(cfg):
    """Pergunta do operador → pipeline completo (thread própria)."""
    def runner(pergunta: str) -> str:
        from .agent import Agent
        from .ollama_client import get_client
        from .orchestrator import run_pipeline
        ag = Agent(cfg, client=get_client(cfg))
        return run_pipeline(ag, cfg, pergunta, [])
    return runner


# ------------------------------------------------------------ gateway
class Gateway:
    """Agrega canais; notifica NOVAS pendências (poll em disco)."""

    INTERVALO_S = 5.0

    def __init__(self, cfg, decidir=None, runner=None):
        self.cfg = cfg
        self.decidir = decidir or (lambda tid, acao:
                                   decidir_via_server(cfg, tid, acao))
        self.runner = runner or _runner_padrao(cfg)
        self.canais: list = []
        self._notificados: set[str] = set()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def adicionar(self, canal) -> None:
        self.canais.append(canal)

    # ---- notificações de pendências (canal de CONTROLE)
    def _msg_pendencia(self, p: dict) -> str:
        obj = str(p.get("objetivo", ""))[:120]
        return (f"🔒 *{p.get('id')}* · {p.get('kind', 'plano')}\n"
                f"🎯 {obj}\n"
                f"responda: /aprovar {p.get('id')} ou /rejeitar {p.get('id')}")

    def tick(self) -> int:
        """Varre pendências novas e notifica os canais. Retorna qtd."""
        from .orchestrator import list_pending
        novas = 0
        for p in list_pending(self.cfg):
            pid = str(p.get("id", ""))
            if pid and pid not in self._notificados:
                self._notificados.add(pid)
                msg = self._msg_pendencia(p)
                for canal in self.canais:
                    try:
                        canal.enviar(msg)
                    except Exception:  # noqa: BLE001
                        pass
                novas += 1
        return novas

    def _loop(self) -> None:
        while not self._parar.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                pass
            self._parar.wait(self.INTERVALO_S)

    def iniciar(self) -> None:
        for canal in self.canais:
            canal.iniciar(self)
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop,
                                            daemon=True)
            self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        for canal in self.canais:
            try:
                canal.parar()
            except Exception:  # noqa: BLE001
                pass

    # ---- roteamento de mensagem vinda de um canal
    def receber(self, canal, remetente: str, texto: str) -> str | None:
        autorizado = canal.autorizado(remetente)
        return processar_comando(self.cfg, texto, remetente,
                                 self.decidir, self.runner,
                                 autorizado)


def start_automatico(cfg) -> Gateway | None:
    """Chamado pelo `betterme server`: sobe os canais ligados no config."""
    gw = None
    if str(getattr(cfg, "telegram_on", False)).lower() not in \
            ("false", "0", "no", ""):
        from .telegram_gw import CanalTelegram
        gw = gw or Gateway(cfg)
        gw.adicionar(CanalTelegram(cfg))
    if str(getattr(cfg, "whatsapp_on", False)).lower() not in \
            ("false", "0", "no", ""):
        from .whatsapp_gw import CanalWhatsapp
        cw = CanalWhatsapp(cfg)
        if cw.disponivel():
            gw = gw or Gateway(cfg)
            gw.adicionar(cw)
        else:
            print("⚠ WhatsApp: playwright não instalado — "
                  "betterme whatsapp setup")
    if gw is not None:
        gw.iniciar()
        print(f"📱 gateway ativo: {len(gw.canais)} canal(is)")
    return gw
