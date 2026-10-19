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
import os
import re
import shutil
import subprocess
import threading
import time

CLAUDE_TIMEOUT_S = 900  # teto de 15 min por execução

_CLAUDE_INSTALL_HINT = (
    "Claude Code não encontrado neste computador. Instale com:\n"
    "  curl -fsSL https://claude.ai/install.sh | bash\n"
    "  (ou: npm install -g @anthropic-ai/claude-code)\n"
    "Para usar via Ollama, teste no terminal: ollama launch claude --model hermes3:8b\n"
    "Depois reinicie o `hermes server` e tente de novo."
)


def _claude_env(cfg) -> dict:
    """Ambiente do subprocesso `claude` — Ollama por padrão.

    Com claude_use_ollama=True (padrão), o Claude Code é apontado para o
    MESMO servidor Ollama do agente Hermes, sem precisar exportar nada.
    Variáveis já presentes no ambiente NÃO são sobrescritas.
    """
    env = os.environ.copy()
    if getattr(cfg, "claude_use_ollama", True):
        env.setdefault("ANTHROPIC_BASE_URL",
                       str(getattr(cfg, "ollama_url", "http://127.0.0.1:11434")))
        env.setdefault("ANTHROPIC_AUTH_TOKEN", "ollama")
        env.setdefault("ANTHROPIC_API_KEY", "")
    return env


# Diretiva curta que substitui o prompt gigante do Claude Code no modo local
# (medido: prompt padrão 5.780 chars -> ~300 com --bare + isto).
CLAUDE_LIGHT_PROMPT = (
    "Você é um agente prático rodando LOCALMENTE (Ollama). Responda em "
    "português do Brasil, direto ao ponto. Você tem SOMENTE as ferramentas "
    "Bash, Read e Edit. Para obter dados (sistema, arquivos, rede), EXECUTE "
    "Bash (ex.: uname -a, free -h, df -h, ls) e responda com a saída REAL. "
    "PROIBIDO escrever JSON Schema, XML, exemplos de chamada de ferramenta "
    "ou qualquer explicação sobre como usar ferramentas. Nunca invente dados."
    "\nREGRA INVIOLÁVEL DE EXECUÇÃO: escrever um comando dentro de um bloco "
    "de código é ERRO — o comando só existe quando você CHAMA a ferramenta "
    "Bash. NUNCA peça ao usuário para executar, verificar, abrir o terminal "
    "ou 'conferir com lscpu': quem executa é VOCÊ, com a ferramenta Bash. "
    "Resposta sem execução = resposta errada."
)

# ── guard de execução (v3.0.2) ──────────────────────────────────────────────
# Modelos pequenos às vezes escrevem os comandos em blocos de código (ou
# dizem "você pode verificar com lscpu") em vez de CHAMAR a ferramenta Bash.
# O guard detecta isso e garante que a resposta venha de execução REAL.
_BASH_BLOCK_RE = re.compile(r"```(?:bash|sh|shell|zsh)?\s*\n(.+?)```",
                            re.DOTALL | re.IGNORECASE)
_TELL_USER_RE = re.compile(
    r"voc[eê]\s+pode\s+(verificar|executar|rodar|usar)"
    r"|pode\s+(verificar|executar|rodar)\s+com"
    r"|(execute|rode|digite)\s+(o\s+|esse\s+|este\s+)?comando"
    r"|abra\s+o\s+terminal"
    r"|verifique\s+se\s+os\s+endere",
    re.IGNORECASE)


def _extract_commands(text: str) -> list[str]:
    """Comandos dos blocos ```bash (sem comentários, até 4, ≤500 chars)."""
    out: list[str] = []
    for m in _BASH_BLOCK_RE.finditer(text or ""):
        lines = [l.rstrip() for l in m.group(1).splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        cmd = "\n".join(lines).strip()
        if cmd and len(cmd) <= 500:
            out.append(cmd)
    return out[:4]


def _guard_execute(cfg, commands: list[str], ev) -> str:
    """Último recurso: executa os comandos com as ferramentas do HERMES
    (denylist + timeout + auditoria) e devolve a saída REAL."""
    from .tools import execute_tool

    parts: list[str] = []
    for cmd in commands:
        primeiro = cmd.split()[0] if cmd.split() else ""
        if "sudo " in cmd or "=" in primeiro or '"' in primeiro:
            parts.append(f"$ {cmd}\n(pulado: não parece um comando executável "
                         "de forma segura — rode manualmente se precisar)")
            continue
        ev({"type": "tool_start", "name": "run_command", "args": {"command": cmd}})
        res = execute_tool("run_command", {"command": cmd}, cfg,
                           source="guard-claude", agent="claude")
        ev({"type": "tool_end", "name": "run_command", "ok": res["ok"],
            "output": res["output"][:4000]})
        parts.append(f"$ {cmd}\n{res['output']}")
    return "\n\n".join(parts)


# ── guard anti-loop (v3.1.3) ──────────────────────────────────────────────
# Modelos pequenos locais às vezes DEGENERAM: repetem a mesma linha dezenas
# de vezes até estourar o limite de tokens (visto na prática com "Acessar
# Configurações de Contas do Google:" ×30). O guard corta a repetição na
# resposta final e registra o evento — o streaming bruto é mantido, mas a
# mensagem entregue fica limpa.
_LOOP_THRESHOLD = 4   # ≥4 repetições em sequência = loop
_LOOP_KEEP = 2        # mantém as 2 primeiras ocorrências + nota


def _strip_loops(text: str) -> tuple[str, int]:
    """Corta runs de linhas idênticas consecutivas → (texto limpo, cortes)."""
    lines = (text or "").split("\n")
    out: list[str] = []
    cortes = 0
    i = 0
    while i < len(lines):
        cur = lines[i].strip()
        j = i
        while j < len(lines) and lines[j].strip() == cur:
            j += 1
        run = j - i
        if cur and run >= _LOOP_THRESHOLD:
            out.extend(lines[i:i + _LOOP_KEEP])
            out.append(f"[… guard anti-loop do Hermes: a mesma linha repetiu "
                       f"{run}× e foi cortada aqui …]")
            cortes += run - _LOOP_KEEP
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), cortes


_VERSION_CACHE: dict[str, str] = {}


def _cli_version(exe: str) -> str:
    """Versão da CLI claude (cacheada; '?' se não conseguir ler)."""
    if exe not in _VERSION_CACHE:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True,
                                 text=True, timeout=20)
            m = re.search(r"\d+\.\d+\.\d+", out.stdout or "")
            _VERSION_CACHE[exe] = m.group(0) if m else "?"
        except Exception:  # noqa: BLE001
            _VERSION_CACHE[exe] = "?"
    return _VERSION_CACHE[exe]


def _claude_cmd(exe: str, cfg, prompt: str, light: bool = True) -> list[str]:
    """Linha de comando do Claude Code (headless, stream JSON).

    MODO LEVE (Ollama): --bare — o payload enviado ao modelo cai de 21
    ferramentas/58k chars (o modelo pequeno delira ecoando os schemas, p.ex.
    da ferramenta Workflow) para 3 ferramentas/3,5k chars + prompt mínimo +
    diretiva curta em PT + limite de 4 turnos. CLIs antigas sem --bare caem
    no modo completo pelo fallback de _run_impl.
    """
    cmd = [exe, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    ollama = bool(getattr(cfg, "claude_use_ollama", True))
    model = str(getattr(cfg, "claude_model", "") or "").strip()
    if ollama and not model:
        model = str(getattr(cfg, "model", "") or "").strip()
    if light:
        cmd += [
            "--bare",                        # payload enxuto p/ modelo local
            "--max-turns", "4",              # sem viagens infinitas
            "--append-system-prompt", CLAUDE_LIGHT_PROMPT,
            "--allowedTools", "Bash", "Read", "Edit",
        ]
    if model:
        cmd += ["--model", model]
    return cmd


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
        "No modo real eu rodaria a CLI `claude` — conectada ao seu Ollama — com todas as funções padrão "
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

    Emite os mesmos eventos do chat: step, note, token, tool_start,
    tool_end, done, error, cancelled. O rodapé da resposta indica o modo
    (leve/completo) e a versão da CLI — autodiagnóstico para o usuário.
    """
    return _run_impl(cfg, message, history, on_event, cancel, _light=None)


def _run_impl(cfg, message, history, on_event, cancel, _light=None,
              _guard: bool = False) -> str:
    ev = on_event or (lambda _e: None)
    history = history or []

    if getattr(cfg, "mock", False):
        return _simulate(message, ev, cancel)

    exe = claude_path()
    if not exe:
        ev({"type": "error", "message": _CLAUDE_INSTALL_HINT})
        return _CLAUDE_INSTALL_HINT

    prompt = _build_prompt(message, history)
    ollama_mode = bool(getattr(cfg, "claude_use_ollama", True))
    fell_back = _light is False            # veio do fallback (CLI antiga)
    use_light = ollama_mode and (_light if _light is not None else True)
    ver = _cli_version(exe)
    try:
        proc = subprocess.Popen(
            _claude_cmd(exe, cfg, prompt, light=use_light),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(cfg.workdir), env=_claude_env(cfg),
        )
    except OSError as exc:
        msg = f"não consegui executar o Claude Code: {exc}"
        ev({"type": "error", "message": msg})
        return msg

    tool_names: dict[str, str] = {}  # tool_use_id -> nome (p/ tool_end)
    tools_used = 0                   # v3.0.2: o modelo CHAMOU ferramentas?
    final = ""
    t0 = time.time()
    ev({"type": "step", "step": 1})
    if ollama_mode:
        modo = ("modo leve (payload enxuto p/ modelo local)" if use_light
                else "modo completo — CLI antiga, atualize com: claude update")
        ev({"type": "note", "message": f"Claude Code · {modo} · CLI {ver}"})

    def _finish_ok() -> str:
        texto, cortadas = _strip_loops(final)
        if cortadas:
            ev({"type": "note",
                "message": f"guard anti-loop: {cortadas} linhas repetidas "
                           "cortadas da resposta"})
            try:
                from . import activity
                activity.log(cfg, "claude",
                             f"🌀 guard anti-loop cortou {cortadas} repetições")
            except Exception:  # noqa: BLE001
                pass
        if ollama_mode:
            texto += (f"\n\n─\n*🔌 Claude Code · "
                      f"{'modo leve' if use_light else 'modo completo (CLI antiga — atualize com: claude update)'}"
                      f" · CLI {ver}*")
        ev({"type": "done", "message": texto})
        return texto

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
                        tools_used += 1
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
                        # v3.0: auditoria · v3.1.1: log ao vivo
                        try:
                            from . import audit
                            audit.log(cfg, "claude", nome, {}, ok,
                                      out or "", source="claude-cli")
                        except Exception:  # noqa: BLE001
                            pass
                        try:
                            from . import activity
                            activity.log(cfg, "claude",
                                         f"🔧 {nome} → {'ok' if ok else 'erro'}")
                        except Exception:  # noqa: BLE001
                            pass

            elif etype == "result":
                texto = str(data.get("result") or "")
                if texto:
                    final = texto
                if data.get("is_error"):
                    ev({"type": "error", "message": texto or "erro no Claude Code"})
                    return final or texto

                # ── guard de execução (v3.0.2): escreveu comando, não rodou ──
                if (use_light and tools_used == 0 and not _guard
                        and (cancel is None or not cancel.is_set())):
                    cmds = _extract_commands(final)
                    if cmds or _TELL_USER_RE.search(final or ""):
                        ev({"type": "note",
                            "message": "guard de execução: o modelo escreveu "
                                       "comandos sem executar — repetindo com "
                                       "ordem direta de usar a ferramenta Bash"})
                        fix = (
                            "CORREÇÃO IMPORTANTE: na sua resposta anterior você "
                            "escreveu comandos em blocos de código (ou pediu que "
                            "o usuário executasse/verificasse). Isso é PROIBIDO.\n"
                            "Você possui a ferramenta Bash: CHAME a ferramenta "
                            "Bash para executar cada comando, aguarde o resultado "
                            "e responda com a SAÍDA REAL.\n\n"
                            "Pedido original do usuário:\n" + message + "\n"
                        )
                        if cmds:
                            fix += ("\nConteúdo dos blocos de código da sua resposta "
                                    "anterior (execute via ferramenta Bash o que for "
                                    "comando; se um bloco não for comando válido, "
                                    "ignore e obtenha os dados reais de outra forma):\n")
                            fix += "\n".join(f"  {c}" for c in cmds)
                        return _run_impl(cfg, fix, history=[], on_event=ev,
                                         cancel=cancel, _light=use_light,
                                         _guard=True)
                if _guard and tools_used == 0:
                    cmds = _extract_commands(final)
                    if cmds:
                        ev({"type": "note",
                            "message": "guard de execução: executando os comandos "
                                       "no lugar do modelo (saída real, com auditoria)"})
                        real = _guard_execute(cfg, cmds, ev)
                        final = (final.rstrip()
                                 + "\n\n─\n⚙ *guard de execução do Hermes — o modelo "
                                   "não usou as ferramentas dele; os comandos foram "
                                   "executados pelo Hermes (saída REAL, registrada na "
                                   "aba Auditoria):*\n\n" + real)
                return _finish_ok()

        # processo terminou sem evento "result"
        proc.wait(timeout=10)
        if final:
            return _finish_ok()
        err = (proc.stderr.read() or "").strip()[:400] if proc.stderr else ""
        if use_light and err and ("unknown option" in err.lower()
                                  or "unrecognized" in err.lower()):
            # CLI antiga sem --bare: repete uma vez em modo completo
            ev({"type": "note",
                "message": "esta CLI não suporta --bare — repetindo em modo completo"})
            return _run_impl(cfg, message, history, on_event, cancel,
                             _light=False)
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
