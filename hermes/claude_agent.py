"""Claude Code como segundo agente da GUI.

O usuário já pode ter o Claude Code instalado (CLI `claude`, configurado para
rodar sobre o Ollama ou sobre a API da Anthropic). Este módulo executa

    claude -p "<prompt>" --output-format stream-json --verbose

no workspace do agente e traduz o JSON-por-linha dele para os mesmos eventos
do chat (token, tool_start/tool_end, done, error) — assim a GUI, o histórico
de conversas, as tarefas agendadas e a visão "ao vivo" funcionam igual.

No modo demonstração (mock), simula uma resposta para a GUI continuar usável.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time

CLAUDE_TIMEOUT_S = 900  # teto de 15 min por execução

_CLAUDE_INSTALL_HINT = (
    "Claude Code não encontrado neste computador. Instale com:\n"
    "  npm install -g @anthropic-ai/claude-code\n"
    "Depois configure as variáveis (ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN)\n"
    "e reinicie o `hermes server` no mesmo terminal onde elas estão ativas."
)


def claude_path() -> str | None:
    """Caminho do binário `claude` (None se não estiver instalado)."""
    return shutil.which("claude")


def _build_prompt(message: str, history: list[dict]) -> str:
    """Serializa a conversa anterior + a mensagem nova em um único prompt."""
    if not history:
        return message
    lines = ["Conversa anterior (contexto):"]
    for m in history[-10:]:
        quem = "Usuário" if m.get("role") == "user" else "Assistente"
        lines.append(f"{quem}: {str(m.get('content', ''))[:800]}")
    lines.append("")
    lines.append("Agora responda, em português do Brasil, à nova mensagem:")
    lines.append(f"Usuário: {message}")
    return "\n".join(lines)


def _simulate(message: str, ev, cancel) -> str:
    """Resposta simulada (modo demonstração) — mesmo formato de eventos."""
    if cancel is not None and cancel.is_set():
        ev({"type": "cancelled", "message": ""})
        return ""
    ev({"type": "step", "step": 1})
    texto = (
        f"[Claude Code — simulado na demonstração] Recebi: “{message[:120]}”. "
        "No modo real eu rodaria a CLI `claude` com todas as funções padrão "
        "do Claude Code (bash, leitura/edição de arquivos, busca web…) dentro "
        "do workspace do Hermes, e você acompanharia tudo por esta mesma GUI."
    )
    final = ""
    for i in range(0, len(texto), 6):
        if cancel is not None and cancel.is_set():
            ev({"type": "cancelled", "message": final})
            return final
        chunk = texto[i:i + 6]
        final += chunk
        ev({"type": "token", "content": chunk})
        time.sleep(0.02)
    ev({"type": "done", "message": final})
    return final


def run_claude(cfg, message: str, history: list[dict] | None = None,
               on_event=None, cancel: threading.Event | None = None) -> str:
    """Executa o Claude Code e devolve a resposta final (texto).

    Emite os mesmos eventos do chat: step, token, tool_start, tool_end,
    done, error, cancelled.
    """
    ev = on_event or (lambda _e: None)
    history = history or []

    if getattr(cfg, "mock", False):
        return _simulate(message, ev, cancel)

    exe = claude_path()
    if not exe:
        ev({"type": "error", "message": _CLAUDE_INSTALL_HINT})
        return _CLAUDE_INSTALL_HINT

    prompt = _build_prompt(message, history)
    try:
        proc = subprocess.Popen(
            [exe, "-p", prompt, "--output-format", "stream-json", "--verbose"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(cfg.workdir),
        )
    except OSError as exc:
        msg = f"não consegui executar o Claude Code: {exc}"
        ev({"type": "error", "message": msg})
        return msg

    tool_names: dict[str, str] = {}  # tool_use_id -> nome (p/ tool_end)
    final = ""
    t0 = time.time()

    def _finish_ok() -> str:
        ev({"type": "done", "message": final})
        return final

    try:
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                proc.terminate()
                ev({"type": "cancelled", "message": final})
                return final
            if time.time() - t0 > CLAUDE_TIMEOUT_S:
                proc.terminate()
                msg = f"Claude Code excedeu {CLAUDE_TIMEOUT_S // 60} min e foi interrompido."
                ev({"type": "error", "message": msg})
                return final or msg
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = data.get("type")

            if etype == "assistant":
                for block in (data.get("message") or {}).get("content") or []:
                    if block.get("type") == "text" and block.get("text"):
                        final += block["text"]
                        ev({"type": "token", "content": block["text"]})
                    elif block.get("type") == "tool_use":
                        tool_names[block.get("id", "")] = block.get("name", "tool")
                        ev({"type": "tool_start", "name": block.get("name", "tool"),
                            "args": block.get("input") or {}})

            elif etype == "user":
                for block in (data.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_result":
                        out = block.get("content")
                        if not isinstance(out, str):
                            out = json.dumps(out, ensure_ascii=False)
                        nome = tool_names.get(block.get("tool_use_id", ""), "tool")
                        ok = not block.get("is_error")
                        ev({"type": "tool_end", "name": nome, "ok": ok,
                            "output": (out or "")[:4000]})

            elif etype == "result":
                texto = str(data.get("result") or "")
                if texto:
                    final = texto
                if data.get("is_error"):
                    ev({"type": "error", "message": texto or "erro no Claude Code"})
                    return final or texto
                return _finish_ok()

        # processo terminou sem evento "result"
        proc.wait(timeout=10)
        if final:
            return _finish_ok()
        err = (proc.stderr.read() or "").strip()[:400] if proc.stderr else ""
        msg = f"Claude Code terminou sem resposta{(f': {err}' if err else '')}"
        ev({"type": "error", "message": msg})
        return msg
    except Exception as exc:  # noqa: BLE001
        proc.terminate()
        msg = f"falha ao rodar o Claude Code: {exc.__class__.__name__}: {exc}"
        ev({"type": "error", "message": msg})
        return final or msg
    finally:
        if proc.poll() is None:
            proc.terminate()
