"""CLI do Betterme Agent.

Principais comandos:
  betterme chat                      chat interativo no terminal
  betterme run "tarefa"              executa uma tarefa única
  betterme daemon                    roda o daemon em primeiro plano
  betterme server                    sobe a GUI web (ligar/desligar, chat, fila)
  betterme status                    status do agente e do Ollama
  betterme agent start|stop|restart  controla o daemon
  betterme ollama start|stop|status  controla o servidor Ollama
  betterme ollama pull [modelo]      baixa modelo
  betterme tasks                     lista fila de tarefas/resultados
  betterme config show|set           vê/altera configuração
"""

from __future__ import annotations

import argparse
import json
import sys

from . import VERSION
from .config import DEFAULTS, Config


# ------------------------------------------------------------------ helpers

def _cfg(args) -> Config:
    import os

    if getattr(args, "data_dir", None):
        os.environ["BETTERME_DATA_DIR"] = args.data_dir
    if getattr(args, "mock", False):
        os.environ["BETTERME_MOCK"] = "1"
    return Config()


def _p(text: str = "") -> None:
    print(text)


def _ok(msg: str) -> None:
    print(f"✔ {msg}")


def _fail(msg: str) -> None:
    print(f"✖ {msg}", file=sys.stderr)
    raise SystemExit(1)


# ------------------------------------------------------------------ comandos

def cmd_status(args) -> None:
    from .manager import DaemonManager, OllamaManager

    cfg = _cfg(args)
    agent = DaemonManager(cfg).status()
    ollama = OllamaManager(cfg).status()

    _p(f"\n◈ Betterme Agent v{VERSION}{'  [MODO DEMONSTRAÇÃO — Ollama simulado]' if cfg.mock else ''}")
    _p(f"  dados      : {cfg.data_dir}")
    _p(f"  modelo     : {cfg.model}")
    _p("  ── agente " + "─" * 40)
    if agent["running"]:
        up = agent.get("uptime_s") or 0
        _p(f"  estado     : 🟢 LIGADO (pid {agent['pid']}, {agent['status']}, há {int(up // 60)}min{int(up % 60)}s)")
    else:
        _p("  estado     : 🔴 DESLIGADO")
    _p("  ── ollama " + "─" * 40)
    if not ollama["installed"]:
        _p("  estado     : ⚠ NÃO INSTALADO  (rodar ./install.sh ou curl -fsSL https://ollama.com/install.sh | sh)")
    elif ollama["running"]:
        models = ", ".join(ollama["models"]) or "nenhum modelo baixado"
        _p(f"  estado     : 🟢 LIGADO  (v{ollama['version']}, {ollama['managed_by']})")
        _p(f"  modelos    : {models}")
    else:
        _p("  estado     : 🔴 DESLIGADO  (ligue com: betterme ollama start)")
    _p()


def cmd_agent(args) -> None:
    from .manager import DaemonManager

    cfg = _cfg(args)
    mgr = DaemonManager(cfg)
    if args.action == "status":
        st = mgr.status()
        _p(json.dumps(st, ensure_ascii=False, indent=2))
        return
    result = getattr(mgr, args.action)()
    (_ok if result["ok"] else _fail)(result["msg"])


def cmd_email(args) -> None:
    """Configura contas de e-mail para o servidor MCP (credenciais locais)."""
    from .emailcfg import _imap_login, load, setup_interactive, status

    cfg = _cfg(args)
    action = getattr(args, "email_action", "status")
    if action == "setup":
        setup_interactive(cfg)
        return
    if action == "oauth":
        from .emailcfg import _oauth_wizard
        _oauth_wizard(cfg)
        return
    if action == "test":
        data = load(cfg)
        if not data.get("accounts"):
            _p("  nenhuma conta — rode: betterme email setup")
            return
        for a in data["accounts"]:
            ok, detail = _imap_login(a)
            modo = ("🔎 somente leitura" if a.get("readonly", True)
                    else "✉ leitura+envio")
            _p(f"  {'✔' if ok else '✖'} {a.get('user')} [{a.get('id')}] — "
               f"{detail} · {modo}")
        return
    if action == "modo":
        from .emailcfg import set_modo
        conta = getattr(args, "conta", None)
        novo = (getattr(args, "novo_modo", None) or "").strip().lower()
        data = load(cfg)
        if not conta:
            for a in data.get("accounts", []):
                modo = ("🔎 somente leitura" if a.get("readonly", True)
                        else "✉ leitura+envio")
                _p(f"  · {a.get('user')} [{a.get('id')}] — {modo}")
            _p("  uso: betterme email modo <conta> envio|leitura")
            return
        if novo not in ("envio", "leitura"):
            _p("  ✖ informe: betterme email modo <conta> envio|leitura")
            return
        try:
            a = set_modo(cfg, conta, envio=(novo == "envio"))
        except ValueError as exc:
            _p(f"  ✖ {exc}")
            return
        modo = "🔎 somente leitura (visualização)" if a.get("readonly") \
            else "✉ leitura+envio"
        _p(f"  ✔ {a.get('user')} [{a.get('id')}] → {modo}")
        return
    st = status(cfg)
    _p("\n📧 E-mail do Betterme Agent")
    _p(f"  arquivo de credenciais: {st['secrets_file']} "
       f"({'✔ existe, permissão ' + st['mode'] if st['exists'] else '✖ não configurado'})")
    for a in st["accounts"]:
        modo = ("🔎 somente leitura" if a.get("readonly", True)
                else ("✉ leitura+envio" if a.get("smtp_ok")
                      else "🔎 leitura (SMTP não validado)"))
        _p(f"  · {a['user']} [{a['id']}] — {a['imap_host']} · {modo}")
    _p(f"  servidor MCP 'email' no config: "
       f"{'✔' if st['mcp_registered'] else '✖ (rode betterme email setup)'}")


def cmd_agenda(args) -> None:
    """Agenda Google Calendar — somente leitura (MCP agenda_*)."""
    from . import agendacfg

    cfg = _cfg(args)
    action = getattr(args, "agenda_action", "status")
    if action == "oauth":
        agendacfg.setup_interactive(cfg)
        return
    if action == "test":
        try:
            _p("\n" + agendacfg.list_events(cfg, dias=1))
        except RuntimeError as exc:
            _p(f"  ✖ {exc}")
        return
    st = agendacfg.status(cfg)
    _p("\n🗓 Agenda do Betterme Agent — somente leitura")
    _p(f"  arquivo de credenciais: {st['secrets_file']} "
       f"({'✔ existe, permissão ' + st['mode'] if st['exists'] else '✖ não configurado'})")
    for a in st["accounts"]:
        _p(f"  · {a['user']} [{a['id']}] — {a['scope']}")
    _p(f"  servidor MCP 'agenda' no config: "
       f"{'✔' if st['mcp_registered'] else '✖ (rode betterme agenda oauth)'}")
    if not st["accounts"]:
        _p("  para conectar: betterme agenda oauth  (fluxo com seu 2FA, sem senha)")


def cmd_doctor(args) -> None:
    """Diagnóstico completo: config -> Ollama (com geração real) -> agente."""
    from .manager import DaemonManager, OllamaManager

    cfg = _cfg(args)
    _p("\n◈ Betterme Doctor — diagnóstico da conexão Ollama ↔ Python")
    _p("─" * 58)
    _p(f"  config      : {cfg.path}")
    _p(f"  endereço    : {cfg.ollama_url}")
    _p(f"  modelo      : {cfg.model}")

    _p("─" * 58)
    mgr = OllamaManager(cfg)
    diag = mgr.diagnose(deep=True)
    for s in diag["steps"]:
        mark = "✔" if s["ok"] else "✖"
        _p(f"  {mark} {s['name']:<20} {s['detail']}")

    _p("─" * 58)
    ag = DaemonManager(cfg).status()
    if ag["running"]:
        _p(f"  ✔ agente            LIGADO (pid {ag['pid']}, {ag['status']})")
    else:
        _p("  • agente            desligado (ligue com: betterme agent start)")

    # v3.0: checklist completo (voz, Claude Code, segurança…)
    _p("─" * 58)
    from .doctor import run_checks as _run_checks
    for c in _run_checks(cfg):
        mark = "✔" if c["ok"] else ("⚠" if c.get("optional") else "✖")
        _p(f"  {mark} {c['name']:<20} {c['detail']}")
        if not c["ok"]:
            _p(f"      → corrigir: {c['fix']}")

    _p("─" * 58)
    if diag["ok"]:
        _p("  ✅ TUDO OK — conexão validada, pode trabalhar.\n")
    else:
        _p("  ❌ corrija os itens ✖ acima. Comandos úteis:")
        _p("     sudo systemctl start ollama      # ligar o serviço")
        _p("     ollama pull hermes3:8b           # baixar o modelo")
        _p("     betterme config set model hermes3:8b  # corrigir o modelo")
        _p("")


def cmd_ollama(args) -> None:
    from .manager import OllamaManager

    cfg = _cfg(args)
    mgr = OllamaManager(cfg)
    if args.action == "status":
        _p(json.dumps(mgr.status(), ensure_ascii=False, indent=2))
    elif args.action == "test":
        cmd_doctor(args)
        return
    elif args.action in ("start", "stop"):
        result = getattr(mgr, args.action)()
        (_ok if result["ok"] else _fail)(result["msg"])
    elif args.action == "pull":
        from .ollama_client import OllamaError

        model = args.model or cfg.model
        client = mgr.client
        print(f"baixando {model} (pode demorar)…")
        try:

            def progress(data: dict) -> None:
                status = data.get("status", "")
                total, done = data.get("total"), data.get("completed")
                if total and done is not None:
                    pct = done / total * 100
                    sys.stdout.write(f"\r  {status:<28} {pct:5.1f}%")
                else:
                    sys.stdout.write(f"\r  {status:<35}")
                sys.stdout.flush()

            client.pull(model, progress)
            _p()
            _ok(f"modelo {model} disponível")
        except OllamaError as exc:
            _p()
            _fail(str(exc))
    elif args.action == "install":
        _fail("use o instalador do projeto: ./install.sh")


def cmd_run(args) -> None:
    from .agent import Agent

    cfg = _cfg(args)
    agent = Agent(cfg)
    task = " ".join(args.task).strip()

    def on_event(event: dict) -> None:
        if event["type"] == "tool_start":
            args_str = " ".join(f"{k}={v!r}" for k, v in (event.get("args") or {}).items())
            print(f"\033[2m  🔧 {event['name']}({args_str})\033[0m")

    print(f"◈ tarefa: {task}\n")
    final = agent.run([{"role": "user", "content": task}], on_event=on_event)
    print("\n" + "─" * 60)
    print(final)
    print("─" * 60)


def cmd_chat(args) -> None:
    from .tui import run_chat

    run_chat(_cfg(args))


def cmd_update(args) -> None:
    """Atualiza o projeto a partir do GitHub (tags oficiais do repo)."""
    from .update import run as run_update
    raise SystemExit(run_update(check_only=bool(getattr(args, "check", False)),
                                assume_yes=bool(getattr(args, "yes", False))))


def cmd_memory_import(args) -> None:
    """v3.12: importa fatos para a memória do agente (JSON lista de
    strings, ou texto com um fato por linha). Duplicados são pulados."""
    import json as _json
    from pathlib import Path as _P
    from .memory import MemoryStore

    arq = _P(args.arquivo).expanduser()
    try:
        texto = arq.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"não consegui ler {arq}: {exc}")
        raise SystemExit(1) from exc
    if arq.suffix == ".json":
        try:
            dados = _json.loads(texto)
        except ValueError as exc:
            _fail(f"JSON inválido: {exc}")
            raise SystemExit(1) from exc
        if isinstance(dados, dict):
            dados = dados.get("fatos") or dados.get("facts") or []
        fatos = [str(f) for f in dados]
    else:
        fatos = [l for l in texto.splitlines()
                 if l.strip() and not l.strip().startswith("#")]
    novos, dup = MemoryStore(_cfg(args)).import_facts(fatos)
    _p(f"\n🧠 memória: {novos} fato(s) importado(s)"
       + (f" · {dup} duplicado(s) pulado(s)" if dup else ""))
    if not novos and not dup:
        _fail("nenhum fato válido no arquivo")


def cmd_rag(args) -> None:
    """v3.15.0 (PR#2): biblioteca local (RAG) — indexar e consultar."""
    from . import knowledge
    cfg = _cfg(args)
    consulta = str(getattr(args, "consulta", "") or "").strip()
    if consulta:
        for r in knowledge.buscar(cfg, consulta, k=3):
            print(f"── FONTE: {r['fonte']} (relevância {r['score']})")
            print(r["texto"][:600] + "\n")
        return
    st = knowledge.indexar(cfg)
    print(f"📚 biblioteca indexada: {st['livros']} livro(s), "
          f"{st['blocos']} trechos (índice {st['tamanho']} B)")
    print(f"   pasta: {knowledge.biblioteca_dir(cfg)}")
    print("   consulta no chat: ferramenta knowledge_search · "
          "aqui: betterme rag \"sua consulta\"")


def cmd_skills_import(args) -> None:
    """v3.15.0 (PR#3): importa skills de pasta local, .zip, URL ou owner/repo."""
    from .skills import import_from
    r = import_from(str(getattr(args, "fonte", "") or ""), _cfg(args))
    print(r.get("msg") or r)
    for nome in r.get("importadas") or []:
        print(f"  ✦ {nome} — nativa (ativa por padrão)")
    if not r.get("ok"):
        raise SystemExit(1)


def cmd_skills_scan(args) -> None:
    """v3.15.0 (PR#3): varre as pastas assistidas e importa skills novas."""
    from .skills import autoscan
    r = autoscan(_cfg(args))
    importadas = r.get("importadas") or []
    if importadas:
        print(f"✦ {len(importadas)} skill(s) importada(s): "
              f"{', '.join(importadas)}")
    else:
        print("nenhuma skill nova nas pastas assistidas "
              "(baixe para ~/Downloads ou aponte em skills_watch_dirs)")


def cmd_selftest(args) -> None:
    """v3.13.3: bateria de aceitação com LLM REAL (pula sem Ollama)."""
    from .selftest import run as run_selftest
    raise SystemExit(run_selftest(_cfg(args),
                                  timeout=int(getattr(args, "timeout", 240)),
                                  all_models=bool(getattr(args, "all_models",
                                                          False))))


def cmd_skills_audit(args) -> None:
    """v3.11: audita o catálogo de skills (estrutura, tamanho, injeção)."""
    from .skills_audit import run_audit
    raise SystemExit(run_audit(_cfg(args)))


def cmd_daemon(args) -> None:
    from .daemon import run_daemon

    run_daemon(_cfg(args))


def cmd_server(args) -> None:
    from .server.app import serve

    cfg = _cfg(args)
    cfg.ensure_dirs()
    if args.token:
        cfg.auth_token = args.token
    serve(cfg, host=args.host or cfg.host, port=args.port or cfg.port)


def cmd_schedule(args) -> None:
    import time as _time

    from .scheduler import Scheduler, ScheduleStore, human_schedule, parse_schedule

    cfg = _cfg(args)
    store = ScheduleStore(cfg)
    if args.action == "list":
        items = store.public_list()
        if not items:
            _p('nenhuma tarefa agendada — crie com: betterme schedule add "tarefa" "diário 08:30"')
            return
        _p(f"\n⏰ {len(items)} tarefa(s) agendada(s)")
        for s in items:
            mark = "🟢" if s["enabled"] else "⚪"
            _p(f"  {mark} {s['id']}")
            _p(f"      o quê : {s['input'][:90]}")
            _p(f"      quando: {s['human']} | próxima: {s['next_run'] or '—'} | execuções: {s['run_count']}")
        _p()
    elif args.action == "add":
        try:
            spec = parse_schedule(args.when)
        except ValueError as exc:
            _fail(str(exc))
        entry = store.create(args.text, spec)
        _ok(f"agendada ({human_schedule(spec)}): {entry['id']}")
        _p("  dica: o agendador roda dentro do `betterme server` — mantenha-o aberto.")
    elif args.action == "del":
        sid = args.id or args.text or args.when
        removed = store.delete(sid)
        (_ok if removed else _fail)("agendamento removido" if removed else "não encontrado")
    elif args.action == "run":
        sid = args.id or args.text or args.when
        sched = Scheduler(cfg)
        sched.start()
        result = sched.run_now(sid)
        (_ok if result["ok"] else _fail)(result["msg"])
        if result["ok"]:
            _time.sleep(4)
            entry = store.load(args.id)
            if entry and entry.get("last_output"):
                _p("─" * 60)
                _p(entry["last_output"][:1200])
                _p("─" * 60)


def cmd_tasks(args) -> None:
    from .daemon import list_tasks

    cfg = _cfg(args)
    data = list_tasks(cfg)
    _p(f"\n◈ fila de tarefas — {len(data['pending'])} pendente(s), {len(data['done'])} concluída(s)")
    for t in data["pending"]:
        _p(f"  ⏳ {t.get('id')}  {t.get('input', '')[:70]}")
    for t in data["done"]:
        mark = "✔" if t.get("status") == "ok" else "✖"
        dur = t.get("duration_s", "?")
        _p(f"  {mark} {t.get('id')}  [{dur}s]  {t.get('input', '')[:70]}")
    _p()


def cmd_config(args) -> None:
    cfg = _cfg(args)
    if args.action == "show":
        _p(f"# configuração ativa ({cfg.path})")
        _p(json.dumps(cfg.as_dict(), ensure_ascii=False, indent=2))
    elif args.action == "set":
        if len(args.kv) != 2 or args.kv[0] not in DEFAULTS:
            _fail(f"use: betterme config set <chave> <valor>  — chaves: {', '.join(DEFAULTS)}")
        cfg.update({args.kv[0]: args.kv[1]})
        _ok(f"{args.kv[0]} = {getattr(cfg, args.kv[0])!r} salvo em {cfg.path}")
    elif args.action == "edit":
        import os
        import subprocess

        subprocess.run([os.environ.get("EDITOR", "nano"), str(cfg.path)])


def cmd_provider(args) -> None:
    """v3.17.0: provedores LLM externos GRATUITOS (memória nunca sai)."""
    import getpass as _gp
    from .llm_providers import REGISTRY, api_key, salvar_key, testar
    acao = str(getattr(args, "acao", "list"))
    cfg = _cfg(args)
    if acao == "list":
        atual = str(getattr(cfg, "llm_provider", "local"))
        _p("\n🔌 provedores LLM gratuitos (todos compatíveis, sem cartão):")
        for nome, info in REGISTRY.items():
            chave = "sem chave" if info.get("sem_chave") else (
                "chave ok" if api_key(cfg, nome) else "SEM chave")
            marca = " ◀ atual" if nome == atual else ""
            _p(f"  • {nome:11s} {info['model']:42s} {chave}{marca}")
            _p(f"              {info['nota']} · base {info['base']}")
        _p("\n  configure: betterme provider set <nome> [--model X] · "
           "teste: betterme provider test · volte ao local: provider off")
        _p("  🔒 privacidade: a memória/dados pessoais NUNCA vão a provedores "
           "externos;\n     ferramentas e arquivos continuam 100% locais.")
        return
    if acao == "set":
        nome = str(getattr(args, "provedor", "")).strip().lower()
        if nome not in REGISTRY:
            _fail(f"provedor desconhecido: {nome!r} — use: "
                  + ", ".join(REGISTRY))
            raise SystemExit(1)
        modelo = str(getattr(args, "model", "") or "").strip() \
            or REGISTRY[nome]["model"]
        if not REGISTRY[nome].get("sem_chave") and not api_key(cfg, nome):
            key = str(getattr(args, "key", "") or "").strip()
            if not key:
                _p(f"\n🔑 cole a chave de API de {nome} "
                   f"(fica em ~/.betterme/secrets/{nome}.key, modo 600 — "
                   "não aparece na tela):")
                key = _gp.getpass("   chave: ").strip()
            if not key:
                _fail("sem chave — nada configurado")
                raise SystemExit(1)
            arq = salvar_key(cfg, nome, key)
            _p(f"\n🔑 chave gravada em {arq} (600)")
        cfg.update({"llm_provider": nome, "llm_model": modelo})
        _p(f"\n🔌 provedor ativo: {nome} · modelo {modelo}")
        _p("   🔒 memória e dados pessoais ficam no Ollama local; se "
           f"{nome} falhar, cai no local automaticamente.")
        _p("   valide com: betterme provider test")
        return
    if acao == "test":
        nome = str(getattr(cfg, "llm_provider", "local"))
        if nome == "local":
            _p("\n🔌 provedor atual: LOCAL (Ollama) — nada a testar fora")
            return
        _p(f"\n🔌 testando {nome} (chamada real de 1 completion)…")
        r = testar(cfg, nome, str(getattr(cfg, "llm_model", "") or ""))
        _p(("  ✔ " if r["ok"] else "  ✖ ") + r["msg"])
        if not r["ok"]:
            raise SystemExit(1)
        return
    if acao == "off":
        cfg.update({"llm_provider": "local", "llm_model": ""})
        _p("\n🔌 voltou ao LOCAL (Ollama) — chave continua salva em "
           "secrets/ se quiser reativar")
        return


def cmd_varredura(args) -> None:
    """v4.0.0: varre segredos/dados pessoais — 1 se houver crítico."""
    from . import varredura
    code = varredura.cmd(args, _cfg(args))
    if code:
        raise SystemExit(code)


def cmd_init(args) -> None:
    """v4.0.0: cria HERMES.md de partida no projeto."""
    from . import project_context
    project_context.cmd(args, _cfg(args))


def cmd_autonomia(args) -> None:
    """v4.0.0: vê/muda o nível de autonomia (cauteloso|padrao|autonomo)."""
    from . import autonomy
    autonomy.cmd(args, _cfg(args))


def cmd_gerente(args) -> None:
    """v4.0.0 (M7, D5): gerente de código (Claude) — opt-in consciente."""
    from . import code_manager
    code_manager.cmd(args, _cfg(args))


def cmd_telegram(args) -> None:
    """v4.2.0 (PR#5): canal Telegram (token em secrets, allowlist)."""
    from . import telegram_gw
    telegram_gw.cmd(args, _cfg(args))


def cmd_whatsapp(args) -> None:
    """v4.2.0 (PR#5): canal WhatsApp via Playwright (local, removível)."""
    from . import whatsapp_gw
    whatsapp_gw.cmd(args, _cfg(args))


def cmd_arena(args) -> None:
    """v4.3.0 (PR#6): arena — mesma task nos provedores grátis, ranking medido."""
    from . import arena
    arena.cmd(" ".join(getattr(args, "task", []) or []),
              getattr(args, "n", 1) or 1, _cfg(args))


def cmd_grafo(args) -> None:
    """v4.4.0 (PR#7): grafo de código (onde está a lógica de X?)."""
    from . import grafo
    grafo.cmd(args, _cfg(args))


def cmd_revisar(args) -> None:
    """v4.5.0 (PR#8): revisão de diff — gate único pré-push."""
    from . import revisar
    revisar.cmd(args, _cfg(args))


def cmd_aprendidos(args) -> None:
    """v4.0.0 (M6.5): rascunhos de aprendizado (aprovação do operador)."""
    from . import learning
    learning.cmd(args, _cfg(args))


def cmd_skills_aprender(args) -> None:
    """v4.0.0 (M6.5): transforma documento/texto/URL em rascunho de skill."""
    from . import learning
    fonte = " ".join(getattr(args, "fonte", []) or [])
    ok, msg = learning.aprender_de_documento(_cfg(args), fonte)
    print(("✔ " if ok else "✖ ") + msg)
    if not ok:
        raise SystemExit(1)


def cmd_conversas_buscar(args) -> None:
    """v4.0.0 (M6.5): busca textual nas conversas passadas."""
    from .learning import buscar_conversas
    termo = " ".join(getattr(args, "termo", []) or [])
    ach = buscar_conversas(_cfg(args), termo)
    if not ach:
        print(f"🗂 nenhuma conversa menciona {termo!r}")
        return
    print(f"🗂 {len(ach)} trecho(s):")
    for a_ in ach:
        print(f"  [{a_['data']} · {a_['role']} · {a_['titulo']}]")
        print(f"    \"{a_['trecho']}\"")


def cmd_memory_list(args) -> None:
    """v3.16.1: lista os fatos da memória do agente."""
    from .memory import MemoryStore
    fatos = MemoryStore(_cfg(args)).list_all()
    if not fatos:
        _p("\n🧠 memória vazia — importe com: betterme memory import <arquivo>")
        return
    _p(f"\n🧠 memória do agente ({len(fatos)} fato(s)):")
    for f in fatos:
        _p(f"  📔 [{f.get('id', '?')}] {f.get('text', '')[:110]}")


def cmd_memory_clear(args) -> None:
    """v3.16.1: apaga TODOS os fatos da memória (para reimportar um
    pacote organizado sem duplicatas). Pede confirmação, salvo --yes."""
    from .memory import MemoryStore
    ms = MemoryStore(_cfg(args))
    fatos = ms.list_all()
    if not fatos:
        _p("\n🧠 memória já está vazia")
        return
    if not getattr(args, "yes", False):
        _p(f"\n⚠ isto vai apagar {len(fatos)} fato(s) da memória.")
        resp = input("digite SIM para confirmar: ").strip()
        if resp.upper() != "SIM":
            _p("cancelado — nada foi apagado")
            return
    for f in fatos:
        try:
            ms.delete(str(f.get("id")))
        except Exception:  # noqa: BLE001
            pass
    _p(f"\n🧠 memória limpa: {len(fatos)} fato(s) apagado(s)")


def cmd_models(args) -> None:
    from .manager import OllamaManager

    ollama = OllamaManager(_cfg(args)).status()
    if ollama["running"]:
        _p("\nmodelos locais no Ollama:")
        for m in ollama["models"]:
            mark = " ◀ atual" if m == _cfg(args).model else ""
            _p(f"  • {m}{mark}")
        _p("\ntroque com: betterme config set model <nome>")
    else:
        _fail("Ollama desligado — ligue com: betterme ollama start")


def cmd_models_auto(args) -> None:
    """v3.11.3: escolhe o melhor modelo instalado para cada papel."""
    from .autoselect import run_auto
    if not run_auto(_cfg(args), multi=bool(getattr(args, "multi", False))
                    ).get("ok"):
        raise SystemExit(1)


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="betterme",
        description="◈ Betterme Agent — agente Linux local com Ollama + GUI web",
    )
    parser.add_argument("--version", action="version", version=f"betterme-agent {VERSION}")
    parser.add_argument("--data-dir", help="diretório de dados (padrão: ~/.betterme)")
    parser.add_argument("--mock", action="store_true", help="força modo demonstração (Ollama simulado)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("update", help="atualiza o agente a partir do GitHub")
    p.add_argument("--check", action="store_true",
                   help="apenas verifica se há versão nova (não aplica)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="aplica sem pedir confirmação")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("memory", help="memória de longo prazo do agente")
    msub = p.add_subparsers(dest="memory_cmd", required=True)
    pm = msub.add_parser("import",
                         help="importa fatos para a memória (JSON lista ou "
                              "um fato por linha) — duplicados pulados")
    pm.add_argument("arquivo", help="caminho do arquivo de fatos")
    pm.set_defaults(fn=cmd_memory_import)
    pl = msub.add_parser("list", help="lista os fatos da memória do agente")
    pl.set_defaults(fn=cmd_memory_list)
    pc = msub.add_parser("clear", help="apaga TODOS os fatos da memória (reimporte um pacote limpo depois)")
    pc.add_argument("-y", "--yes", action="store_true", help="não pede confirmação")
    pc.set_defaults(fn=cmd_memory_clear)

    p = sub.add_parser("skills", help="catálogo de skills")
    ssub = p.add_subparsers(dest="skills_cmd", required=True)
    pi = ssub.add_parser("import", help="importa skills: pasta local, .zip, URL git ou owner/repo")
    pi.add_argument("fonte", help="caminho da pasta/zip, URL ou owner/repo")
    pi.set_defaults(fn=cmd_skills_import)
    pap = ssub.add_parser("aprender",
                          help="transforma arquivo/URL/texto em rascunho de skill (M6.5)")
    pap.add_argument("fonte", nargs="+",
                     help="arquivo, URL ou texto para virar skill")
    pap.set_defaults(fn=cmd_skills_aprender)
    ps = ssub.add_parser("scan", help="varre pastas assistidas (ex.: ~/Downloads) e importa skills novas")
    ps.set_defaults(fn=cmd_skills_scan)
    pa = ssub.add_parser("audit",
                         help="audita todas as skills: estrutura, tamanho, "
                              "prompt injection, duplicatas")
    pa.set_defaults(fn=cmd_skills_audit)

    p = sub.add_parser("chat", help="chat interativo no terminal")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("selftest",
                       help="🧪 bateria de aceitação com o LLM real: sem "
                            "recusa, com evidência (pula se Ollama desligado)")
    p.add_argument("--timeout", type=int, default=240,
                   help="segundos máximos por cenário (padrão 240)")
    p.add_argument("--all-models", action="store_true",
                   help="🧪 testa TODOS os modelos instalados e mostra a "
                        "matriz (modelo × cenário) com recomendação")
    p.set_defaults(fn=cmd_selftest)

    p = sub.add_parser("provider", help="provedores LLM externos gratuitos (memória nunca sai)")
    psub = p.add_subparsers(dest="acao", required=True)
    pl = psub.add_parser("list", help="lista provedores gratuitos e o atual")
    pl.set_defaults(acao="list", fn=cmd_provider)
    ps = psub.add_parser("set", help="ativa um provedor (pede a chave com segurança)")
    ps.add_argument("provedor", help="groq|gemini|mistral|openrouter|llm7|zai|cohere")
    ps.add_argument("--model", default="", help="modelo (default do provedor se vazio)")
    ps.add_argument("--key", default="", help="chave (se não passar, pede escondida)")
    ps.set_defaults(acao="set", fn=cmd_provider)
    pt = psub.add_parser("test", help="ping + 1 completion real do provedor ativo")
    pt.set_defaults(acao="test", fn=cmd_provider)
    po = psub.add_parser("off", help="volta ao Ollama local")
    po.set_defaults(acao="off", fn=cmd_provider)
    p = sub.add_parser("varredura",
                       help="varre segredos/dados pessoais antes de expor código (pré-push)")
    p.add_argument("--tudo", action="store_true",
                   help="varre o repo inteiro (default: diff não commitado)")
    p.add_argument("--raiz", default=None,
                   help="raiz do projeto (default: diretório atual)")
    p.set_defaults(fn=cmd_varredura)
    p = sub.add_parser("init",
                       help="cria HERMES.md (instruções duráveis do projeto)")
    p.add_argument("caminho", nargs="?", default=None,
                   help="pasta do projeto (default: diretório atual)")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("autonomia",
                       help="nível de autonomia do agente (cauteloso|padrao|autonomo)")
    p.add_argument("nivel", nargs="?", default=None,
                   help="novo nível (vazio = mostra o atual)")
    p.set_defaults(fn=cmd_autonomia)
    p = sub.add_parser("gerente",
                       help="gerente de código (Claude Code) — opt-in consciente")
    p.add_argument("acao", nargs="?", default="status",
                   help="status|on|off")
    p.add_argument("--yes", action="store_true",
                   help="confirma o aviso de privacidade (necessário p/ on)")
    p.set_defaults(fn=cmd_gerente)
    p = sub.add_parser("telegram",
                       help="canal Telegram: controle e aprovação pelo celular")
    p.add_argument("acao", nargs="?", default="status",
                   help="status|start|stop|chat-id|autorizar")
    p.add_argument("id", nargs="?", default=None,
                   help="chat_id (para autorizar)")
    p.set_defaults(fn=cmd_telegram)
    p = sub.add_parser("whatsapp",
                       help="canal WhatsApp via Playwright — grátis, local, removível")
    p.add_argument("acao", nargs="?", default="status",
                   help="status|setup|start|stop|qr|autorizar|remover")
    p.add_argument("id", nargs="?", default=None,
                   help="número (para autorizar)")
    p.set_defaults(fn=cmd_whatsapp)

    p = sub.add_parser("arena",
                       help="🏟️ roda a MESMA task nos provedores grátis e ranqueia (v4.3.0)")
    p.add_argument("task", nargs="+", help="a task — idêntica para todos os contendores")
    p.add_argument("--n", type=int, default=1,
                   help="rodadas por contendedor (default 1; tempo médio)")
    p.set_defaults(fn=cmd_arena)

    p = sub.add_parser("grafo",
                       help="🗺️ grafo de código: onde está a lógica de X? (v4.4.0)")
    gsub = p.add_subparsers(dest="acao", required=True)
    gb = gsub.add_parser("build", help="constrói o grafo AST do projeto (SQLite no data-dir)")
    gb.add_argument("--raiz", default=None,
                    help="raiz do projeto (default: diretório atual)")
    gq = gsub.add_parser("query", help="busca símbolos por nome (função/classe/método)")
    gq.add_argument("termo", nargs="+", help="nome (ou parte) a buscar")
    gp = gsub.add_parser("path", help="traça o caminho de chamadas A → B")
    gp.add_argument("de", help="símbolo de origem")
    gp.add_argument("para", help="símbolo de destino")
    p.set_defaults(fn=cmd_grafo)

    p = sub.add_parser("revisar",
                       help="🔍 revisa o git diff HEAD (gate único pré-push; v4.5.0)")
    p.add_argument("--raiz", default=None,
                   help="raiz do repo (default: diretório atual)")
    p.set_defaults(fn=cmd_revisar)
    p = sub.add_parser("aprendidos",
                       help="rascunhos de skills/lições esperando sua aprovação")
    pa = p.add_argument("acao", nargs="?", default="list",
                        help="list|aprovar|rejeitar")
    p.add_argument("id", nargs="?", default=None, help="id do rascunho")
    p.set_defaults(fn=cmd_aprendidos)
    p = sub.add_parser("conversas", help="conversas passadas do agente")
    p.add_argument("acao", nargs="?", default="buscar",
                   help="buscar")
    p.add_argument("termo", nargs="*", help="termo a buscar")
    p.set_defaults(fn=cmd_conversas_buscar)
    p = sub.add_parser("rag", help="biblioteca de livros (RAG local): indexa ou consulta")
    p.add_argument("consulta", nargs="?", default="", help="texto a buscar (vazio = reindexar)")
    p.set_defaults(fn=cmd_rag)
    p = sub.add_parser("doctor", help="diagnostica a conexão Ollama↔Python (com geração de teste)")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("email", help="configura contas de e-mail (MCP email_*)")
    p.add_argument("email_action", nargs="?", default="status",
                   choices=["setup", "oauth", "test", "status", "modo"],
                   help="setup = adicionar contas · oauth = Microsoft/Google (2FA) · "
                        "test = validar logins · status = ver · "
                        "modo = envio|leitura por conta")
    p.add_argument("conta", nargs="?", default=None,
                   help="[com 'modo'] id ou e-mail da conta")
    p.add_argument("novo_modo", nargs="?", default=None,
                   help="[com 'modo'] 'envio' libera o envio; 'leitura' volta a somente ver")
    p.set_defaults(fn=cmd_email)

    p = sub.add_parser("agenda", help="agenda Google Calendar — somente leitura (MCP agenda_*)")
    p.add_argument("agenda_action", nargs="?", default="status",
                   choices=["oauth", "test", "status"],
                   help="oauth = conectar conta Google (2FA, device code) · "
                        "test = listar eventos de hoje · status = ver")
    p.set_defaults(fn=cmd_agenda)

    p = sub.add_parser("status", help="status do agente e do Ollama")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("run", help="executa uma tarefa única")
    p.add_argument("task", nargs="+", help="descrição da tarefa")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("daemon", help="roda o daemon em primeiro plano")
    p.set_defaults(fn=cmd_daemon)

    p = sub.add_parser("server", help="sobe a GUI web de controle")
    p.add_argument("--host", help="endereço de escuta (padrão: 127.0.0.1)")
    p.add_argument("--port", type=int, help="porta (padrão: 8080)")
    p.add_argument("--token", help="senha de acesso exigida na GUI/API")
    p.set_defaults(fn=cmd_server)

    p = sub.add_parser("agent", help="controla o agente (ligar/desligar)")
    p.add_argument("action", choices=["start", "stop", "restart", "status"])
    p.set_defaults(fn=cmd_agent)

    p = sub.add_parser("ollama", help="controla o servidor Ollama")
    p.add_argument("action", choices=["status", "start", "stop", "test", "pull", "install"])
    p.add_argument("model", nargs="?", help="modelo para 'pull' (padrão: o da configuração)")
    p.set_defaults(fn=cmd_ollama)

    p = sub.add_parser("tasks", help="lista tarefas da fila e resultados")
    p.set_defaults(fn=cmd_tasks)

    p = sub.add_parser("schedule", help="tarefas agendadas (⏰)")
    p.add_argument("action", choices=["list", "add", "del", "run"])
    p.add_argument("text", nargs="?", help="para 'add': o que o agente deve fazer")
    p.add_argument("when", nargs="?", help="para 'add': quando — ex.: 'diário 08:30', 'seg,qua 14:00', 'a cada 30m'")
    p.add_argument("id", nargs="?", help="para 'del'/'run': id da tarefa")
    p.set_defaults(fn=cmd_schedule)

    p = sub.add_parser("config", help="configuração")
    p.add_argument("action", choices=["show", "set", "edit"])
    p.add_argument("kv", nargs="*", help="para 'set': chave valor")
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser("models", help="lista modelos locais do Ollama")
    msub = p.add_subparsers(dest="models_cmd")
    pa = msub.add_parser("auto",
                         help="✨ auto-atribui o melhor modelo instalado "
                              "para cada papel (chat/orquestrador/revisor/"
                              "executor/claude)")
    pa.add_argument("--multi", action="store_true",
                    help="modelo distinto por papel (padrão: econômico — "
                         "pipeline inteiro herda o chat, zero trocas)")
    pa.set_defaults(fn=cmd_models_auto)
    p.set_defaults(fn=cmd_models)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "fn", None) is None:
        parser.print_help()
        return
    args.fn(args)
