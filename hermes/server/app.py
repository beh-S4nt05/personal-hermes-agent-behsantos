"""Servidor web do Hermes: GUI + API REST de controle.

Endpoints principais:
  GET  /                    página da GUI
  GET  /api/status          status consolidado (agente, ollama, host)
  POST /api/agent/start     liga o agente (daemon)
  POST /api/agent/stop      desliga o agente
  POST /api/agent/restart   reinicia o agente
  POST /api/ollama/start    liga o servidor Ollama
  POST /api/ollama/stop     desliga o servidor Ollama
  GET  /api/logs            últimas linhas do log do agente
  GET  /api/logs/stream     log ao vivo via SSE
  POST /api/chat            conversa com o agente (stream NDJSON de eventos)
  GET  /api/tasks           fila de tarefas + resultados
  POST /api/tasks           enfileira nova tarefa
  POST /api/tasks/clear     limpa o histórico de tarefas concluídas
  GET/POST /api/settings    configurações (modelo, prompt, limites...)
"""

from __future__ import annotations

import json
import re
import time
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context

from ..config import VERSION, Config
from ..daemon import enqueue, list_tasks
from ..manager import DaemonManager, OllamaManager, python_env_check
from ..mcp_client import get_manager
from ..ollama_client import get_client
from ..skills import SkillLoader

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# downloads de modelos em andamento (model -> Event de cancelamento)
ACTIVE_PULLS: dict = {}

# nome de modelo válido para o Ollama: nome[/namespace][:tag] — sem espaços
MODEL_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*(:[A-Za-z0-9._-]+)?$")


def create_app(cfg: Config) -> Flask:
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
    app.config["HERMES_CFG"] = cfg
    agents: dict[str, object] = {}

    # ------------------------------------------------------------- auth
    def protected(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = (app.config["HERMES_CFG"].auth_token or "").strip()
            if token:
                supplied = (
                    request.headers.get("X-Hermes-Token")
                    or request.args.get("token")
                    or (request.get_json(silent=True) or {}).get("token")
                    or ""
                )
                if supplied != token:
                    return jsonify({"ok": False, "msg": "token de acesso inválido"}), 401
            return fn(*args, **kwargs)

        return wrapper

    @app.after_request
    def api_headers(resp):
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
            # CORS: a GUI pode ser servida dentro de iframes/previews com origem
            # opaca (Origin: null); sem estes cabeçalhos o navegador bloqueia a
            # leitura das respostas da API (a página abre, mas os fetch falham).
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Hermes-Token, Authorization"
            resp.headers["Access-Control-Max-Age"] = "86400"
        return resp

    # Responde às pré-checagens CORS (OPTIONS) de qualquer rota /api/*
    @app.route("/api/<path:_rest>", methods=["OPTIONS"])
    def api_preflight(_rest: str):
        return ("", 204)

    # -------------------------------------------------------------- GUI
    @app.get("/")
    def index():
        html = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
        # no-store: depois de atualizar o projeto, o navegador não pode servir
        # a GUI antiga do cache (causa de "atualizei e nada mudou")
        resp = Response(html, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp

    # ----------------------------------------------------------- status
    @app.get("/api/status")
    @protected
    def status():
        mgr = DaemonManager(cfg)
        agent = mgr.status()
        ollama = OllamaManager(cfg).status()
        return jsonify(
            {
                "version": VERSION,
                "mock": cfg.mock,
                "agent": agent,
                "ollama": ollama,
                "mcp": get_manager(cfg).status(),
                "skills": [s["name"] for s in SkillLoader(cfg).scan()],
                "config": {
                    "model": cfg.model,
                    "max_steps": cfg.max_steps,
                    "sandbox": cfg.sandbox,
                    "num_ctx": cfg.num_ctx,
                    "cmd_timeout": cfg.cmd_timeout,
                    "system_prompt_extra": cfg.system_prompt_extra,
                },
                "data_dir": str(cfg.data_dir),
                "auth": bool((cfg.auth_token or "").strip()),
            }
        )

    # ------------------------------------------------- agente on/off
    @app.post("/api/agent/<action>")
    @protected
    def agent_action(action: str):
        if action not in ("start", "stop", "restart"):
            return jsonify({"ok": False, "msg": "ação inválida"}), 400
        result = getattr(DaemonManager(cfg), action)()
        return jsonify(result), (200 if result["ok"] else 409)

    # ------------------------------------------------- ollama on/off
    @app.post("/api/ollama/<action>")
    @protected
    def ollama_action(action: str):
        if action not in ("start", "stop"):
            return jsonify({"ok": False, "msg": "ação inválida"}), 400
        result = getattr(OllamaManager(cfg), action)()
        return jsonify(result), (200 if result["ok"] else 409)

    # ------------------------------------------------ ollama: visão completa
    @app.get("/api/ollama/diagnose")
    @protected
    def ollama_diagnose():
        deep = request.args.get("deep", "0") in ("1", "true", "yes")
        return jsonify(OllamaManager(cfg).diagnose(deep=deep))

    @app.post("/api/ollama/test")
    @protected
    def ollama_test():
        """Validação completa da conexão, incluindo geração de teste real."""
        return jsonify(OllamaManager(cfg).diagnose(deep=True))

    @app.get("/api/ollama/models")
    @protected
    def ollama_models():
        if cfg.mock:
            return jsonify({
                "models": [
                    {"name": "hermes3:8b", "size_gb": 4.7, "modified": "—",
                     "current": cfg.model == "hermes3:8b"},
                    {"name": "hermes3:3b", "size_gb": 2.0, "modified": "—",
                     "current": cfg.model == "hermes3:3b"},
                ],
                "loaded": [],
                "simulated": True,
            })
        client = OllamaManager(cfg).client
        models = [
            {
                "name": m.get("name", "?"),
                "size_gb": round((m.get("size") or 0) / 1e9, 1),
                "modified": str(m.get("modified_at", ""))[:10],
                "current": m.get("name") == cfg.model,
            }
            for m in client.model_details()
        ]
        loaded = [
            {
                "name": m.get("name", "?"),
                "size_vram_gb": round((m.get("size_vram") or 0) / 1e9, 1),
                "expires": str(m.get("expires_at", "")),
            }
            for m in client.ps()
        ]
        return jsonify({"models": models, "loaded": loaded})

    @app.post("/api/ollama/pull")
    @protected
    def ollama_pull():
        """Baixa um modelo streamando o progresso (NDJSON)."""
        payload = request.get_json(silent=True) or {}
        model = str(payload.get("model", "")).strip()
        if not model or not MODEL_RE.fullmatch(model):
            return jsonify({"ok": False, "msg": "nome de modelo inválido (use nome:tag)"}), 400

        import queue
        import threading

        q: "queue.Queue[dict | None]" = queue.Queue()

        def on_progress(data: dict):
            total, done = data.get("total"), data.get("completed")
            pct = round(done / total * 100, 1) if total else None
            q.put({"type": "progress", "status": data.get("status", ""), "pct": pct})

        import threading as _th

        pull_cancel = _th.Event()
        ACTIVE_PULLS[model] = pull_cancel

        def worker():
            try:
                get_client(cfg).pull(model, on_progress, cancel=pull_cancel)
                if pull_cancel.is_set():
                    q.put({"type": "error", "msg": f"download de {model} cancelado"})
                else:
                    q.put({"type": "done", "msg": f"modelo {model} instalado"})
            except Exception as exc:  # noqa: BLE001
                q.put({"type": "error", "msg": str(exc)[:300]})
            finally:
                ACTIVE_PULLS.pop(model, None)
                q.put(None)

        def gen():
            threading.Thread(target=worker, daemon=True).start()
            while True:
                item = q.get()
                if item is None:
                    break
                yield json.dumps(item, ensure_ascii=False) + "\n"

        resp = Response(stream_with_context(gen()), mimetype="application/x-ndjson")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/ollama/delete")
    @protected
    def ollama_delete():
        payload = request.get_json(silent=True) or {}
        model = str(payload.get("model", "")).strip()
        if not model:
            return jsonify({"ok": False, "msg": "informe o modelo"}), 400
        if cfg.mock:
            return jsonify({"ok": True, "msg": f"(simulado) modelo {model} removido"})
        if model == cfg.model:
            return jsonify({"ok": False,
                            "msg": "este é o modelo em uso — troque o modelo antes de remover"}), 409
        try:
            OllamaManager(cfg).client.delete_model(model)
            return jsonify({"ok": True, "msg": f"modelo {model} removido"})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "msg": str(exc)[:200]}), 500

    @app.post("/api/ollama/restart")
    @protected
    def ollama_restart():
        result = OllamaManager(cfg).restart()
        return jsonify(result), (200 if result["ok"] else 409)

    @app.post("/api/ollama/boot")
    @protected
    def ollama_boot():
        """Liga/desliga a inicialização do Ollama junto do sistema."""
        payload = request.get_json(silent=True) or {}
        result = OllamaManager(cfg).set_boot(bool(payload.get("enable")))
        return jsonify(result), (200 if result["ok"] else 400)

    # ------------------------------------------------------------ MCP
    @app.get("/api/mcp")
    @protected
    def mcp_status():
        return jsonify({"servers": get_manager(cfg).status()})

    @app.post("/api/mcp/start")
    @protected
    def mcp_start():
        get_manager(cfg).start_all()
        servers = get_manager(cfg).status()
        ok = all(s["state"] == "ativo" for s in servers) if servers else False
        msg = ", ".join(f"{s['name']}={s['state']}" for s in servers) or "nenhum servidor configurado"
        return jsonify({"ok": ok, "msg": f"servidores MCP: {msg}", "servers": servers}), (200 if ok else 409)

    @app.post("/api/mcp/restart")
    @protected
    def mcp_restart():
        get_manager(cfg).restart()
        return mcp_start()

    # -------------------------------------------------------- skills
    @app.get("/api/skills")
    @protected
    def skills_list():
        return jsonify({"skills": SkillLoader(cfg).scan()})

    @app.get("/api/skills/content")
    @protected
    def skills_content():
        path = request.args.get("path", "")
        try:
            return jsonify({"ok": True, "content": SkillLoader(cfg).read_skill_md(path)})
        except (PermissionError, FileNotFoundError) as exc:
            return jsonify({"ok": False, "msg": str(exc)}), 400

    @app.post("/api/skills/toggle")
    @protected
    def skills_toggle():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        enabled = bool(payload.get("enabled", True))
        if not name:
            return jsonify({"ok": False, "msg": "informe o nome da skill"}), 400
        SkillLoader(cfg).toggle(name, enabled)
        return jsonify({"ok": True, "msg": f"skill '{name}' {'habilitada' if enabled else 'desabilitada'}"})

    @app.post("/api/skills/install")
    @protected
    def skills_install():
        payload = request.get_json(silent=True) or {}
        repo = str(payload.get("repo", "")).strip()
        subpath = str(payload.get("subpath", "")).strip()
        if not repo:
            return jsonify({"ok": False, "msg": "informe owner/repo ou a URL do GitHub"}), 400
        result = SkillLoader(cfg).install_from_github(repo, subpath)
        return jsonify(result), (200 if result.get("ok") else 400)

    # -------------------------------------------------------------- log
    @app.get("/api/logs")
    @protected
    def logs():
        try:
            lines = int(request.args.get("lines", 300))
        except ValueError:
            lines = 300
        lines = max(10, min(lines, 2000))
        path = cfg.logfile
        text = ""
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            text = "\n".join(content[-lines:])
        return jsonify({"lines": text})

    @app.post("/api/logs/clear")
    @protected
    def logs_clear():
        cfg.logfile.parent.mkdir(parents=True, exist_ok=True)
        cfg.logfile.write_text("", encoding="utf-8")
        return jsonify({"ok": True})

    @app.get("/api/logs/stream")
    @protected
    def logs_stream():
        def generate():
            path = cfg.logfile
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8"):  # garante que existe
                pass
            with open(path, encoding="utf-8", errors="replace") as fh:
                fh.seek(0, 2)  # começa do fim (ao vivo)
                idle = 0
                while True:
                    line = fh.readline()
                    if line:
                        idle = 0
                        yield f"data: {json.dumps({'line': line.rstrip(chr(10))})}\n\n"
                    else:
                        idle += 1
                        if idle % 4 == 0:
                            yield ": keepalive\n\n"
                        time.sleep(0.35)

        resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    # ------------------------------------------------------------- chat
    @app.post("/api/chat")
    @protected
    def chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        history = payload.get("history") or []
        chat_agent = str(payload.get("agent") or "hermes")
        if chat_agent not in ("hermes", "claude"):
            chat_agent = "hermes"
        if not message:
            return jsonify({"ok": False, "msg": "mensagem vazia"}), 400

        clean_history = [
            {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
            for m in history
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
        ][-20:]

        # ---- sessão persistida (histórico recuperável a qualquer momento) ----
        from ..conversations import SESSION_ID_RE, ConversationStore

        store = ConversationStore(cfg)
        session_id = str(payload.get("session_id") or "").strip()
        if not SESSION_ID_RE.fullmatch(session_id):
            session_id = ""  # id inválido/ausente -> nova conversa
        new_session = not session_id
        if new_session:
            session_id = store.new_session()["id"]
        # a mensagem do usuário é gravada ANTES da geração: nunca se perde
        store.append(session_id, "user", message)
        store.set_current(session_id)

        client = get_client(cfg)
        if chat_agent == "hermes" and not client.is_running():
            def unavailable():
                yield json.dumps({
                    "type": "error",
                    "message": (
                        "O servidor Ollama está desligado. Ligue-o na aba Ollama "
                        "(ou: hermes ollama start) e tente de novo. Dica: ative "
                        "«ligar o Ollama automaticamente» na aba Ollama para o "
                        "agente subir o servidor sozinho."
                    ),
                }, ensure_ascii=False) + "\n"
                yield json.dumps({"type": "done", "message": ""}, ensure_ascii=False) + "\n"
            return Response(stream_with_context(unavailable()), mimetype="application/x-ndjson")

        from ..agent import Agent

        agent = agents.setdefault("chat", Agent(cfg))

        import queue
        import threading

        q: "queue.Queue[dict | None]" = queue.Queue()
        cancel = threading.Event()
        result = {"final": "", "duration_s": None, "tokens": 0, "steps": 0}

        def collect(e: dict) -> None:
            """Publica eventos na fila e coleta estatísticas da geração."""
            if cancel.is_set():
                return
            if e.get("type") == "token":
                result["tokens"] += 1
            elif e.get("type") == "step":
                result["steps"] = max(result["steps"], int(e.get("step", 0)))
            q.put(e)

        def worker():
            """A 'promise' da geração: roda em thread e publica eventos na fila."""
            t0 = time.time()
            try:
                if chat_agent == "claude":
                    from ..claude_agent import run_claude
                    result["final"] = run_claude(cfg, message, history=clean_history,
                                                 on_event=collect, cancel=cancel)
                else:
                    result["final"] = agent.run(
                        clean_history + [{"role": "user", "content": message}],
                        on_event=collect,
                        cancel=cancel,
                    )
            except Exception as exc:  # noqa: BLE001
                if not cancel.is_set():
                    q.put({"type": "error",
                           "message": f"falha interna: {exc.__class__.__name__}: {exc}"})
            finally:
                result["duration_s"] = round(time.time() - t0, 1)
                # estatísticas da resposta (tempo, tokens, passos) para a GUI
                if not cancel.is_set():
                    q.put({
                        "type": "stats",
                        "duration_s": result["duration_s"],
                        "tokens": result["tokens"],
                        "steps": result["steps"],
                    })
                q.put(None)

        def generate():
            # informa ao front em qual sessão esta conversa vive
            yield json.dumps({"type": "session", "id": session_id},
                             ensure_ascii=False) + "\n"
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            try:
                while True:
                    try:
                        item = q.get(timeout=5.0)
                    except queue.Empty:
                        if not t.is_alive():
                            break
                        # keepalive enquanto a IA "pensa" (ex.: modelo carregando
                        # na memória pela primeira vez) — mantém a conexão viva
                        yield json.dumps({"type": "ping", "ts": time.time()},
                                         ensure_ascii=False) + "\n"
                        continue
                    if item is None:
                        break
                    yield json.dumps(item, ensure_ascii=False) + "\n"
            except GeneratorExit:
                # navegador fechou/abortou a requisição: cancela a geração
                cancel.set()
                raise
            finally:
                cancel.set()  # nunca deixa thread órfã gerando sozinha
                # persiste a resposta (mesmo parcial) na sessão, com o tempo
                try:
                    if result["final"]:
                        store.append(session_id, "assistant", result["final"],
                                     dur=result["duration_s"],
                                     agent=(chat_agent if chat_agent == "claude" else None))
                except OSError:
                    pass

        resp = Response(stream_with_context(generate()), mimetype="application/x-ndjson")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # -------------------------------------------------- conversas (histórico)
    # --------------------------------------------------------- ferramentas
    @app.get("/api/tools")
    @protected
    def tools_catalog():
        """Catálogo das funções padrão do agente (ferramentas nativas + MCP)."""
        from ..tools import TOOLS

        mcp_tools = []
        try:
            mcp_tools = [
                {"name": t["function"]["name"],
                 "description": t["function"]["description"].splitlines()[0][:200]}
                for t in get_manager(cfg).openai_tools()
            ]
        except Exception:
            pass
        return jsonify({
            "tools": [
                {"name": t["function"]["name"],
                 "description": t["function"]["description"]}
                for t in TOOLS
            ],
            "mcp": mcp_tools,
        })

    @app.post("/api/tools/run")
    @protected
    def tools_run():
        """Terminal rápido — mesma segurança do agente (denylist + timeout)."""
        from ..tools import execute_tool

        payload = request.get_json(silent=True) or {}
        command = str(payload.get("command", "")).strip()
        if not command:
            return jsonify({"ok": False, "output": "comando vazio"}), 400
        res = execute_tool("run_command", {"command": command, "timeout": 120}, cfg)
        return jsonify(res)

    @app.post("/api/tools/list_dir")
    @protected
    def tools_list_dir():
        from ..tools import execute_tool

        payload = request.get_json(silent=True) or {}
        return jsonify(execute_tool("list_dir", {"path": payload.get("path") or "."}, cfg))

    @app.post("/api/tools/read_file")
    @protected
    def tools_read_file():
        from ..tools import execute_tool

        payload = request.get_json(silent=True) or {}
        return jsonify(execute_tool("read_file", {"path": payload.get("path", "")}, cfg))

    @app.post("/api/tools/write_file")
    @protected
    def tools_write_file():
        from ..tools import execute_tool

        payload = request.get_json(silent=True) or {}
        path = str(payload.get("path", "")).strip()
        if not path:
            return jsonify({"ok": False, "output": "informe o caminho do arquivo"}), 400
        return jsonify(execute_tool(
            "write_file", {"path": path, "content": str(payload.get("content", ""))}, cfg))

    @app.post("/api/tools/sys_info")
    @protected
    def tools_sys_info():
        from ..tools import execute_tool

        return jsonify(execute_tool("sys_info", {}, cfg))

    # ------------------------------------------- catálogo de modelos (LMMs)
    @app.get("/api/ollama/library")
    @protected
    def ollama_library():
        """Busca modelos: curadoria popular + biblioteca oficial (ollama.com)."""
        import html as html_mod
        import re as re_mod

        import requests as rq

        q = str(request.args.get("q", "")).strip().lower()
        import unicodedata as _ud

        def _flat(s: str) -> str:
            return "".join(c for c in _ud.normalize("NFD", s)
                           if _ud.category(c) != "Mn").lower()
        popular = [
            # ── leves (≤7B) — recomendados p/ máquinas com ~10 GB de RAM ──
            {"name": "llama3.2:3b", "desc": "Meta 3B — excelente em português: organizar, categorizar e planejar (2.0 GB)"},
            {"name": "deepseek-r1:7b", "desc": "🧮 raciocínio lógico passo a passo — topo da faixa ≤7B (4.7 GB)"},
            {"name": "deepseek-r1:1.5b", "desc": "🧮 raciocínio lógico ultraleve e rápido (1.1 GB)"},
            {"name": "qwen2.5-coder:7b", "desc": "💻 melhor em código na faixa ≤7B: gerar, depurar e explicar (4.7 GB)"},
            {"name": "qwen2.5-coder:1.5b", "desc": "💻 scripts Python/Bash rapidíssimos (1 GB)"},
            {"name": "phi3:3.8b", "desc": "🧮 Microsoft — matemática e lógica estáveis (2.2 GB)"},
            {"name": "phi4-mini:3.8b", "desc": "📋 Microsoft — raciocínio, planejamento e instruções (2.5 GB)"},
            {"name": "granite4.2:3b", "desc": "📅 IBM — estruturação de dados e rotinas (2.2 GB)"},
            {"name": "llama3.2:1b", "desc": "Meta 1B — o mais leve p/ tarefas simples (1.3 GB)"},
            # ── gerais ──
            {"name": "hermes3", "desc": "Nous Research — conversacional/agente (3B/8B/70B), o padrão do Hermes"},
            {"name": "qwen2.5", "desc": "Alibaba — forte em código e raciocínio (0.5B a 72B)"},
            {"name": "qwen2.5-coder", "desc": "especialista em programação (0.5B a 32B)"},
            {"name": "gemma3", "desc": "Google — moderno e eficiente (1B a 27B), com visão"},
            {"name": "deepseek-r1", "desc": "raciocínio passo a passo (1.5B a 671B)"},
            {"name": "mistral", "desc": "Mistral AI — leve e equilibrado (7B)"},
            {"name": "phi4", "desc": "Microsoft — 14B compacto com bom raciocínio"},
            {"name": "llava", "desc": "entende imagens (7B)"},
            {"name": "tinyllama", "desc": "1.1B — mínimo, roda em qualquer máquina"},
            {"name": "nomic-embed-text", "desc": "embeddings p/ busca semântica (leve)"},
            {"name": "codellama", "desc": "Meta — código (7B/13B/70B)"},
        ]
        models = [dict(m) for m in popular
                  if (not q) or q in m["name"] or q in _flat(m["desc"])]
        source = "curadoria"
        if not cfg.mock:
            try:
                r = rq.get("https://ollama.com/search",
                           params={"q": q} if q else {}, timeout=8,
                           headers={"User-Agent": "hermes-agent"})
                r.raise_for_status()
                known = {m["name"] for m in models}
                for m in re_mod.finditer(
                        r'href="/library/([a-z0-9._-]+)"(.*?)</li>', r.text, re_mod.S):
                    name, chunk = m.group(1), m.group(2)
                    if name in known:
                        continue
                    known.add(name)
                    dm = re_mod.search(r"<p[^>]*>\s*(.*?)\s*</p>", chunk, re_mod.S)
                    desc = re_mod.sub(r"<[^>]+>", "", dm.group(1)) if dm else ""
                    desc = html_mod.unescape(desc)[:160]
                    item = {"name": name, "desc": desc or "—"}
                    caps = re_mod.findall(
                        r'bg-indigo-50[^>]*">\s*([a-z]+)\s*</span>', chunk)
                    sizes = re_mod.findall(
                        r'bg-\[#ddf4ff\][^>]*">\s*(\d+(?:\.\d+)?[bm])\s*</span>', chunk)
                    if caps:
                        item["caps"] = "·".join(caps[:3])
                    if sizes:
                        item["sizes"] = "·".join(sizes[:6])
                    models.append(item)
                if len(models) > len(popular):
                    source = "ollama.com"
            except Exception:
                pass
        if q:
            models.sort(key=lambda m: 0 if m["name"] == q else 1)
        return jsonify({"models": models[:40], "source": source})

    @app.post("/api/ollama/pull/cancel")
    @protected
    def ollama_pull_cancel():
        payload = request.get_json(silent=True) or {}
        model = str(payload.get("model", "")).strip()
        ev = ACTIVE_PULLS.get(model)
        if ev is None:
            return jsonify({"ok": False, "msg": "nenhum download ativo com esse nome"}), 404
        ev.set()
        return jsonify({"ok": True, "msg": f"cancelando download de {model}…"})

    @app.get("/api/conversations")
    @protected
    def conversations_list():
        from ..conversations import ConversationStore

        store = ConversationStore(cfg)
        return jsonify({"sessions": store.list(), "current": store.get_current()})

    @app.get("/api/conversations/<sid>")
    @protected
    def conversations_get(sid: str):
        from ..conversations import ConversationStore

        session = ConversationStore(cfg).load(sid)
        if not session:
            return jsonify({"ok": False, "msg": "conversa não encontrada"}), 404
        return jsonify({"ok": True, "session": session})

    @app.get("/api/conversations/search")
    @protected
    def conversations_search():
        from ..conversations import ConversationStore

        query = str(request.args.get("q", ""))
        return jsonify({"ok": True,
                        "results": ConversationStore(cfg).search(query)})

    @app.post("/api/conversations/delete")
    @protected
    def conversations_delete():
        from ..conversations import ConversationStore

        payload = request.get_json(silent=True) or {}
        sid = str(payload.get("id", ""))
        store = ConversationStore(cfg)
        if not store.delete(sid):
            return jsonify({"ok": False, "msg": "conversa não encontrada"}), 404
        if store.get_current() == sid:
            store.set_current(None)
        return jsonify({"ok": True, "msg": "conversa removida"})

    @app.post("/api/conversations/current")
    @protected
    def conversations_current():
        from ..conversations import ConversationStore

        payload = request.get_json(silent=True) or {}
        sid = str(payload.get("id") or "")
        store = ConversationStore(cfg)
        if sid and not store.load(sid):
            return jsonify({"ok": False, "msg": "conversa não encontrada"}), 404
        store.set_current(sid or None)
        return jsonify({"ok": True})

    # ---------------------------------------------------------- tarefas
    @app.get("/api/tasks")
    @protected
    def tasks_get():
        return jsonify(list_tasks(cfg))

    @app.post("/api/tasks")
    @protected
    def tasks_post():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("input", "")).strip()
        if not text:
            return jsonify({"ok": False, "msg": "descrição da tarefa vazia"}), 400
        task = enqueue(cfg, text)
        agent_running = DaemonManager(cfg).status()["running"]
        return jsonify({
            "ok": True,
            "task": task,
            "agent_running": agent_running,
            "msg": ("tarefa enfileirada — o agente vai pegar em instantes" if agent_running
                    else "tarefa enfileirada, mas o agente está DESLIGADO — ligue-o no Painel"),
        })

    @app.post("/api/tasks/clear")
    @protected
    def tasks_clear():
        removed = 0
        for f in cfg.done_dir.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        return jsonify({"ok": True, "msg": f"{removed} resultado(s) removido(s)"})

    # ------------------------------------------------------- agendamentos
    @app.get("/api/schedules")
    @protected
    def schedules_list():
        from ..scheduler import ScheduleStore

        return jsonify({"schedules": ScheduleStore(cfg).public_list()})

    @app.post("/api/schedules")
    @protected
    def schedules_create():
        from ..scheduler import ScheduleStore, human_schedule, parse_schedule

        payload = request.get_json(silent=True) or {}
        input_text = str(payload.get("input", "")).strip()
        when = str(payload.get("when", "")).strip()
        if not input_text:
            return jsonify({"ok": False, "msg": "descreva o que o agente deve fazer"}), 400
        try:
            spec = parse_schedule(when)
        except ValueError as exc:
            return jsonify({"ok": False, "msg": str(exc)}), 400
        sched_agent = str(payload.get("agent") or "hermes")
        if sched_agent not in ("hermes", "claude"):
            sched_agent = "hermes"
        entry = ScheduleStore(cfg).create(input_text, spec, agent=sched_agent)
        return jsonify({
            "ok": True,
            "msg": f"tarefa agendada: {human_schedule(spec)}",
            "schedule": entry["id"],
        })

    @app.post("/api/schedules/toggle")
    @protected
    def schedules_toggle():
        from ..scheduler import ScheduleStore

        payload = request.get_json(silent=True) or {}
        store = ScheduleStore(cfg)
        entry = store.load(str(payload.get("id", "")))
        if not entry:
            return jsonify({"ok": False, "msg": "tarefa não encontrada"}), 404
        entry["enabled"] = bool(payload.get("enabled", not entry.get("enabled")))
        store.save(entry)
        return jsonify({"ok": True,
                        "msg": f"agendamento {'ativado' if entry['enabled'] else 'pausado'}"})

    @app.post("/api/schedules/delete")
    @protected
    def schedules_delete():
        from ..scheduler import ScheduleStore

        payload = request.get_json(silent=True) or {}
        if not ScheduleStore(cfg).delete(str(payload.get("id", ""))):
            return jsonify({"ok": False, "msg": "tarefa não encontrada"}), 404
        return jsonify({"ok": True, "msg": "agendamento removido"})

    @app.post("/api/schedules/run")
    @protected
    def schedules_run():
        payload = request.get_json(silent=True) or {}
        sched = app.config.get("HERMES_SCHEDULER")
        if sched is None:
            return jsonify({"ok": False, "msg": "agendador não está ativo"}), 409
        result = sched.run_now(str(payload.get("id", "")))
        return jsonify(result), (200 if result["ok"] else 404)

    @app.get("/api/schedules/live")
    @protected
    def schedules_live():
        from ..scheduler import live_status

        buf = live_status(str(request.args.get("id", "")))
        if buf is None:
            return jsonify({"ok": False,
                            "msg": "sem dados ao vivo (tarefa nunca rodou neste server)"}), 404
        return jsonify({"ok": True, "live": buf})

    # ------------------------------------------------------------- memória
    @app.get("/api/memory")
    @protected
    def memory_list():
        from ..memory import MemoryStore

        return jsonify({"facts": MemoryStore(cfg).list_all()})

    @app.post("/api/memory")
    @protected
    def memory_add():
        from ..memory import MemoryStore

        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return jsonify({"ok": False, "msg": "fato vazio"}), 400
        try:
            fact = MemoryStore(cfg).add(text)
        except ValueError as exc:
            return jsonify({"ok": False, "msg": str(exc)}), 400
        return jsonify({"ok": True, "msg": "lembrado!", "fact": fact})

    @app.post("/api/memory/update")
    @protected
    def memory_update():
        from ..memory import MemoryStore

        payload = request.get_json(silent=True) or {}
        fact = MemoryStore(cfg).update(str(payload.get("id", "")),
                                       str(payload.get("text", "")))
        if not fact:
            return jsonify({"ok": False, "msg": "fato não encontrado"}), 404
        return jsonify({"ok": True, "msg": "fato atualizado", "fact": fact})

    @app.post("/api/memory/delete")
    @protected
    def memory_delete():
        from ..memory import MemoryStore

        payload = request.get_json(silent=True) or {}
        if not MemoryStore(cfg).delete(str(payload.get("id", ""))):
            return jsonify({"ok": False, "msg": "fato não encontrado"}), 404
        return jsonify({"ok": True, "msg": "fato apagado"})

    # ------------------------------------------------------ configuração
    @app.get("/api/settings")
    @protected
    def settings_get():
        return jsonify({"ok": True, "settings": cfg.as_dict(), "path": str(cfg.path)})

    @app.post("/api/settings")
    @protected
    def settings_post():
        payload = request.get_json(silent=True) or {}
        allowed = {"model", "system_prompt_extra", "max_steps", "num_ctx",
                   "cmd_timeout", "sandbox", "confirm_dangerous", "temperature", "auth_token",
                   "ollama_url", "auto_start_ollama", "claude_use_ollama", "claude_model"}
        changes = {k: v for k, v in payload.items() if k in allowed}
        if not changes:
            return jsonify({"ok": False, "msg": "nada para alterar"}), 400
        if "model" in changes:
            model = str(changes["model"]).strip()
            if not MODEL_RE.fullmatch(model):
                return jsonify({
                    "ok": False,
                    "msg": f"nome de modelo inválido: '{model}' — use o formato nome:tag "
                           "(ex.: hermes3:8b), sem espaços ou caracteres especiais",
                }), 400
        if "ollama_url" in changes:
            url = str(changes["ollama_url"]).strip().rstrip("/")
            if not url.startswith(("http://", "https://")):
                return jsonify({"ok": False,
                                "msg": "endereço inválido — use http://host:porta"}), 400
            changes["ollama_url"] = url
        if "claude_model" in changes:
            cm = str(changes["claude_model"]).strip()
            if cm and not MODEL_RE.fullmatch(cm):
                return jsonify({"ok": False,
                                "msg": f"modelo inválido para o Claude Code: '{cm}'"}), 400
            changes["claude_model"] = cm
        cfg.update(changes)
        agents.clear()  # próximo chat usa a nova configuração
        return jsonify({"ok": True, "msg": f"configuração salva em {cfg.path}", "changes": changes})

    return app


def serve(cfg: Config, host: str, port: int) -> None:
    app = create_app(cfg)
    if cfg.mock:
        print("\n" + "!" * 64)
        print("⚠  MODO DEMONSTRAÇÃO — IA SIMULADA (HERMES_MOCK=1 ou --mock)")
        print("    Este NÃO é o modo de uso real. Encerre (Ctrl+C) e rode:")
        print("        hermes server")
        print("!" * 64)
    mock_note = " [MODO DEMONSTRAÇÃO — Ollama simulado]" if cfg.mock else ""
    auth_note = " 🔒 com token" if (cfg.auth_token or "").strip() else ""
    print(f"\n◈ Hermes Agent GUI v{VERSION}{mock_note}{auth_note}")
    print(f"  ➜ painel: http://{host}:{port}")
    print(f"  ➜ dados : {cfg.data_dir}")
    print(f"  ➜ config: {cfg.path}")

    # ---- auto-diagnóstico: falhas óbvias aparecem AQUI, no início ----
    env = python_env_check()
    print(f"  {'✔' if env['ok'] else '✖'} {env['name']}: {env['detail']}")
    if not cfg.mock:
        diag = OllamaManager(cfg).diagnose(deep=False)
        for s in diag["steps"][1:]:  # ambiente python já foi mostrado acima
            mark = "✔" if s["ok"] else "✖"
            print(f"  {mark} ollama: {s['name']} — {s['detail']}")
        try:
            for m in get_manager(cfg).status():
                if m["state"] == "erro":
                    print(f"  ✖ mcp: {m['name']} — {m['error']}")
        except Exception:
            pass
        if not diag["ok"]:
            print("  ⚠ corrija os itens ✖ acima — comandos úteis:")
            print("     sudo systemctl start ollama          # ligar o serviço")
            print(f"     ollama pull {cfg.model:<20}      # baixar o modelo")
            print("     hermes config set model <nome>        # usar um modelo de `ollama list`")
    print("  ➜ CTRL+C para encerrar\n")

    # agendador de tarefas (mantenha o server rodando para os horários dispararem)
    from ..scheduler import Scheduler

    sched = Scheduler(cfg)
    sched.start()
    app.config["HERMES_SCHEDULER"] = sched
    ativos = sum(1 for s in sched.store.public_list() if s["enabled"])
    print(f"  ⏰ agendador ativo — {ativos} tarefa(s) agendada(s) "
          f"(verifica a cada 15s)")

    app.run(host=host, port=port, threaded=True, debug=False)
