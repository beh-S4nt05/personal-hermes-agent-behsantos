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

# nome de modelo válido para o Ollama: nome[/namespace][:tag] — sem espaços
MODEL_RE = re.compile(r"^[A-Za-z0-9._]+(/[A-Za-z0-9._-]+)?(:[A-Za-z0-9._-]+)?$")


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

        if cfg.mock:
            def fake():
                for pct in range(0, 101, 10):
                    yield json.dumps({"type": "progress", "status": "baixando (simulado)",
                                      "pct": pct}, ensure_ascii=False) + "\n"
                    time.sleep(0.12)
                yield json.dumps({"type": "done", "msg": f"modelo {model} disponível (simulado)"},
                                 ensure_ascii=False) + "\n"
            return Response(stream_with_context(fake()), mimetype="application/x-ndjson")

        import queue
        import threading

        q: "queue.Queue[dict | None]" = queue.Queue()

        def on_progress(data: dict):
            total, done = data.get("total"), data.get("completed")
            pct = round(done / total * 100, 1) if total else None
            q.put({"type": "progress", "status": data.get("status", ""), "pct": pct})

        def worker():
            try:
                OllamaManager(cfg).client.pull(model, on_progress)
                q.put({"type": "done", "msg": f"modelo {model} instalado"})
            except Exception as exc:  # noqa: BLE001
                q.put({"type": "error", "msg": str(exc)[:300]})
            finally:
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
        if not message:
            return jsonify({"ok": False, "msg": "mensagem vazia"}), 400

        clean_history = [
            {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
            for m in history
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
        ][-20:]

        client = get_client(cfg)
        if not client.is_running():
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
        result = {"final": ""}

        def worker():
            try:
                result["final"] = agent.run(
                    clean_history + [{"role": "user", "content": message}],
                    on_event=q.put,
                )
            except Exception as exc:  # noqa: BLE001
                q.put({"type": "error",
                       "message": f"falha interna: {exc.__class__.__name__}: {exc}"})
            finally:
                q.put(None)

        def generate():
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            while True:
                item = q.get()
                if item is None:
                    break
                yield json.dumps(item, ensure_ascii=False) + "\n"
            # registra a conversa em data/conversations/
            try:
                day = time.strftime("%Y-%m-%d")
                path = cfg.conversations_dir / f"chat-{day}.jsonl"
                cfg.conversations_dir.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": time.time(), "role": "user", "content": message}, ensure_ascii=False) + "\n")
                    fh.write(json.dumps({"ts": time.time(), "role": "assistant", "content": result["final"]}, ensure_ascii=False) + "\n")
            except OSError:
                pass

        resp = Response(stream_with_context(generate()), mimetype="application/x-ndjson")
        resp.headers["Cache-Control"] = "no-store"
        return resp

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
                   "ollama_url", "auto_start_ollama"}
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
        cfg.update(changes)
        agents.clear()  # próximo chat usa a nova configuração
        return jsonify({"ok": True, "msg": f"configuração salva em {cfg.path}", "changes": changes})

    return app


def serve(cfg: Config, host: str, port: int) -> None:
    app = create_app(cfg)
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
    app.run(host=host, port=port, threaded=True, debug=False)
