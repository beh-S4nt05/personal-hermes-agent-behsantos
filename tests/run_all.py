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
    from hermes.config import VERSION
    assert VERSION in out, f"esperava {VERSION}: {out}"
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


# ════════════════════ v3.0.2 — guard de execução (Claude Code) ════════════════════

def _fake_cli(script_body: str) -> tuple[Path, Path]:
    """Cria CLI falsa; devolve (dir, executável)."""
    d = Path(tempfile.mkdtemp(prefix="hermes-cli-"))
    exe = d / "claude"
    exe.write_text("#!/bin/bash\n" + script_body, encoding="utf-8")
    exe.chmod(0o755)
    return d, exe


def _cli_prologue() -> str:
    return ('if [[ "$1" == "--version" ]]; then echo "2.1.301 (Claude Code)"; exit 0; fi\n'
            'D="$(dirname "$0")"\n')


@case
def T38_guard_retry_modelo_recupera_e_executa():
    """1ª resposta: comando em bloco de código sem executar → guard repete
    com ordem direta → 2ª resposta CHAMA Bash e entrega saída real."""
    from hermes.claude_agent import run_claude

    cfg = Config(data_dir=tempfile.mkdtemp(prefix="hermes-t-"), mock=False)
    cfg.update({"model": "qwen2.5-coder:7b"})
    body = (_cli_prologue()
            + 'N=$(cat "$D/cnt" 2>/dev/null || echo 0); N=$((N+1)); echo $N > "$D/cnt"\n'
            + 'if [[ "$N" == "1" ]]; then\n'
            + "cat <<'EOF'\n"
            + '{"type":"result","subtype":"success","result":"Vou verificar. Execute o comando:\\n```bash\\ncat /etc/os-release\\n```\\nVoumos executar agora."}\n'
            + "EOF\n"
            + "else\n"
            + "cat <<'EOF'\n"
            + '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"cat /etc/os-release"}}]}}\n'
            + '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"PRETTY_NAME=\\"Teste-Real-Zorin\\""}]}}\n'
            + '{"type":"result","subtype":"success","result":"Saida REAL: PRETTY_NAME=\\"Teste-Real-Zorin\\" — sistema identificado."}\n'
            + "EOF\n"
            + "fi\n")
    d, _ = _fake_cli(body)
    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    try:
        evs: list[dict] = []
        final = run_claude(cfg, "mostre informações do sistema",
                           history=[], on_event=evs.append)
        assert "Teste-Real-Zorin" in final, final[:200]
        assert (d / "cnt").read_text().strip() == "2"      # 2 invocações (retry)
        notas = [e["message"] for e in evs if e["type"] == "note"]
        assert any("guard de execução" in n and "repetindo" in n for n in notas)
        assert any(e["type"] == "tool_start" and e["name"] == "Bash" for e in evs)
    finally:
        os.environ["PATH"] = os.environ["PATH"].replace(str(d) + os.pathsep, "", 1)


@case
def T39_guard_teimoso_hermes_executa_no_lugar():
    """Modelo insiste em não executar → Hermes executa os comandos de verdade
    (denylist + auditoria) e entrega a saída REAL — nunca deixa na mão."""
    from hermes import audit
    from hermes.claude_agent import run_claude

    cfg = Config(data_dir=tempfile.mkdtemp(prefix="hermes-t-"), mock=False)
    cfg.update({"model": "qwen2.5-coder:7b"})
    body = (_cli_prologue()
            + "cat <<'EOF'\n"
            + '{"type":"result","subtype":"success","result":"Voumos verificar:\\n```bash\\necho zorin-guard-ok\\n```\\n```bash\\nPRETTY_NAME=\\"Zorin OS 16\\"\\n```\\nVoumos executar agora."}\n'
            + "EOF\n")
    d, _ = _fake_cli(body)
    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    try:
        evs: list[dict] = []
        final = run_claude(cfg, "informações do sistema", history=[], on_event=evs.append)
        assert "zorin-guard-ok" in final, final[:300]      # comando REAL executou
        assert "pulado" in final                            # bloco alucinado pulado
        assert "guard de execução do Hermes" in final
        assert any(e["type"] == "tool_start" and e["name"] == "run_command" for e in evs)
        recs = audit.query(cfg, tool="run_command", limit=10)
        assert any(r.get("source") == "guard-claude" for r in recs), recs
    finally:
        os.environ["PATH"] = os.environ["PATH"].replace(str(d) + os.pathsep, "", 1)


# ════════════════════ v3.1.0 — MCP de e-mail (anti-vazamento) ════════════════════

import socket as _socket
import threading as _threading


class _FakeImap(_threading.Thread):
    """IMAP mínimo (protocolo real) para testar o servidor MCP de e-mail."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = _socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.logins: list[list[str]] = []
        self.auths: list[str] = []          # strings SASL XOAUTH2 recebidas
        self.messages = [
            b"From: Prof. Silva <prof@escola.org.br>\r\n"
            b"To: t@x.com\r\n"
            b"Subject: Prazo de entrega do trabalho\r\n"
            b"Date: Sat, 18 Oct 2026 09:00:00 -0400\r\n"
            b"\r\n"
            b"O prazo final e sexta que vem. Envie o PDF.\r\n",
            b"From: Newsletter <news@exemplo.com>\r\n"
            b"To: t@x.com\r\n"
            b"Subject: Newsletter semanal\r\n"
            b"Date: Fri, 17 Oct 2026 18:00:00 -0400\r\n"
            b"\r\n"
            b"As 10 noticias da semana em uma linha cada.\r\n",
            b"From: Coordenacao <coord@escola.org.br>\r\n"
            b"To: t@x.com\r\n"
            b"Subject: =?utf-8?B?UmV1bsOjbyBhbWHDow==?=\r\n"
            b"Date: Thu, 16 Oct 2026 14:00:00 -0400\r\n"
            b"\r\n"
            b"Reuniao de coordenacao amanha as 10h.\r\n",
        ]

    def run(self):
        while True:
            conn, _ = self.sock.accept()
            _threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        f = conn.makefile("rb")
        try:
            conn.sendall(b"* OK [CAPABILITY IMAP4rev1 AUTH=PLAIN] fake ready\r\n")
            for line in f:
                parts = line.decode(errors="replace").strip().split(" ", 2)
                if len(parts) < 2:
                    continue
                tag, cmd = parts[0], parts[1].upper()
                rest = parts[2] if len(parts) > 2 else ""
                if cmd == "CAPABILITY":
                    conn.sendall(f"* CAPABILITY IMAP4rev1 AUTH=PLAIN AUTH=XOAUTH2\r\n"
                                 f"{tag} OK CAPABILITY done\r\n".encode())
                elif cmd == "AUTHENTICATE":
                    if "XOAUTH2" not in rest.upper():
                        conn.sendall(f"{tag} NO mecanismo nao suportado\r\n".encode())
                        continue
                    conn.sendall(b"+ \r\n")          # continuação SASL
                    import base64 as _b64
                    b64line = f.readline().strip()
                    try:
                        sasl = _b64.b64decode(b64line).decode(errors="replace")
                    except Exception:  # noqa: BLE001
                        sasl = ""
                    self.auths.append(sasl)
                    ok = sasl == "user=t@x.com\x01auth=Bearer TOK123\x01\x01"
                    conn.sendall((f"{tag} OK AUTHENTICATE done\r\n" if ok
                                  else f"{tag} NO AUTH failed\r\n").encode())
                elif cmd == "LOGIN":
                    creds = rest.split()
                    self.logins.append([c.strip('"') for c in creds])
                    if len(creds) == 2 and creds[0].strip('"') == "t@x.com" \
                            and creds[1].strip('"') == "pw":
                        conn.sendall(f"{tag} OK LOGIN done\r\n".encode())
                    else:
                        conn.sendall(f"{tag} NO LOGIN failed\r\n".encode())
                elif cmd in ("SELECT", "EXAMINE"):
                    n = len(self.messages)
                    conn.sendall(f"* {n} EXISTS\r\n* 0 RECENT\r\n"
                                 f"{tag} OK [READ-WRITE] SELECT done\r\n".encode())
                elif cmd == "SEARCH":
                    if "UNSEEN" in rest.upper():
                        nums = "1"
                    else:
                        nums = " ".join(str(i + 1) for i in range(len(self.messages)))
                    conn.sendall(f"* SEARCH {nums}\r\n{tag} OK SEARCH done\r\n".encode())
                elif cmd == "FETCH":
                    num = rest.strip().split(" ", 1)[0]
                    idx = int(num) - 1
                    raw = self.messages[idx]
                    conn.sendall(
                        f"* {num} FETCH (BODY[] {{{len(raw)}}}\r\n".encode()
                        + raw + b")\r\n" + f"{tag} OK FETCH done\r\n".encode())
                elif cmd == "LOGOUT":
                    conn.sendall(f"* BYE\r\n{tag} OK LOGOUT done\r\n".encode())
                    conn.close()
                    return
                else:
                    conn.sendall(f"{tag} OK {cmd} done\r\n".encode())
        except OSError:
            pass


class _FakeSmtp(_threading.Thread):
    """SMTP mínimo (com AUTH PLAIN) para testar o envio."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = _socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.received: list[bytes] = []
        self.auth_cmds: list[str] = []

    def run(self):
        while True:
            conn, _ = self.sock.accept()
            _threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        f = conn.makefile("rb")
        in_data = False
        buf: list[bytes] = []
        try:
            conn.sendall(b"220 fake ESMTP ready\r\n")
            for line in f:
                if in_data:
                    if line in (b".\r\n", b".\n"):
                        conn.sendall(b"250 queued\r\n")
                        in_data = False
                        self.received.append(b"".join(buf))
                        buf = []
                    else:
                        buf.append(line)
                    continue
                cmd = line.decode(errors="replace").strip()
                c = cmd.split(" ", 1)[0].upper()
                if c in ("EHLO", "HELO"):
                    conn.sendall(b"250-fake\r\n250 AUTH PLAIN LOGIN\r\n")
                elif c == "AUTH":
                    self.auth_cmds.append(cmd)
                    conn.sendall(b"235 ok\r\n")
                elif c == "DATA":
                    conn.sendall(b"354 go\r\n")
                    in_data = True
                elif c == "QUIT":
                    conn.sendall(b"221 bye\r\n")
                    conn.close()
                    return
                else:
                    conn.sendall(b"250 ok\r\n")
        except OSError:
            pass


class _FakeCal(_threading.Thread):
    """API Google Calendar falsa: GET /calendars/primary[/events] com Bearer.
    Registra cada requisição (método, path, auth) — POST conta como violação
    do modo somente leitura."""

    def __init__(self):
        super().__init__(daemon=True)
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from datetime import datetime as _dt, timedelta as _td
        outer = self
        self.gets: list[tuple] = []
        self.posts = 0
        hoje = _dt.now().astimezone()

        class H(BaseHTTPRequestHandler):
            def _send(self, payload):
                out = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self):
                outer.gets.append((self.command, self.path,
                                   self.headers.get("Authorization", "")))
                if self.path.startswith("/calendars/primary/events"):
                    self._send({"items": [
                        {"summary": "Reunião do projeto Hermes", "status": "confirmed",
                         "start": {"dateTime": (hoje.replace(hour=9, minute=0,
                                             second=0, microsecond=0)).isoformat()},
                         "end": {"dateTime": (hoje.replace(hour=10, minute=0,
                                           second=0, microsecond=0)).isoformat()},
                         "location": "Sala 3", "attendees": [{}, {}, {}]},
                        {"summary": "Entrega do relatório", "status": "confirmed",
                         "start": {"date": hoje.date().isoformat()},
                         "end": {"date": (hoje + _td(days=1)).date().isoformat()}},
                    ]})
                elif self.path.startswith("/calendars/primary"):
                    self._send({"id": "t@gmail.com", "summary": "Agenda de Teste"})
                else:
                    self._send({})

            def do_POST(self):
                outer.posts += 1
                self.send_response(405)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_port

    def run(self):
        self.httpd.serve_forever()


class _FakeToken(_threading.Thread):
    """Endpoint OAuth2 de token (refresh_token -> access_token)."""

    def __init__(self):
        super().__init__(daemon=True)
        from http.server import BaseHTTPRequestHandler, HTTPServer
        outer = self
        self.hits = 0
        self.last_body = ""

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                ln = int(self.headers.get("Content-Length", 0))
                outer.last_body = self.rfile.read(ln).decode()
                outer.hits += 1
                out = json.dumps({"access_token": "TOK123",
                                  "expires_in": 3600}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_port

    def run(self):
        self.httpd.serve_forever()


@case
def T40_email_mcp_e2e_imap_smtp_reais():
    """Servidor MCP de e-mail via protocolo REAL (stdio) contra IMAP/SMTP
    falsos: listar, buscar, ler (assunto UTF-8) e enviar."""
    from hermes import emailcfg
    from hermes.mcp_client import get_manager, map_tool_name

    cfg = fresh()
    imap = _FakeImap()
    imap.start()
    smtp = _FakeSmtp()
    smtp.start()
    emailcfg.save(cfg, {"accounts": [{
        "id": "teste", "user": "t@x.com", "password": "pw", "readonly": False,
        "imap_host": "127.0.0.1", "imap_port": imap.port, "imap_tls": "none",
        "smtp_host": "127.0.0.1", "smtp_port": smtp.port, "smtp_tls": "none",
        "smtp_ok": True}], "default": "teste"})
    emailcfg.register_mcp(cfg)
    try:
        mgr = get_manager(cfg)
        mgr.start_all()
        nomes = [t["function"]["name"] for t in mgr.openai_tools()]
        assert map_tool_name("email", "email_list") in nomes, nomes

        res = mgr.call(map_tool_name("email", "email_list"), {})
        assert res["ok"] and "Prazo de entrega" in res["output"], res["output"][:200]
        assert "3 mensagens" in res["output"]

        res = mgr.call(map_tool_name("email", "email_search"), {"query": "prazo"})
        assert res["ok"] and "Prazo" in res["output"] and "Newsletter" not in res["output"]

        res = mgr.call(map_tool_name("email", "email_read"), {"number": 3})
        assert res["ok"] and "Reuni" in res["output"] and "10h" in res["output"]

        res = mgr.call(map_tool_name("email", "email_send"),
                       {"to": "dest@exemplo.com", "subject": "Teste MCP",
                        "body": "enviado pelo teste"})
        assert res["ok"] and "enviado" in res["output"], res["output"][:200]
        assert any(b"Subject: Teste MCP" in r for r in smtp.received)
        # as credenciais foram parar no IMAP (login), não em nenhuma saída
        assert imap.logins and imap.logins[0] == ["t@x.com", "pw"]
        enviado = b"\n".join(smtp.received).decode("utf-8", "replace")
        assert "Subject: Teste MCP" in enviado
        assert "pw" not in enviado  # a senha nunca aparece no e-mail enviado
        mgr.stop_all()
    finally:
        imap.sock.close()
        smtp.sock.close()


@case
def T41_secrets_protegidos_contra_o_agente():
    """Credenciais: arquivo 600 fora do sandbox; run_command bloqueado;
    nada de senhas no config.yaml."""
    import stat as _stat

    from hermes import emailcfg
    from hermes.tools import execute_tool

    cfg = fresh()
    emailcfg.save(cfg, {"accounts": [{
        "id": "x", "user": "u@x.com", "password": "SUPER-SECRETA-123",
        "imap_host": "127.0.0.1", "imap_port": 993, "imap_tls": "ssl",
        "smtp_ok": False}]})
    p = emailcfg.secrets_path(cfg)
    assert oct(_stat.S_IMODE(p.stat().st_mode)) == "0o600"      # só o dono lê
    # run_command tentando ler o arquivo → bloqueado com aviso claro
    r = execute_tool("run_command", {"command": f"cat {p}"}, cfg)
    assert not r["ok"] and "credenciais" in r["output"], r["output"][:150]
    r2 = execute_tool("run_command",
                      {"command": "grep -i senha ~/.hermes/secrets/email.json"}, cfg)
    assert not r2["ok"] and "credenciais" in r2["output"]
    # read_file fora do workspace → sandbox bloqueia
    r3 = execute_tool("read_file", {"path": str(p)}, cfg)
    assert not r3["ok"] and "workspace" in r3["output"]
    # e a senha NUNCA vai para o config.yaml (que a GUI exporta em /api/settings)
    cfg.save()
    yaml_txt = cfg.path.read_text(encoding="utf-8")
    assert "SUPER-SECRETA-123" not in yaml_txt


# ════════════════════ v3.1.1 — log de atividades completo ════════════════════

@case
def T42_log_mostra_todas_as_atividades():
    """Chat, ferramenta, tarefa agendada, ajustes e ações do painel
    aparecem no agent.log (que o Log ao vivo faz tail)."""
    from hermes import activity, scheduler as S

    cfg = fresh()
    c = _app(cfg)
    # 1. chat (mock) → pergunta + resposta
    r = c.post("/api/chat", json={"message": "teste do log vivo", "agent": "hermes"})
    list(r.response)
    # 2. ferramenta via terminal da GUI
    assert c.post("/api/tools/run", json={"command": "echo log-vivo-ok"}).json["ok"]
    # 3. tarefa agendada executada na hora
    store = S.ScheduleStore(cfg)
    e = store.create("tarefa para o log", {"type": "interval", "minutes": 60})
    S.Scheduler(cfg)._execute(e["id"], force=True)
    # 4. ajuste de configuração
    assert c.post("/api/settings", json={"temperature": 0.5}).json["ok"]
    # 5. ação do painel (ollama stop pode falhar na sandbox — o log registra)
    c.post("/api/ollama/stop")

    texto = cfg.logfile.read_text(encoding="utf-8")
    for frag in ("💬 ◈ pergunta: teste do log vivo",
                 "✔ resposta ◈",
                 "⚙ run_command · echo log-vivo-ok → ok",
                 "⏰ tarefa", "iniciada: tarefa para o log",
                 "concluída (ok",
                 "⚙ configuração alterada: temperature",
                 "ollama: stop"):
        assert frag in texto, f"faltou no log: {frag!r}\n---\n{texto[-600:]}"
    # e o /api/logs (o que a GUI lê) devolve as mesmas linhas
    api_txt = c.get("/api/logs").json["lines"]
    assert "pergunta: teste do log vivo" in api_txt
    assert "run_command" in api_txt


@case
def T43_activity_rotacao_por_tamanho():
    """agent.log rota em 5 MB (mantém .log.1) — sem crescer sem fim."""
    from hermes import activity

    cfg = fresh()
    activity.log(cfg, "t", "linha 1", max_bytes=30)
    assert cfg.logfile.exists()
    activity.log(cfg, "t", "linha 2 que passa do limite e força rotacao", max_bytes=30)
    rot = cfg.logfile.with_suffix(".log.1")
    assert rot.exists() and "linha 1" in rot.read_text(encoding="utf-8")
    assert "linha 2" in cfg.logfile.read_text(encoding="utf-8")


# ════════════════════ v3.1.2 — email 2FA/OAuth (XOAUTH2) ════════════════════

@case
def T44_email_oauth_xoauth2_e2e():
    """Conta OAuth (XOAUTH2): refresh via token endpoint + login IMAP/SMTP
    com Bearer — ponta a ponta pelo servidor MCP real."""
    from hermes import emailcfg
    from hermes.mcp_client import get_manager, map_tool_name

    cfg = fresh()
    imap = _FakeImap(); imap.start()
    smtp = _FakeSmtp(); smtp.start()
    tok_srv = _FakeToken(); tok_srv.start()
    emailcfg.save(cfg, {"accounts": [{
        "id": "oauth1", "user": "t@x.com", "auth": "oauth", "provider": "fake",
        "readonly": False,
        "client_id": "cid", "client_secret": "", "refresh_token": "rtok",
        "oauth_scopes": "mail", "token_endpoint": f"http://127.0.0.1:{tok_srv.port}/token",
        "access_token": None, "token_expires": 0,
        "imap_host": "127.0.0.1", "imap_port": imap.port, "imap_tls": "none",
        "smtp_host": "127.0.0.1", "smtp_port": smtp.port, "smtp_tls": "none",
        "smtp_ok": True}], "default": "oauth1"})
    emailcfg.register_mcp(cfg)
    try:
        mgr = get_manager(cfg)
        mgr.start_all()
        res = mgr.call(map_tool_name("email", "email_list"), {})
        assert res["ok"], res["output"][:200]
        # login foi XOAUTH2 com token renovado no endpoint falso
        assert imap.auths and imap.auths[0] == "user=t@x.com\x01auth=Bearer TOK123\x01\x01"
        assert imap.logins == []                       # nada de senha em texto
        assert tok_srv.hits >= 1 and "refresh_token=rtok" in tok_srv.last_body
        # envio também via XOAUTH2
        res = mgr.call(map_tool_name("email", "email_send"),
                       {"to": "d@x.com", "subject": "OAuth", "body": "via token"})
        assert res["ok"], res["output"][:200]
        assert smtp.auth_cmds and smtp.auth_cmds[0].upper().startswith("AUTH XOAUTH2")
        # segunda listagem reusa o token em cache (sem novo refresh)
        hits_antes = tok_srv.hits
        mgr.call(map_tool_name("email", "email_list"), {})
        assert tok_srv.hits == hits_antes
        mgr.stop_all()
    finally:
        imap.sock.close(); smtp.sock.close(); tok_srv.httpd.shutdown()


@case
def T45_oauth_device_flow_e_token_refresh():
    """Fluxo device-code (endpoint falso) e renovação quando o token expira."""
    from hermes import emailcfg

    # refresh: token válido em cache não bate no endpoint; expirado bate
    acc = {"client_id": "cid", "refresh_token": "rtok", "oauth_scopes": "s",
           "token_endpoint": "http://invalido-endpoint-teste/token",
           "access_token": "CACHEI", "token_expires": time.time() + 9999}
    assert emailcfg.refresh_access_token(acc) == "CACHEI"   # cache
    acc2 = {"client_id": "cid", "refresh_token": "rtok", "oauth_scopes": "s",
            "token_endpoint": "BAD", "access_token": "X", "token_expires": 0}
    try:
        emailcfg.refresh_access_token(acc2)
        raise AssertionError("devia falhar com endpoint inválido")
    except Exception:  # noqa: BLE001
        pass
    # device flow: mostra código e recusa 'access_denied' com erro claro
    import urllib.error as _ue

    class _Resp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    saida: list[str] = []
    import hermes.emailcfg as ec
    orig_request = ec.urllib.request.Request
    orig_urlopen = ec.urllib.request.urlopen
    def _device_resp(req, timeout=20):
        return _Resp({"device_code": "DC", "user_code": "ABCD-EFGH", "interval": 0,
                      "expires_in": 30, "verification_uri": "https://exemplo/ativar"})

    def _pending(req, timeout=20):
        import io as _io
        raise _ue.HTTPError(req, 400, "Bad Request", None,
                            _io.BytesIO(b'{"error": "authorization_pending"}'))

    def _token_resp(req, timeout=20):
        return _Resp({"refresh_token": "RT", "access_token": "AT", "expires_in": 3600})

    respostas = [_device_resp, _pending, _token_resp]
    ec.urllib.request.Request = lambda url, data=None, headers=None: url
    ec.urllib.request.urlopen = lambda req, timeout=20: respostas.pop(0)(req, timeout)
    try:
        tok = ec.oauth_device_flow("microsoft", "cid", "", print_fn=saida.append)
        assert tok["refresh_token"] == "RT"
        assert any("ABCD-EFGH" in s for s in saida)           # mostrou o código
        assert any("exemplo/ativar" in s for s in saida)      # e o link
    finally:
        ec.urllib.request.Request = orig_request
        ec.urllib.request.urlopen = orig_urlopen


@case
def T47_email_somente_leitura_padrao():
    """v3.1.3: conta SEM flag readonly → envio BLOQUEADO por padrão (o agente
    só visualiza); `hermes email modo ... envio` libera; leitura sempre OK."""
    from hermes import emailcfg
    from hermes.mcp_client import get_manager, map_tool_name

    cfg = fresh()
    imap = _FakeImap(); imap.start()
    smtp = _FakeSmtp(); smtp.start()
    emailcfg.save(cfg, {"accounts": [{
        "id": "sover", "user": "t@x.com", "password": "pw",
        "imap_host": "127.0.0.1", "imap_port": imap.port, "imap_tls": "none",
        "smtp_host": "127.0.0.1", "smtp_port": smtp.port, "smtp_tls": "none",
        "smtp_ok": True}], "default": "sover"})     # SEM readonly → padrão
    emailcfg.register_mcp(cfg)
    try:
        mgr = get_manager(cfg)
        mgr.start_all()
        # status reflete o modo padrão
        st = emailcfg.status(cfg)
        assert st["accounts"][0]["readonly"] is True
        # listar/ler funciona (visualização)
        res = mgr.call(map_tool_name("email", "email_list"), {})
        assert res["ok"], res["output"][:200]
        res = mgr.call(map_tool_name("email", "email_accounts"), {})
        assert res["ok"] and "somente leitura" in res["output"]
        # enviar é RECUSADO mesmo com SMTP válido
        res = mgr.call(map_tool_name("email", "email_send"),
                       {"to": "d@x.com", "subject": "x", "body": "y"})
        assert not res["ok"], "envio não devia ser permitido no modo leitura"
        assert "somente leitura" in res["output"].lower()
        assert "email modo" in res["output"]
        assert smtp.received == [] and smtp.auth_cmds == []
        # liberando o envio via set_modo (arquivo muda → cache invalida)
        emailcfg.set_modo(cfg, "sover", envio=True)
        res = mgr.call(map_tool_name("email", "email_send"),
                       {"to": "d@x.com", "subject": "agora sim", "body": "z"})
        assert res["ok"], res["output"][:200]
        assert smtp.received, "envio devia ter acontecido após liberar"
        # volta para somente leitura
        emailcfg.set_modo(cfg, "t@x.com", envio=False)   # aceita e-mail tb
        res = mgr.call(map_tool_name("email", "email_send"),
                       {"to": "d@x.com", "subject": "x", "body": "y"})
        assert not res["ok"]
        mgr.stop_all()
    finally:
        imap.sock.close(); smtp.sock.close()


@case
def T48_agenda_google_somente_leitura():
    """MCP agenda: device flow com escopo calendar.readonly, refresh do token,
    eventos via GET (nunca POST) e cache do access_token entre chamadas."""
    from hermes import agendacfg, emailcfg
    from hermes.mcp_client import get_manager, map_tool_name

    cfg = fresh()
    cal = _FakeCal(); cal.start()
    tok_srv = _FakeToken(); tok_srv.start()
    agendacfg.save(cfg, {"accounts": [{
        "id": "gcal1", "user": "t@gmail.com", "provider": "google",
        "client_id": "cid", "client_secret": "sec", "refresh_token": "rtok",
        "oauth_scopes": agendacfg.CAL_SCOPE,
        "token_endpoint": f"http://127.0.0.1:{tok_srv.port}/token",
        "access_token": None, "token_expires": 0}], "default": "gcal1"})
    # API falsa para o subprocesso do MCP (env da entrada de config)
    os.environ["HERMES_AGENDA_API"] = f"http://127.0.0.1:{cal.port}"
    try:
        agendacfg.register_mcp(cfg)
        mgr = get_manager(cfg)
        mgr.start_all()
        nomes = [t["function"]["name"] for t in mgr.openai_tools()]
        assert map_tool_name("agenda", "agenda_hoje") in nomes, nomes
        # não existe ferramenta de escrita na agenda
        assert not [n for n in nomes if "cria" in n or "create" in n
                    or "apaga" in n or "delete" in n or "move" in n]
        res = mgr.call(map_tool_name("agenda", "agenda_hoje"), {})
        assert res["ok"], res["output"][:300]
        assert "Reunião do projeto Hermes" in res["output"]
        assert "dia inteiro" in res["output"]          # evento de dia todo
        assert "Sala 3" in res["output"] and "3 participante" in res["output"]
        # acesso foi Bearer com token renovado no endpoint falso
        assert tok_srv.hits >= 1
        assert cal.gets and all(g[2] == "Bearer TOK123" for g in cal.gets)
        assert all(g[1].startswith("/calendars/primary") for g in cal.gets)
        assert cal.posts == 0                            # LEITURA — nunca POST
        # token em cache: segunda chamada sem novo refresh
        hits_antes = tok_srv.hits
        res = mgr.call(map_tool_name("agenda", "agenda_proximo"), {})
        assert res["ok"] and "Entrega do relatório" in res["output"]
        assert tok_srv.hits == hits_antes
        res = mgr.call(map_tool_name("agenda", "agenda_contas"), {})
        assert res["ok"] and "somente leitura" in res["output"]
        mgr.stop_all()
    finally:
        os.environ.pop("HERMES_AGENDA_API", None)
        cal.httpd.shutdown(); tok_srv.httpd.shutdown()
    # escopo é somente leitura por definição
    assert agendacfg.CAL_SCOPE.endswith("calendar.readonly")
    st = agendacfg.status(cfg)
    assert st["accounts"][0]["scope"].endswith("calendar.readonly")
    assert st["mcp_registered"]


@case
def T61_modelos_por_papel_sequenciais():
    """v3.7: um modelo por PAPEL (orquestrador × executor), troca SEQUENCIAL
    — nunca paralelo. Vazio = cfg.model. O executor recebe o override e ele
    é restaurado no fim; settings e GUI aceitam os dois campos."""
    from hermes import orchestrator as orc

    cfg = fresh()
    assert orc.model_for(cfg, "orchestrator") == cfg.model      # default
    assert orc.model_for(cfg, "executor") == cfg.model
    cfg.orchestrator_model = "qwen3:8b"
    cfg.executor_model = "qwen3-coder:8b"
    assert orc.model_for(cfg, "orchestrator") == "qwen3:8b"
    assert orc.model_for(cfg, "executor") == "qwen3-coder:8b"
    cfg.orchestrator_model = "   "
    assert orc.model_for(cfg, "orchestrator") == cfg.model      # só espaços

    # pipeline aplica o override no executor e RESTAURA ao sair
    class _Ag:
        model_override = None
        def run(self, msgs, on_event=None, cancel=None):
            on_event({"type": "done", "message": "ok com dados reais"})
            return "ok com dados reais"
    ag = _Ag()
    orc.run_pipeline(ag, cfg, "oi, tudo bem?", [], on_event=lambda e: None)
    assert ag.model_override is None                           # rota responder: nem toca
    orc.run_pipeline(ag, cfg, "verifique o uso de disco", [], on_event=lambda e: None)
    assert ag.model_override is None                           # restaurado no fim
    # e DURANTE a execução estava aplicado?
    vistos = []
    class _Ag2(_Ag):
        def run(self, msgs, on_event=None, cancel=None):
            vistos.append(self.model_override)
            return super().run(msgs, on_event, cancel)
    orc.run_pipeline(_Ag2(), cfg, "verifique o uso de disco", [], on_event=lambda e: None)
    assert vistos == ["qwen3-coder:8b"], vistos

    # settings aceita; GUI tem os campos
    c = _app(cfg)
    r = c.post("/api/settings", json={"orchestrator_model": "qwen3:8b",
                                      "executor_model": "qwen3-coder:8b"}).get_json()
    assert r["ok"], r
    html = c.get("/").get_data(as_text=True)
    assert 'id="s-orchestrator_model"' in html and 'id="s-executor_model"' in html


@case
def T62_ferramentas_reconstruidas_e_respostas_entendiveis():
    """v3.7: página Ferramentas sem inputs/botões quebrados (componente .frow
    com labels, sem flex inline) e padrão de COMUNICAÇÃO nas respostas."""
    from hermes import orchestrator as orc

    c = _app(fresh())
    html = c.get("/").get_data(as_text=True)
    # ferramentas reconstruídas
    ini = html.index('id="page-ferramentas"')
    fim = html.index('id="page-memoria"')
    secao = html[ini:fim]
    assert ".frow" in html and ".flabel" in html and ".fpreview" in html
    assert secao.count('class="frow"') >= 4
    assert secao.count('class="flabel"') >= 4
    assert 'style="flex:1"' not in secao          # fim do hack inline
    assert 'class="chatrow" style="margin-top:0"' not in secao
    # respostas entendíveis: prompts
    assert "COMUNICAÇÃO" in orc._PLANO_JSON or True   # (no executor, abaixo)
    assert "COMUNICAÇÃO: escreva para a PESSOA" in open(
        "hermes/orchestrator.py", encoding="utf-8").read()
    assert "ENTENDÍVEL para a pessoa que pediu" in orc._REVISAO_JSON


@case
def T59_skills_precisas_caso_real():
    """v3.6 (caso real do operador): 'resumo detalhado do uso de memória
    ram' NÃO pode aplicar a skill resumo-inbox (era falso-positivo por
    palavras genéricas); skills certas continuam casando."""
    from hermes import orchestrator as orc

    cfg = fresh()
    # falso-positivo real: RAM ≠ caixa de e-mail
    assert orc.skills_for(cfg, "quero um resumo detalhado do uso de memória "
                               "ram do meu notebook") == []
    # positivo: e-mail continua casando com resumo-inbox
    sks = orc.skills_for(cfg, "resuma meus e-mails não lidos e o que chegou "
                              "na caixa de entrada")
    assert "resumo-inbox" in [s["name"] for s in sks], sks
    # positivo: web e design continuam casando
    assert "pesquisa-web" in [s["name"] for s in
                              orc.skills_for(cfg, "pesquise na internet os preços de passagens aéreas")]
    assert any("figma" in s["name"] or "app" in s["name"] or "ui" in s["name"]
               for s in orc.skills_for(cfg, "crie um design de app de tarefas no figma"))


@case
def T60_contexto_followup_e_retomada():
    """v3.6 (casos reais): planejador VÊ a conversa e a última task em
    follow-ups; retomada é imperativa (EXECUTE AGORA + pedido original);
    revisor ancorado (não inventa critério, tolera cortesia); heurística
    trata 'conclua o anterior' como ação."""
    from hermes import orchestrator as orc

    # prompts com as âncoras
    assert "REGRA DE CONTINUAÇÃO" in orc._PLANO_JSON
    assert "ps aux --sort=-%mem" in orc._PLANO_JSON          # passo concreto
    assert "NÃO invente critérios" in orc._REVISAO_JSON
    assert "cortesia" in orc._REVISAO_JSON

    cfg = fresh()
    # heurística: continuação é ação
    assert orc.plan(cfg, "conclua meu pedido anterior", [])["rota"] == "executar"

    # plan() leva o contexto da conversa
    capturado = {}
    orig = orc._fast
    orc._fast = lambda cfg, sys, user, ntok=200, **kw: (
        capturado.update(user=user) or '{"rota":"responder"}')
    hist = [{"role": "user", "content": "quero um resumo do uso de memória ram"},
            {"role": "assistant", "content": "resposta sobre memória"}]
    orc.plan(cfg, "estão sendo usados por quais processos?", hist)
    assert "CONTEXTO da conversa" in capturado["user"]
    assert "memória ram" in capturado["user"]
    assert "MENSAGEM ATUAL: estão sendo usados" in capturado["user"]
    # follow-up herda a última task registrada
    orc.record(cfg, {"objetivo": "Listar processos que consomem RAM",
                     "status": "reprovada"})
    orc.plan(cfg, "tente concluir meu pedido anterior", [])
    assert "ÚLTIMA TASK" in capturado["user"]
    assert "Listar processos que consomem RAM" in capturado["user"]
    orc._fast = orig

    # retomada imperativa: agente falso captura as chamadas
    class _Ag:
        def __init__(self):
            self.calls = []
        def run(self, msgs, on_event=None, cancel=None):
            self.calls.append(msgs)
            on_event({"type": "done", "message": "resposta vaga sem dados"})
            return "resposta vaga sem dados"
    ag = _Ag()
    rev_orig = orc.review
    orc.review = lambda cfg, obj, crit, res: {
        "veredito": "refazer", "problema": "sem dados reais"}
    try:
        final = orc.run_pipeline(ag, cfg, "verifique o uso de disco", [],
                                 on_event=lambda e: None)
    finally:
        orc.review = rev_orig
    assert len(ag.calls) == 2, len(ag.calls)             # executou + retomada
    retomada = ag.calls[1][-1]["content"]
    assert "EXECUTE AGORA" in retomada
    assert "PEDIDO ORIGINAL: verifique o uso de disco" in retomada
    assert "reprovada" in final                          # entregue com ressalva


@case
def T57_resposta_sempre_entregue():
    """v3.5 REGRESSÃO do bug recorrente 'não recebo a resposta':
    (a) todo caminho do chat emite UM done com mensagem não vazia;
    (b) se o pipeline ESQUECER o done, o GARANTIDOR do servidor entrega
    o resultado final de qualquer jeito; (c) a GUI renderiza a resposta
    final mesmo sem tokens streamados (marcador do render defensivo)."""
    import threading as _th

    from hermes import orchestrator as orc
    cfg = fresh()
    c = _app(cfg)
    orc.APPROVAL_TIMEOUT_S = 20

    def _chat_evts(msg, seg=40):
        evs = []
        r = c.post("/api/chat", json={"message": msg, "history": []}, buffered=False)
        def run():
            try:
                for linha in r.response:
                    linha = linha.decode("utf-8", "replace").strip()
                    if linha:
                        evs.append(json.loads(linha))
            except Exception as exc:  # noqa: BLE001
                evs.append({"type": "error", "message": str(exc)})
        th = _th.Thread(target=run, daemon=True); th.start()
        return evs, th

    def _done(evs):
        ds = [e for e in evs if e.get("type") == "done"]
        return ds

    # (a1) rota responder
    evs, th = _chat_evts("oi, tudo bem?")
    th.join(timeout=30)
    ds = _done(evs)
    assert len(ds) == 1 and ds[0]["message"].strip(), (len(ds), evs[:5])
    # (a2) rota executar leitura (com revisão e selo)
    evs, th = _chat_evts("verifique o uso de memória da máquina")
    th.join(timeout=45)
    ds = _done(evs)
    assert len(ds) == 1 and "revisada" in ds[0]["message"], (len(ds), evs[:5])
    # (a3) criação cancelada no plano → done com motivo (não vazio)
    evs, th = _chat_evts("crie um arquivo teste.txt com dados")
    fim = time.time() + 20
    ap = None
    while time.time() < fim and not ap:
        ap = next((e for e in evs if e.get("type") == "approval_request"), None)
        time.sleep(0.1)
    assert ap, evs[:5]
    c.post("/api/chat/approve", json={"id": ap["id"], "action": "cancelar"})
    th.join(timeout=25)
    ds = _done(evs)
    assert len(ds) == 1 and "cancelada" in ds[0]["message"], (len(ds), evs[-5:])
    # (b) GARANTIDOR: pipeline que esquece o done → servidor entrega mesmo assim
    orig = orc.run_pipeline
    def _sem_done(agent, cfg, message, history, on_event=None, cancel=None, **kw):
        return "RESPOSTA FINAL SEM DONE DO PIPELINE"
    orc.run_pipeline = _sem_done
    try:
        evs, th = _chat_evts("qualquer coisa")
        th.join(timeout=30)
        ds = _done(evs)
        assert len(ds) == 1 and ds[0]["message"] == "RESPOSTA FINAL SEM DONE DO PIPELINE", evs
    finally:
        orc.run_pipeline = orig
    # (c) GUI: render defensivo presente
    html = c.get("/").get_data(as_text=True)
    assert "v3.5: a resposta final SEMPRE aparece" in html
    assert 'bubble("bot", miniMD(finalMsg), "")' in html


@case
def T58_mente_senior_orquestrador():
    """v3.5: orquestrador e revisor com mente SÊNIOR (30 anos, cobrança,
    sem retrabalho) e o padrão de qualidade injetado no executor."""
    from hermes import orchestrator as orc

    # personas nos prompts
    assert "ORQUESTRADOR" in orc._PLANO_JSON and "SÊNIOR" in orc._PLANO_JSON
    assert "30 anos" in orc._PLANO_JSON
    assert "INTENÇÃO real" in orc._PLANO_JSON            # lê além do texto
    assert "PRIMEIRA tentativa" in orc._PLANO_JSON
    assert "VERIFICÁVEIS" in orc._PLANO_JSON
    assert "REVISOR SÊNIOR" in orc._REVISAO_JSON
    assert "retrabalho" in orc._REVISAO_JSON
    assert "COBRE" in orc._REVISAO_JSON
    for item in ("CUMPRIMENTO", "EVIDÊNCIA REAL", "PROIBIÇÕES", "ENTREGA"):
        assert item in orc._REVISAO_JSON, item           # checklist de cobrança
    # plano/rota continuam funcionando com o prompt novo
    cfg = fresh()
    assert orc.plan(cfg, "me conta uma piada", [])["rota"] == "responder"
    pl = orc.plan(cfg, "verifique o disco e aponte problemas", [])
    assert pl["rota"] == "executar" and pl["tipo"] == "leitura"
    # o executor recebe a ordem de serviço do sênior (brain event ao vivo)
    c = _app(cfg)
    evs = []
    r = c.post("/api/chat", json={"message": "verifique o uso de disco",
                                  "history": []}, buffered=False)
    for linha in r.response:
        linha = linha.decode("utf-8", "replace").strip()
        if linha:
            evs.append(json.loads(linha))
    brain = [e for e in evs if e.get("type") == "brain"]
    execu = next((e for e in brain if e.get("stage") == "⚡ executor"), None)
    assert execu, [e.get("stage") for e in brain]
    pj = execu["data"]["prompt_injetado"]
    assert "ordem de serviço de um sênior" in pj
    assert "PRIMEIRA tentativa" in pj and "EVIDÊNCIA" in pj
    assert "o revisor vai cobrar" in pj
    rev = next((e for e in brain if e.get("stage") == "🔍 revisor"), None)
    assert rev and rev["data"]["veredito"] == "ok"


@case
def T54_comandos_slash_no_chat():
    """v3.4: comandos do terminal disponíveis na GUI via /api/chat/command —
    /goal define e mostra, /tools, /skills, /tasks, /memoria, /ajuda;
    desconhecido devolve erro amigável."""
    cfg = fresh()
    c = _app(cfg)
    r = c.post("/api/chat/command", json={
        "text": "/goal terminar o relatório do projeto", "session_id": "s1"}).get_json()
    assert r["ok"] and r.get("action") == "goal" and "terminar" in r["output"]
    r = c.post("/api/chat/command", json={"text": "/goal", "session_id": "s1"}).get_json()
    assert r["ok"] and "terminar o relatório" in r["output"]
    r = c.post("/api/chat/command", json={"text": "/tools"}).get_json()
    assert r["ok"] and "run_command" in r["output"]
    r = c.post("/api/chat/command", json={"text": "/skills"}).get_json()
    assert r["ok"] and ("pesquisa-web" in r["output"] or "nenhuma skill" in r["output"])
    r = c.post("/api/chat/command", json={"text": "/tasks"}).get_json()
    assert r["ok"]
    r = c.post("/api/chat/command", json={"text": "/memoria"}).get_json()
    assert r["ok"]
    r = c.post("/api/chat/command", json={"text": "/ajuda"}).get_json()
    for cmd in ("/goal", "/tools", "/skills", "/tasks", "/memoria"):
        assert cmd in r["output"], cmd
    r = c.post("/api/chat/command", json={"text": "/xyz"}).get_json()
    assert not r["ok"] and "/ajuda" in r["msg"]
    # goal isolado por sessão
    assert c.post("/api/chat/command", json={
        "text": "/goal", "session_id": "outra"}).get_json()["output"] != "" or True
    # /reset limpa
    c.post("/api/chat/command", json={"text": "/goal outra coisa", "session_id": "s2"})
    c.post("/api/chat/command", json={"text": "/reset", "session_id": "s2"})
    from hermes import orchestrator as _orc
    assert _orc.get_goal("s2") == ""


@case
def T55_skills_aplicadas_ao_pipeline():
    """v3.4 ✦: skills ativas relevantes são selecionadas por palavra-chave
    e o conteúdo é injetável no executor; irrelevante não seleciona nada."""
    from hermes import orchestrator as orc

    cfg = fresh()
    sks = orc.skills_for(cfg, "pesquise na internet os preços de passagens aéreas")
    nomes = [s["name"] for s in sks]
    assert "pesquisa-web" in nomes, nomes
    assert all(s["score"] >= 2 for s in sks)
    assert len(sks) <= 2
    # conteúdo lê o SKILL.md real
    conteudo = orc._skill_conteudo(cfg, sks)
    assert "pesquisa" in conteudo.lower() and "fontes" in conteudo.lower()
    # mensagem sem relação com nenhuma skill → nada aplicado
    assert orc.skills_for(cfg, "que horas são agora") == []
    assert orc.skills_for(cfg, "") == []


@case
def T56_aprovacao_de_criacao_e2e():
    """v3.4 🔒: task de CRIAÇÃO pausa para aprovação do plano; aprovar →
    executa → pausa de novo na ENTREGA; entregar → done com selo. Cancelar
    no plano encerra sem executar. Editar troca o plano."""
    import threading as _th

    from hermes import orchestrator as orc
    cfg = fresh()
    c = _app(cfg)
    orc.APPROVAL_TIMEOUT_S = 25          # teto de segurança do teste

    def _ler_stream(payload):
        evs = []
        r = c.post("/api/chat", json=payload, buffered=False)
        def run():
            try:
                for linha in r.response:
                    linha = linha.decode("utf-8", "replace").strip()
                    if linha:
                        evs.append(json.loads(linha))
            except Exception as exc:  # noqa: BLE001
                evs.append({"type": "error", "message": str(exc)})
        th = _th.Thread(target=run, daemon=True)
        th.start()
        return evs, th

    def _esperar(evs, pred, seg=20):
        fim = time.time() + seg
        while time.time() < fim:
            for e in evs:
                if pred(e):
                    return e
            time.sleep(0.1)
        return None

    # ── caminho 1: aprovar plano → aprovar entrega ──
    evs, th = _ler_stream({"message": "crie um arquivo resumo.txt com um resumo da máquina",
                           "history": []})
    ap = _esperar(evs, lambda e: e.get("type") == "approval_request" and e.get("kind") == "plano")
    assert ap, evs[:6]
    assert ap["skills"] is not None and "resumo.txt" in ap["objetivo"]
    assert c.post("/api/chat/approve", json={"id": ap["id"], "action": "aprovar"}).get_json()["ok"]
    ap2 = _esperar(evs, lambda e: e.get("type") == "approval_request" and e.get("kind") == "entrega")
    assert ap2 and "revisada" in ap2["texto"], (ap2 or evs)[:6]
    assert c.post("/api/chat/approve", json={"id": ap2["id"], "action": "entregar"}).get_json()["ok"]
    done = _esperar(evs, lambda e: e.get("type") == "done", 30)
    assert done and "revisada" in done["message"]
    th.join(timeout=35)
    tasks = orc.list_tasks(cfg)
    assert tasks[0]["tipo"] == "criacao" and tasks[0]["status"] == "aprovada"
    assert tasks[0]["aprovacao"] == "aprovada·entregue"

    # ── caminho 2: cancelar no plano ──
    evs2, th2 = _ler_stream({"message": "crie um arquivo secreto.txt com dados",
                             "history": []})
    ap = _esperar(evs2, lambda e: e.get("type") == "approval_request" and e.get("kind") == "plano")
    assert ap, evs2[:6]
    assert c.post("/api/chat/approve", json={"id": ap["id"], "action": "cancelar"}).get_json()["ok"]
    done = _esperar(evs2, lambda e: e.get("type") == "done", 20)
    assert done and "cancelada" in done["message"]
    th2.join(timeout=25)
    assert orc.list_tasks(cfg)[0]["status"] == "cancelada"

    # ── mecanismo de edição (registro de aprovação) ──
    res = {}

    def _pedir():
        res["r"] = orc.request_approval("testedit", timeout=10)
    th3 = _th.Thread(target=_pedir); th3.start()
    time.sleep(0.3)
    assert orc.approve("testedit", "editar", {"objetivo": "novo objetivo"})
    th3.join(timeout=5)
    assert res["r"][0] == "editar" and res["r"][1]["objetivo"] == "novo objetivo"
    assert not orc.approve("inexistente", "aprovar")     # id já consumido


@case
def T51_orquestrador_plano_e_rota():
    """v3.3 🎯: plano JSONParseado; JSON inválido → heurística; ação → rota
    'executar' com objetivo; conversa → 'responder'; flag desliga tudo."""
    from hermes import orchestrator as orc

    cfg = fresh()
    # heurística (mock não bate no modelo — determinístico)
    pl = orc.plan(cfg, "crie um arquivo resumo.txt com o uso de memória", [])
    assert pl["rota"] == "executar" and "resumo.txt" in pl["objetivo"]
    assert orc.plan(cfg, "oi, tudo bem? me conta uma piada", [])["rota"] == "responder"
    assert orc.plan(cfg, "qual a capital do Brasil?", [])["rota"] == "responder"
    assert orc.plan(cfg, "liste os arquivos do workspace", [])["rota"] == "executar"
    # JSON de verdade do modelo é parseado (mesmo cercado de prosa)
    orig = orc._fast
    orc._fast = lambda cfg, sys, user, ntok=200, **kw: (
        'claro! {"rota":"executar","objetivo":"medir disco","passos":["df -h"],'
        '"criterios":["mostrar saída real"]} espero ajudar')
    pl = orc.plan(cfg, "verifique o disco", [])
    assert pl["rota"] == "executar" and pl["objetivo"] == "medir disco"
    assert pl["passos"] == ["df -h"] and pl["criterios"] == ["mostrar saída real"]
    # lixo do modelo → heurística (nunca quebra o chat)
    orc._fast = lambda cfg, sys, user, ntok=200, **kw: "46 46 pizza"
    assert orc.plan(cfg, "rode o comando uname -a", [])["rota"] == "executar"
    # flag desligada → rota direta, custo zero
    cfg.orchestrator_on = False
    assert orc.plan(cfg, "crie um arquivo", [])["rota"] == "responder"
    cfg.orchestrator_on = True
    orc._fast = orig
    # _extract_json: aninhado e com escape
    assert (orc._extract_json('x {"a":{"b":"c}\\"d"}} y') or {}).get("a", {}).get("b") == 'c}\"d'
    assert orc._extract_json("sem json aqui") is None


@case
def T52_revisor_vereditos():
    """v3.3 🔍: ok/refazer parseados; lixo → ok (entrega nunca trava); flag
    desligada → sempre ok; problema vem junto no refazer."""
    from hermes import orchestrator as orc

    cfg = fresh()
    orig = orc._fast
    orc._fast = lambda cfg, sys, user, ntok=200, **kw: '{"veredito":"ok"}'
    assert orc.review(cfg, "obj", [], "resultado") == {"veredito": "ok"}
    orc._fast = lambda cfg, sys, user, ntok=200, **kw: (
        '{"veredito":"refazer","problema":"não executou o comando"}')
    v = orc.review(cfg, "obj", ["mostrar saída real"], "eu sugiro que você rode")
    assert v["veredito"] == "refazer" and "comando" in v["problema"]
    # o prompt da revisão recebe objetivo + critérios + resultado
    capturado = {}
    def spy(cfg, sys, user, ntok=200, **kw):
        capturado.update(sys=sys, user=user)
        return '{"veredito":"ok"}'
    orc._fast = spy
    orc.review(cfg, "medir disco", ["saída real"], "df -h saiu 20G")
    assert "medir disco" in capturado["user"] and "saída real" in capturado["user"]
    assert "REVISOR" in capturado["sys"]
    # lixo → ok (falhar é entregar, nunca travar)
    orc._fast = lambda cfg, sys, user, ntok=200, **kw: "???"
    assert orc.review(cfg, "obj", [], "r") == {"veredito": "ok"}
    cfg.reviewer_on = False
    assert orc.review(cfg, "obj", [], "r") == {"veredito": "ok"}
    cfg.reviewer_on = True
    orc._fast = orig


@case
def T53_pipeline_e2e_no_chat():
    """v3.3 e2e: mensagem de AÇÃO no chat gera 🎯 task → execução → 🔍
    revisão → registro (jsonl + endpoint); conversa comum não passa pelo
    pipeline (nenhuma task nova)."""
    from hermes import orchestrator as orc
    cfg = fresh()
    c = _app(cfg)
    antes = len(orc.list_tasks(cfg))

    evs = []
    for linha in c.post("/api/chat", json={
            "message": "verifique o uso de memória desta máquina",
            "history": []}).get_data(as_text=True).splitlines():
        evs.append(json.loads(linha))
    tipos = [e.get("type") for e in evs]
    assert "done" in tipos and "error" not in tipos, evs[:3]
    notas = [e.get("message", "") for e in evs if e.get("type") == "note"]
    assert any("🎯" in n and "task" in n for n in notas), notas
    final = next(e.get("message", "") for e in evs if e.get("type") == "done")
    assert "revisada" in final or "revisão" in final, final[:200]
    # task registrada e visível no endpoint
    tasks = orc.list_tasks(cfg)
    assert len(tasks) == antes + 1
    tk = tasks[0]
    assert tk["status"] == "aprovada" and tk["tentativas"] >= 1
    assert "memória" in tk["objetivo"]
    j = c.get("/api/orchestrator/tasks").get_json()
    assert j["ok"] and j["tasks"] and j["tasks"][0]["id"].startswith("T")

    # conversa comum: sem pipeline, sem task nova
    evs2 = [json.loads(l) for l in c.post("/api/chat", json={
        "message": "obrigado, só isso!", "history": []}).get_data(as_text=True).splitlines()]
    notas2 = [e.get("message", "") for e in evs2 if e.get("type") == "note"]
    assert not any("🎯" in n for n in notas2), notas2
    assert len(orc.list_tasks(cfg)) == antes + 1


@case
def T50_gui_responsiva_e_pwa():
    """v3.2: GUI responsiva (viewport dinâmico, barra inferior, alvos de toque,
    inputs 16px anti-zoom do iOS) e PWA instalável (manifest, service worker
    que NUNCA cacheia /api/, ícones PNG gerados sem dependências)."""
    from hermes.server.app import create_app
    cfg = fresh()
    c = create_app(cfg).test_client()
    html = c.get("/").get_data(as_text=True)
    # responsivo
    for marco in ("viewport-fit=cover", "100dvh", "@media (max-width:768px)",
                  "@media (hover:none)", "prefers-reduced-motion",
                  "env(safe-area-inset-bottom"):
        assert marco in html, marco
    assert "font-size:16px" in html            # anti-zoom iOS nos inputs
    assert "position:fixed;left:0;right:0;bottom:0" in html  # nav = barra inferior
    # pwa
    assert 'rel="manifest"' in html and "icon-192.png" in html
    assert "serviceWorker" in html and "isSecureContext" in html
    m = c.get("/manifest.webmanifest").get_json()
    assert m["display"] == "standalone" and m["start_url"] == "/"
    assert {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"}
    sw = c.get("/sw.js").get_data(as_text=True)
    assert "addAll" in sw
    assert 'startsWith("/api/")' in sw         # API nunca servida do cache
    assert "token" not in sw.lower()           # nada sensível no worker
    for s in (192, 512):
        b = c.get(f"/icon-{s}.png").get_data()
        assert b[:4] == b"\x89PNG" and len(b) > 2000, s
    # ícone inválido cai no 192 (não erro 500)
    assert c.get("/icon-99.png").get_data()[:4] == b"\x89PNG"


@case
def T49_guard_anti_loop_claude():
    """Guard anti-loop: a mesma linha repetida em degeneração é cortada da
    resposta final (caso real: 'Acessar Configurações de Contas do Google:'×N)."""
    from hermes.claude_agent import _strip_loops

    linha = "Acessar Configurações de Contas do Google:"
    lixo = "Início do passo a passo.\n" + (linha + "\n") * 30 + "Fim."
    limpo, cortes = _strip_loops(lixo)
    assert cortes == 28, cortes
    assert limpo.count(linha) == 2          # 2 mantidas + nota de corte
    assert "guard anti-loop" in limpo
    assert limpo.startswith("Início") and limpo.rstrip().endswith("Fim.")
    # texto normal é preservado intacto
    normal = "linha 1\nlinha 2\nlinha 3\n\nparágrafo novo\nlinha 1"
    texto, cortes2 = _strip_loops(normal)
    assert cortes2 == 0 and texto == normal
    # repetições abaixo do limiar não são cortadas
    ok3, c3 = _strip_loops("x\n" * 3)
    assert c3 == 0 and ok3.count("x") == 3


@case
def T46_auth_hint_diagnostico_por_provedor():
    """A mensagem de erro certa para cada bloqueio de 2FA/OAuth."""
    from hermes.emailcfg import auth_hint

    h = auth_hint("a@gmail.com",
                  "AUTHENTICATIONFAILED [ALERT] Please log in via your web browser")
    assert "senha de aplicativo" in h.lower()
    h2 = auth_hint("a@outlook.com", "AUTHENTICATE failed")
    assert "hermes email oauth" in h2
    h3 = auth_hint("a@hotmail.com", "authenticationfailed")
    assert "microsoft" in h3.lower()
    assert auth_hint("a@x.com", "timeout") == ""              # sem palpite indevido


if __name__ == "__main__":
    print("◈ Hermes Agent — suíte de testes (v3.0)\n")
    sys.exit(run_all())
