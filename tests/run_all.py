#!/usr/bin/env python3
"""Suíte de testes do Hermes Agent (v3.0).

Rode com:
    ./.venv/bin/python tests/run_all.py        # no projeto
    python3 tests/run_all.py                    # se as deps estiverem globais

Cada caso usa um diretório temporário PRÓPRIO (nada toca em ~/.hermes).
Cobre: módulos v3.0 (backups, auditoria, métricas, notificações, memória,
seletor, orçamento, paralelismo, cache, scheduler, supervisor), endpoints
da API, regressões das v2.x (JSON solto, anti-loop, modo leve do Claude
Code, keep_alive, denylist) e a CLI.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HERMES_MOCK", "1")

try:
    import flask  # noqa: F401
except ImportError:
    print("✖ flask não encontrado — rode com o venv do projeto:")
    print("    ./.venv/bin/python tests/run_all.py")
    sys.exit(2)

from hermes.config import Config  # noqa: E402

CASES = []
PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def case(fn):
    CASES.append(fn)
    return fn


def fresh(**overrides) -> Config:
    """Config isolada em diretório temporário (anti-contaminação)."""
    cfg = Config(data_dir=tempfile.mkdtemp(prefix="hermes-t-"), mock=True)
    for k, v in overrides.items():
        cfg.update({k: v})
    return cfg


def run_all() -> int:
    for fn in CASES:
        name = fn.__name__.replace("_", " ").strip("T 0123456789") or fn.__name__
        try:
            fn()
            PASSED.append(fn.__name__)
            print(f"  ✔ {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            FAILED.append((fn.__name__, f"{exc}"))
            print(f"  ✖ {fn.__name__}: {exc}")
    print("\n" + "═" * 60)
    print(f"RESULTADO: {len(PASSED)} OK · {len(FAILED)} falha(s) · {len(CASES)} casos")
    if FAILED:
        print("\nFalhas:")
        for name, err in FAILED:
            print(f"  ✖ {name}: {err[:200]}")
    return 0 if not FAILED else 1


# ══════════════════════════════ módulos v3.0 ══════════════════════════════

@case
def T01_backups_grava_restaura_preserva():
    from hermes import backups as B
    from hermes.tools import execute_tool

    cfg = fresh()
    f = cfg.workdir / "relatorio.txt"
    f.write_text("versão 1", encoding="utf-8")
    r = execute_tool("write_file", {"path": "relatorio.txt", "content": "versão 2"}, cfg)
    assert r["ok"] and "backup da versão anterior" in r["output"], r
    bks = B.list_backups(cfg)
    assert len(bks) == 1
    assert (cfg.data_dir / "backups" / bks[0]["id"]).read_text(encoding="utf-8") == "versão 1"
    res = B.restore(cfg, bks[0]["id"])
    assert res["ok"] and f.read_text(encoding="utf-8") == "versão 1"
    assert len(B.list_backups(cfg)) == 2          # restore preservou o atual
    assert "relatorio" in execute_tool("backups", {"action": "list"}, cfg)["output"]


@case
def T02_backups_bloqueia_fora_do_workspace():
    from hermes import backups as B

    cfg = fresh()
    outside = Path(tempfile.mkdtemp()) / "alvo.txt"
    outside.write_text("segredo", encoding="utf-8")
    bdir = cfg.data_dir / "backups" / "2026-01-01"
    bdir.mkdir(parents=True)
    (bdir / "000000-alvo.txt").write_text("velho", encoding="utf-8")
    odir = cfg.data_dir / "backups" / ".origins"
    odir.mkdir(parents=True)
    (odir / "2026-01-01__000000-alvo.txt.txt").write_text(
        str(outside), encoding="utf-8")
    res = B.restore(cfg, "2026-01-01/000000-alvo.txt")
    assert not res["ok"] and "workspace" in res["msg"]


@case
def T03_auditoria_registra_e_consulta():
    from hermes import audit
    from hermes.tools import execute_tool

    cfg = fresh()
    execute_tool("list_dir", {"path": "."}, cfg)
    execute_tool("run_command", {"command": "echo auditoria"}, cfg)
    recs = audit.query(cfg, limit=10)
    assert {r["tool"] for r in recs} >= {"list_dir", "run_command"}
    assert all("ts" in r and "ok" in r and "duration_ms" in r for r in recs)
    assert any(s["tool"] == "run_command" for s in audit.tools_summary(cfg))


@case
def T04_metricas_record_summary_recent():
    from hermes import metrics

    cfg = fresh()
    metrics.record(cfg, "hermes", "modelo-x", 12.0, 240, 20.0, 3)
    metrics.record(cfg, "claude", "modelo-x", 8.0, 100, 12.5, 1)
    s = metrics.summary(cfg)
    assert s["n"] == 2 and s["avg_tok_s"] == 16.2 and len(s["spark"]) == 2
    assert metrics.recent(cfg, agent="claude")[0]["agent"] == "claude"


@case
def T05_notificacoes_push_unread_mark():
    from hermes import notify

    cfg = fresh()
    notify.push(cfg, "task_error", "Falhou", "detalhe")
    notify.push(cfg, "mcp", "MCP renasceu")
    assert notify.unread_count(cfg) == 2
    assert notify.list_all(cfg)[0]["kind"] == "mcp"
    notify.mark_all_read(cfg)
    assert notify.unread_count(cfg) == 0


@case
def T06_memoria_por_relevancia():
    from hermes.memory import MemoryStore

    cfg = fresh()
    mem = MemoryStore(cfg)
    for txt in ("O usuário se chama João e mora em Manaus",
                "O servidor de produção roda Debian 12",
                "Prefere respostas curtas e diretas",
                "O gato do usuário se chama Mia",
                "Trabalha com logística de cargas pelo rio",
                "Usa Zorin Linux no notebook com 10 GB de RAM"):
        mem.add(txt)
    top = " | ".join(f["text"] for f in mem.relevant("qual o sistema do computador?", k=2))
    assert "Zorin" in top or "Debian" in top
    assert "Zorin" in mem.prompt_section("sistema operacional da máquina?")


@case
def T07_seletor_de_ferramentas_mcp():
    from hermes.agent import Agent

    cfg = fresh()
    ag = Agent(cfg)
    descs = ["pesquisa dados do figma", "envia e-mail pelo gmail", "consulta estoque",
             "gera fatura pdf", "lista arquivos do projeto", "cria evento na agenda",
             "consulta clima tempo", "traduz texto", "acessa o banco postgres"]
    tools = [{"type": "function", "function": {"name": f"mcp_s{i}_t{j}", "description": d}}
             for i, d in enumerate(descs) for j in (1, 2)]
    sel = ag._select_mcp_tools("consulte o clima de amanhã", tools)
    assert len(sel) == 8 and sel[0]["function"]["name"].startswith("mcp_s6")
    assert len(ag._select_mcp_tools("x", tools[:5])) == 5   # ≤8 não filtra


# ══════════════════════════════ agente v3.0 ══════════════════════════════

@case
def T08_orcamento_corta_cadeia_infinita():
    from hermes.agent import Agent

    cfg = fresh(max_tool_calls=3, max_steps=20)

    class Cadeia:
        simulated = False
        n = 0

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            Cadeia.n += 1
            yield {"message": {"content": "", "tool_calls": [
                {"function": {"name": "run_command",
                              "arguments": {"command": f"echo passo-{Cadeia.n}"}}}]}}

    evs: list[dict] = []
    final = Agent(cfg, client=Cadeia()).run([{"role": "user", "content": "vai"}],
                                            on_event=evs.append)
    execs = [e for e in evs if e["type"] == "tool_start"]
    assert len(execs) == 3, f"executou {len(execs)}"
    assert any("orçamento" in e["message"] for e in evs if e["type"] == "note")
    assert "orçamento de ferramentas esgotado" in final


@case
def T09_ferramentas_em_paralelo():
    from hermes.agent import Agent

    cfg = fresh()

    class Duas:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            if any(m.get("role") == "tool" for m in messages):
                yield {"message": {"content": "pronto, coletei os dois"}}
            else:
                yield {"message": {"content": "", "tool_calls": [
                    {"function": {"name": "sys_info", "arguments": {}}},
                    {"function": {"name": "list_dir", "arguments": {"path": "."}}}]}}

    evs: list[dict] = []
    final = Agent(cfg, client=Duas()).run([{"role": "user", "content": "diag"}],
                                          on_event=evs.append)
    assert [e["name"] for e in evs if e["type"] == "tool_start"] == ["sys_info", "list_dir"]
    assert "pronto" in final


@case
def T10_cache_do_prompt():
    from hermes.agent import Agent
    from hermes.memory import MemoryStore

    cfg = fresh()

    class Fala:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            yield {"message": {"content": "ok"}}

    ag = Agent(cfg, client=Fala())
    p1 = ag.system_prompt("pergunta A")
    nuc = ag._prompt_cache[1]                             # núcleo cacheado
    id_antes = id(ag._prompt_cache)
    p2_ = ag.system_prompt("pergunta A")
    assert id(ag._prompt_cache) == id_antes                # cache NÃO remontou
    assert p2_.startswith(nuc) and "Data/hora local:" in p2_
    MemoryStore(cfg).add("fato novo importante")
    p3 = ag.system_prompt("pergunta A")
    assert id(ag._prompt_cache) != id_antes                # memória invalida
    assert "fato novo importante" in p3
    chave_a = ag._prompt_key("pergunta A")
    ag.system_prompt("pergunta B")
    assert ag._prompt_key("pergunta A") == chave_a          # chave estável
    assert "fato novo importante" in ag._prompt_cache[1]


@case
def T11_passos_com_duracao():
    from hermes.agent import Agent

    cfg = fresh()

    class Uma:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            if any(m.get("role") == "tool" for m in messages):
                yield {"message": {"content": "feito"}}
            else:
                yield {"message": {"content": "", "tool_calls": [
                    {"function": {"name": "sys_info", "arguments": {}}}]}}

    evs: list[dict] = []
    Agent(cfg, client=Uma()).run([{"role": "user", "content": "x"}], on_event=evs.append)
    steps = [e for e in evs if e["type"] == "step"]
    assert steps and all(isinstance(e.get("t"), float) for e in steps)


@case
def T12_prompt_de_sistema_continua_enxuto():
    from hermes.agent import Agent

    cfg = fresh()
    ag = Agent(cfg)

    class Fala:
        simulated = False

        def chat_stream(self, *a, **k):
            yield {"message": {"content": "ok"}}

    ag.client = Fala()
    prompt = ag.system_prompt("teste")
    assert len(prompt) < 6000, f"prompt inflou: {len(prompt)} chars"
    assert "NUNCA simule" in prompt            # direção anti-alucinação v2.2.5


# ══════════════════════════════ regressões v2.x ══════════════════════════════

@case
def T13_regressao_json_solto_v225():
    """O texto EXATO que o modelo do usuário cuspiu deve virar execução REAL."""
    from hermes.agent import Agent

    cfg = fresh()
    texto = ('erton:\n{ "name": "sys_info", "arguments": {}}\n'
             'Kernel: 5.4.0-89-Amazon Linux 2 · RAM: 16 GiB')  # dados alucinados

    class Bugado:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            if any(m.get("role") == "tool" for m in messages):
                yield {"message": {"content": "coletei os dados reais acima"}}
            else:
                yield {"message": {"content": texto}}

    evs: list[dict] = []
    final = Agent(cfg, client=Bugado()).run([{"role": "user", "content": "info"}],
                                            on_event=evs.append)
    starts = [e["name"] for e in evs if e["type"] == "tool_start"]
    assert starts == ["sys_info"], starts
    saida = str([e for e in evs if e["type"] == "tool_end"][0]["output"])
    assert "Amazon Linux" not in saida           # dados inventados descartados
    assert "coletei" in final


@case
def T14_regressao_anti_loop_v227():
    from hermes.agent import Agent

    cfg = fresh()
    call = [{"function": {"name": "list_dir", "arguments": {"path": "."}}}]

    class Teimoso:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            yield {"message": {"content": "Vou listar.", "tool_calls": call}}

    evs: list[dict] = []
    final = Agent(cfg, client=Teimoso()).run([{"role": "user", "content": "liste"}],
                                             on_event=evs.append)
    assert len([e for e in evs if e["type"] == "tool_start"]) == 1
    assert "anti-loop" in final


@case
def T15_regressao_keep_alive_e_options_v221():
    from hermes.agent import Agent

    cfg = fresh(keep_alive="1h", num_predict=512)
    visto: dict = {}

    class Spy:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            visto["options"] = options
            visto["keep_alive"] = keep_alive
            yield {"message": {"content": "ok"}}

    Agent(cfg, client=Spy()).run([{"role": "user", "content": "oi"}])
    assert visto["keep_alive"] == "1h"
    assert visto["options"]["num_predict"] == 512
    assert visto["options"]["num_ctx"] == cfg.num_ctx


@case
def T16_regressao_denylist_seguranca():
    from hermes.tools import execute_tool, is_dangerous

    cfg = fresh()
    r = execute_tool("run_command", {"command": "rm -rf / --no-preserve-root"}, cfg)
    assert not r["ok"] and "perigoso" in r["output"].lower()
    assert is_dangerous("mkfs.ext4 /dev/sda1")
    assert is_dangerous("shutdown now")
    assert not is_dangerous("ls -la")
    r2 = execute_tool("ferramenta_inexistente", {}, cfg)
    assert not r2["ok"]


@case
def T17_claude_modo_leve_e_fallback_de_cli_antiga():
    from hermes.claude_agent import _claude_cmd, run_claude

    # mock=False: precisa executar a CLI de verdade (falsas, abaixo)
    cfg = Config(data_dir=tempfile.mkdtemp(prefix="hermes-t-"), mock=False)
    cfg.update({"model": "qwen2.5-coder:7b", "claude_model": ""})

    # CLI nova: --bare + diretiva PT + ferramentas essenciais + modelo do Hermes
    d = Path(tempfile.mkdtemp())
    nova = d / "claude"
    nova.write_text("#!/bin/bash\n"
                    'if [[ "$1" == "--version" ]]; then echo "2.1.301 (Claude Code)"; exit 0; fi\n'
                    'printf "%s\\n" "$@" > "' + str(d / "args.log") + '"\n'
                    'if [[ "$*" != *"--bare"* ]]; then echo "ERRO: esperava --bare" >&2; exit 3; fi\n'
                    'echo \'{"type":"result","subtype":"success","result":"resposta leve"}\'\n')
    nova.chmod(0o755)
    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    try:
        evs: list[dict] = []
        final = run_claude(cfg, "teste", history=[], on_event=evs.append)
        args = (d / "args.log").read_text()
        assert "--bare" in args and "--max-turns" in args
        assert "PROIBIDO escrever JSON Schema" in args
        assert args.splitlines()[args.splitlines().index("--model") + 1] == "qwen2.5-coder:7b"
        assert "modo leve" in final and "2.1.301" in final      # rodapé autodiagnóstico
    finally:
        os.environ["PATH"] = os.environ["PATH"].replace(str(d) + os.pathsep, "", 1)

    # CLI antiga: rejeita --bare → fallback modo completo + aviso
    d2 = Path(tempfile.mkdtemp())
    velha = d2 / "claude"
    velha.write_text("#!/bin/bash\n"
                     'if [[ "$1" == "--version" ]]; then echo "1.0.66 (Claude Code)"; exit 0; fi\n'
                     'for a in "$@"; do if [[ "$a" == "--bare" ]]; then '
                     'echo "error: unknown option \'--bare\'" >&2; exit 1; fi; done\n'
                     'echo \'{"type":"result","subtype":"success","result":"modo completo"}\'\n')
    velha.chmod(0o755)
    os.environ["PATH"] = str(d2) + os.pathsep + os.environ.get("PATH", "")
    try:
        evs2: list[dict] = []
        final2 = run_claude(cfg, "teste", history=[], on_event=evs2.append)
        assert "modo completo" in final2 and "CLI antiga" in final2
        assert any("claude update" in e.get("message", "") for e in evs2 if e["type"] == "note")
    finally:
        os.environ["PATH"] = os.environ["PATH"].replace(str(d2) + os.pathsep, "", 1)


@case
def T18_claude_model_vazio_usa_modelo_do_hermes_v222():
    from hermes.claude_agent import _claude_cmd

    cfg = fresh()
    cfg.update({"model": "hermes3:8b", "claude_model": ""})
    cmd = _claude_cmd("/bin/claude", cfg, "p", light=True)
    assert cmd[cmd.index("--model") + 1] == "hermes3:8b"
    cfg.update({"claude_model": "qwen2.5-coder:7b"})
    cmd2 = _claude_cmd("/bin/claude", cfg, "p", light=True)
    assert cmd2[cmd2.index("--model") + 1] == "qwen2.5-coder:7b"


# ══════════════════════════════ scheduler v3.0 ══════════════════════════════

@case
def T19_historico_de_execucoes():
    from hermes import scheduler as S

    cfg = fresh()
    store = S.ScheduleStore(cfg)
    e = store.create("tarefa", {"type": "interval", "minutes": 60})
    S.Scheduler(cfg)._execute(e["id"], force=True)
    S.Scheduler(cfg)._execute(e["id"], force=True)
    ent = store.load(e["id"])
    assert ent["run_count"] == 2 and len(ent["history"]) == 2
    pub = store.public_list()[0]
    assert pub["history_n"] == 2


@case
def T20_retry_com_notificacoes():
    from hermes import notify, scheduler as S
    import hermes.agent as A

    cfg = fresh()
    store = S.ScheduleStore(cfg)
    e = store.create("falha", {"type": "interval", "minutes": 60},
                     retries=2, retry_delay_min=1)

    class FalhaTotal:
        simulated = False

        def chat_stream(self, model, messages, tools=None, options=None,
                        cancel=None, keep_alive=None):
            raise A.OllamaError("modelo explodiu")
            yield  # pragma: no cover

    orig = A.get_client
    A.get_client = lambda cfg: FalhaTotal()
    try:
        S.Scheduler(cfg)._execute(e["id"], force=True)
        e2 = store.load(e["id"])
        assert e2["last_status"] == "error" and e2["retries_used"] == 1
        assert e2["retry_at_ts"] is not None
        S.Scheduler(cfg)._execute(e["id"], is_retry=True)
        e3 = store.load(e["id"])
        assert e3["retries_used"] == 2 and e3["retry_at_ts"] is not None
        S.Scheduler(cfg)._execute(e["id"], is_retry=True)
        e4 = store.load(e["id"])
        assert e4["retries_used"] == 0 and e4["retry_at_ts"] is None  # esgotou
    finally:
        A.get_client = orig
    notifs = notify.list_all(cfg)
    assert any("nova tentativa" in n["title"] for n in notifs)
    assert any("FALHOU" in n["title"] for n in notifs)


@case
def T21_watcher_dispara_somente_arquivos_novos():
    from hermes import scheduler as S

    watch = Path(tempfile.mkdtemp())
    cfg = fresh()
    store = S.ScheduleStore(cfg)
    store.create("pdfs", {"type": "interval", "minutes": 60},
                 trigger={"type": "watch", "path": str(watch), "glob": "*.pdf"})
    S.Scheduler(cfg).tick()                       # aprende o estado
    (watch / "contrato.pdf").write_text("x", encoding="utf-8")
    (watch / "nota.txt").write_text("ignora", encoding="utf-8")
    rodou: list[str] = []

    class Spy(S.Scheduler):
        def _execute(self, sid, force=False, is_retry=False, extra_context=""):
            rodou.append(extra_context)
            return {"ok": True}

    Spy(cfg).tick()
    assert len(rodou) == 1 and "contrato.pdf" in rodou[0] and "nota.txt" not in rodou[0]
    Spy(cfg).tick()                               # sem novidades → quieto
    assert len(rodou) == 1


@case
def T22_webhook_nunca_dispara_por_tempo():
    from hermes import scheduler as S

    cfg = fresh()
    store = S.ScheduleStore(cfg)
    store.create("hook", {"type": "interval", "minutes": 1},
                 trigger={"type": "webhook"})
    rodou: list[str] = []

    class Spy(S.Scheduler):
        def _execute(self, sid, force=False, is_retry=False, extra_context=""):
            rodou.append(sid)
            return {"ok": True}

    for _ in range(3):
        time.sleep(0.05)
        Spy(cfg).tick()
    assert rodou == []


@case
def T23_only_idle_adia_quando_ocupada():
    from hermes import scheduler as S

    cfg = fresh()
    store = S.ScheduleStore(cfg)
    e = store.create("pesada", {"type": "interval", "minutes": 1}, only_idle=True)
    ent = store.load(e["id"])
    ent["created_ts"] = time.time() - 120          # intervalo já venceu
    store.save(ent)
    rodou: list[str] = []

    class Spy(S.Scheduler):
        def _execute(self, sid, force=False, is_retry=False, extra_context=""):
            rodou.append(sid)
            return {"ok": True}

    orig = S._system_busy
    try:
        S._system_busy = lambda threshold=2.0: True
        Spy(cfg).tick()
        assert rodou == []
        S._system_busy = lambda threshold=2.0: False
        Spy(cfg).tick()
        assert rodou == [e["id"]]
    finally:
        S._system_busy = orig


@case
def T24_supervisor_reinicia_mcp_morto():
    from unittest.mock import patch

    from hermes import notify
    from hermes.supervisor import McpSupervisor

    cfg = fresh()

    class FakeMgr:
        def __init__(self):
            self.restarted = []

        def status(self):
            return [{"name": "figma", "state": "ativo", "error": None}]

        def _servers(self):
            return {}

        def restart_server(self, name):
            self.restarted.append(name)

    fake = FakeMgr()
    with patch("hermes.mcp_client.get_manager", return_value=fake):
        evs = McpSupervisor(cfg).check_once()
    assert fake.restarted == ["figma"] and evs[0]["restarted"]
    assert any("reiniciado" in n["title"] for n in notify.list_all(cfg))


# ══════════════════════════════ API (test client) ══════════════════════════════

def _app(cfg):
    from hermes.scheduler import Scheduler
    from hermes.server.app import create_app

    app = create_app(cfg)
    app.config["HERMES_SCHEDULER"] = Scheduler(cfg)
    return app.test_client()


@case
def T25_endpoints_leitura_v3():
    cfg = fresh()
    c = _app(cfg)
    assert c.get("/api/audit").json["ok"]
    assert c.get("/api/metrics").json["ok"]
    assert c.get("/api/notifications").json["ok"]
    assert len(c.get("/api/recipes").json["recipes"]) == 6
    checks = c.get("/api/doctor").json["checks"]
    assert [x["id"] for x in checks] == ["ollama", "model", "stt", "claude", "security"]


@case
def T26_chat_gera_metricas_e_auditoria():
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/chat", json={"message": "oi v3", "agent": "hermes"})
    assert r.status_code == 200
    list(r.response)
    assert c.get("/api/metrics?limit=5").json["summary"]["n"] == 1
    # JSON solto com ferramenta real → executa → audita
    r2 = c.post("/api/chat", json={"message": 'rode {"tool": "sys_info", "args": {}}',
                                   "agent": "hermes"})
    list(r2.response)
    ferramentas = [x["tool"] for x in c.get("/api/audit?limit=10").json["records"]]
    assert "sys_info" in ferramentas


@case
def T27_backups_e_restore_pela_api():
    cfg = fresh()
    c = _app(cfg)
    from hermes.tools import execute_tool

    cfg.workdir.joinpath("api.txt").write_text("v1", encoding="utf-8")
    execute_tool("write_file", {"path": "api.txt", "content": "v2"}, cfg)
    bks = c.get("/api/backups").json["backups"]
    assert len(bks) == 1
    r = c.post("/api/backups/restore", json={"id": bks[0]["id"]})
    assert r.json["ok"] and cfg.workdir.joinpath("api.txt").read_text(encoding="utf-8") == "v1"
    assert not c.post("/api/backups/restore", json={"id": "../evil"}).json["ok"]


@case
def T28_webhook_criacao_disparo_e_guardas():
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/schedules", json={"input": "por hook", "when": "a cada 1h",
                                       "trigger": {"type": "webhook"}})
    assert r.json["ok"] and "/api/hooks/" in r.json["msg"]
    sid = r.json["schedule"]
    assert c.post(f"/api/hooks/{sid}").json["ok"]
    comum = c.post("/api/schedules", json={"input": "comum", "when": "diário 07:00"})
    assert c.post(f"/api/hooks/{comum.json['schedule']}").status_code == 400
    assert c.post("/api/hooks/nao-existe-123").status_code == 404


@case
def T29_watch_valida_e_persiste_campos():
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/schedules", json={"input": "x", "when": "a cada 1h",
                                       "trigger": {"type": "watch", "path": "/nao/existe"}})
    assert r.status_code == 400
    r2 = c.post("/api/schedules", json={"input": "x", "when": "a cada 1h",
                                        "trigger": {"type": "watch", "path": "/tmp",
                                                    "glob": "*.pdf"},
                                        "retries": 2, "only_idle": True})
    assert r2.json["ok"]
    w = [s for s in c.get("/api/schedules").json["schedules"]
         if s.get("trigger") and s["trigger"]["type"] == "watch"]
    assert w and w[0]["retries"] == 2 and w[0]["only_idle"]


@case
def T30_export_conversa_md_e_json():
    cfg = fresh()
    c = _app(cfg)
    from hermes.conversations import ConversationStore

    store = ConversationStore(cfg)
    s = store.new_session()
    store.append(s["id"], "user", "Qual o sentido?")
    store.append(s["id"], "assistant", "## R\n\n- 42\n\n```bash\nuname -a\n```", dur=2.5)
    r = c.get(f"/api/conversations/{s['id']}/export?fmt=md")
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert "42" in body and "◈ Hermes" in body and "(2.5s)" in body
    assert '"messages"' in c.get(f"/api/conversations/{s['id']}/export?fmt=json").get_data(as_text=True)


@case
def T31_mcp_add_e_test_endpoint():
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/mcp/add", json={"name": "arquivos", "command": "npx",
                                     "args": ["-y", "server-fs", "/tmp"]})
    assert r.json["ok"] and any(s["name"] == "arquivos" for s in cfg.mcp_servers)
    assert c.post("/api/mcp/add", json={"name": "sem-nada"}).status_code == 400
    # ferramenta MCP desconhecida → erro amigável (não crasha)
    r2 = c.post("/api/mcp/test", json={"tool": "mcp_nada_x", "args": {}})
    assert r2.json["ok"] is False


@case
def T32_settings_aceita_chaves_v3():
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/settings", json={"max_tool_calls": 20, "backups_keep": 30,
                                      "mcp_autorestart": False, "tool_selector": False,
                                      "memory_top_k": 12})
    assert r.json["ok"]
    assert cfg.max_tool_calls == 20 and cfg.backups_keep == 30
    assert cfg.mcp_autorestart is False and cfg.tool_selector is False
    assert cfg.memory_top_k == 12


# ══════════════════════════════ CLI ══════════════════════════════

@case
def T33_cli_versao_e_doctor():
    venv_py = ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    out = os.popen(f'"{py}" -m hermes --version 2>&1').read()
    assert "3.0.0" in out, out
    env = dict(os.environ, HERMES_DATA_DIR=tempfile.mkdtemp(prefix="hermes-cli-"),
               HERMES_MOCK="1")
    import subprocess

    r = subprocess.run([py, "-m", "hermes", "doctor"], capture_output=True,
                       text=True, env=env, timeout=120, cwd=str(ROOT))
    texto = r.stdout + r.stderr
    assert "Doctor" in texto and "Ollama" in texto, texto[:200]


# ══════════════════════════════ v3.0.1 — hardening ══════════════════════════════

@case
def T34_anti_csrf_post_cross_origin():
    """POST de origem estranha sem token = 403; mesma origem/null/curl passam."""
    cfg = fresh()
    c = _app(cfg)
    ok_body = {"input": "x", "when": "diário 07:00"}
    # sem Origin (curl/webhooks) → passa
    assert c.post("/api/schedules", json=ok_body).status_code == 200
    # Origin same-origin (a GUI legítima) → passa
    r = c.post("/api/schedules", json=ok_body,
               headers={"Origin": "http://localhost"})
    assert r.status_code == 200
    # Origin null (iframe sandbox/preview) → passa
    assert c.post("/api/schedules", json=ok_body,
                  headers={"Origin": "null"}).status_code == 200
    # Origin de site malicioso → 403
    assert c.post("/api/schedules", json=ok_body,
                  headers={"Origin": "https://evil.com"}).status_code == 403
    # ...mas passa com token válido (integração externa legítima)
    cfg.update({"auth_token": "segredo"})
    r = c.post("/api/schedules", json=ok_body,
               headers={"Origin": "https://evil.com", "X-Hermes-Token": "segredo"})
    assert r.status_code == 200
    # GET não é afetado pelo guard (só pelo token, se houver)
    assert c.get("/api/status", headers={"Origin": "https://evil.com",
                                         "X-Hermes-Token": "segredo"}).status_code == 200


@case
def T35_webhook_sem_when():
    """Gatilho webhook/watch não exige horário (bug v3.0.0)."""
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/schedules", json={"input": "por hook",
                                       "trigger": {"type": "webhook"}})
    assert r.status_code == 200 and r.json["ok"], r.json
    assert "/api/hooks/" in r.json["msg"]


@case
def T36_prompt_prefixo_estavel_sem_hora():
    """A data/hora sai da chave do cache: prefixo estável entre minutos."""
    from unittest.mock import patch

    from hermes.agent import Agent

    cfg = fresh()
    ag = Agent(cfg)
    with patch("hermes.agent.time.strftime", return_value="2026-01-01 10:00"):
        k1 = ag._prompt_key("pergunta")
        p1 = ag.system_prompt("pergunta")
    with patch("hermes.agent.time.strftime", return_value="2026-01-01 10:59"):
        k2 = ag._prompt_key("pergunta")
        p2 = ag.system_prompt("pergunta")
    assert k1 == k2, "chave ainda depende do relógio"
    assert p1 != p2                                  # hora fresca no final
    assert p1.rstrip().endswith("10:00") and p2.rstrip().endswith("10:59")


@case
def T37_system_busy_relativo_a_nucleos():
    """Load 3.5: ocioso em 16 núcleos, ocupado em 2."""
    from unittest.mock import patch

    import hermes.scheduler as S
    with patch.object(S.Path, "read_text", return_value="3.50 1 1 1/1 1"), \
         patch.object(S.os, "cpu_count", return_value=16):
        assert S._system_busy() is False
    with patch.object(S.Path, "read_text", return_value="3.50 1 1 1/1 1"), \
         patch.object(S.os, "cpu_count", return_value=2):
        assert S._system_busy() is True
    # limiar manual continua honrado (compat)
    with patch.object(S.Path, "read_text", return_value="99.0 1 1 1/1 1"):
        assert S._system_busy(threshold=2.0) is True


if __name__ == "__main__":
    print("◈ Hermes Agent — suíte de testes (v3.0)\n")
    sys.exit(run_all())
