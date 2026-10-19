"""Núcleo do agente: loop modelo -> ferramentas -> resposta final.

Eventos emitidos (via callback on_event) para TUI, daemon e GUI:
  {"type": "step",      "step": int}
  {"type": "token",     "content": str}
  {"type": "tool_start","name": str, "args": dict}
  {"type": "tool_end",  "name": str, "ok": bool, "output": str}
  {"type": "done",      "message": str}
  {"type": "error",     "message": str}
"""

from __future__ import annotations

import json
import re
import socket
import time

from .config import Config
from .mcp_client import get_manager
from .ollama_client import OllamaError, get_client
from .skills import SkillLoader
from .tools import TOOLS, execute_tool, tool_summary

SYSTEM_PROMPT = """\
Você é o Hermes, um agente de operação Linux controlável por terminal e por uma \
interface web. Você roda localmente sobre o Ollama, na máquina do usuário.

Identidade e postura:
- Fale português do Brasil por padrão (responda no idioma do usuário).
- Seja direto e técnico; explique o que fez e por quê. Sem enrolação.
- Você é o braço operacional do usuário: diagnosticar, gerenciar e automatizar.

Capacidades (ferramentas):
- run_command: executa comandos bash (use para diagnosticar/gerenciar o sistema).
- read_file / write_file / list_dir: manipulam arquivos no workspace.
- sys_info: diagnóstico rápido da máquina.

Boas práticas:
- Sempre INSPECIONE antes de agir (ex.: `df -h`, `free -h`, `ls`, ler arquivos).
- Um comando por vez; analise a saída antes do próximo passo.
- Nunca destrua dados: prefira backups (`cp arquivo arquivo.bak`) antes de alterar.
- Comandos perigosos (apagar a raiz, formatar, desligar) são bloqueados automaticamente.
- Ao concluir, resuma o que foi feito, resultados e próximos passos sugeridos.

Contexto da máquina:
- hostname: {hostname}
- workspace: {workdir}
- sandbox de arquivos: {sandbox}
- data/hora local: {now}

{extra}\
"""

# Plano B caso o modelo/servidor não aceite ferramentas nativas da API:
FALLBACK_TOOLS_NOTE = """
Como alternativa às ferramentas nativas, você TAMBÉM pode chamar uma ferramenta \
respondendo com um único bloco de código json no formato:
```json
{{"tool": "nome_da_ferramenta", "args": {{"parametro": "valor"}}}}
```
Use isso somente quando necessário e aguarde o resultado antes de continuar."""


def _json_blocks(text: str) -> list[dict]:
    """Extrai blocos ```json ...``` (ou json solto) do texto do modelo."""
    blocks: list[dict] = []
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                blocks.append(parsed)
        except json.JSONDecodeError:
            continue
    return blocks


def _as_tool_calls(block: dict) -> list[dict]:
    """Normaliza {"tool":..,"args":..} / {"name":..,"arguments":..} para o formato da API."""
    raw = block.get("tool_calls") if isinstance(block.get("tool_calls"), list) else [block]
    calls = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("tool") or item.get("name") or item.get("function", {}).get("name")
        args = item.get("args") or item.get("arguments") or item.get("function", {}).get("arguments") or {}
        if isinstance(name, str) and name:
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"input": args}
            calls.append({"function": {"name": name, "arguments": args}})
    return calls


class Agent:
    def __init__(self, cfg: Config | None = None, client=None):
        self.cfg = cfg or Config()
        self.client = client or get_client(self.cfg)
        self.mcp = get_manager(self.cfg)      # conectores MCP (Figma, etc.)
        self.skills = SkillLoader(self.cfg)   # catálogo de skills SKILL.md
        self.native_tools = True  # desliga automaticamente se o servidor não suportar

    # -------------------------------------------------------------- prompt
    def system_prompt(self) -> str:
        extra = self.cfg.system_prompt_extra.strip()
        prompt = SYSTEM_PROMPT.format(
            hostname=socket.gethostname(),
            workdir=self.cfg.workdir,
            sandbox="ATIVO (apenas o workspace)" if self.cfg.sandbox else "DESATIVADO (caminhos absolutos liberados)",
            now=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            extra=f"Instruções adicionais do operador:\n{extra}\n" if extra else "",
        )
        if not self.native_tools:
            prompt += FALLBACK_TOOLS_NOTE.format()
        # seções dinâmicas: ferramentas MCP e catálogo de skills
        try:
            mcp_tools = self.mcp.openai_tools()
            if mcp_tools:
                lines = [
                    f"- {t['function']['name']}: "
                    f"{t['function']['description'].splitlines()[0][:160]}"
                    for t in mcp_tools
                ]
                prompt += (
                    "\n\nFerramentas MCP conectadas (use como qualquer outra ferramenta;\n"
                    "as instruções detalhadas podem estar numa skill — veja abaixo):\n"
                    + "\n".join(lines)
                )
        except Exception:
            pass
        try:
            catalog = self.skills.catalog()
            if catalog:
                prompt += "\n\n" + catalog
        except Exception:
            pass
        # memória persistente: fatos sobre o usuário valem para todas as conversas
        try:
            from .memory import MemoryStore
            mem = MemoryStore(self.cfg).prompt_section()
            if mem:
                prompt += mem
        except Exception:
            pass
        return prompt

    # ---------------------------------------------------------------- loop
    def run(self, messages: list[dict], on_event=None, allow_tool=None, cancel=None) -> str:
        """Executa uma tarefa/conversa. `messages` sem o prompt de sistema.

        allow_tool(name, args) -> bool permite ao chamador vetar uma ferramenta
        (usado pela TUI para confirmar comandos arriscados).
        cancel (threading.Event) interrompe a geração a qualquer momento —
        o retorno preserva o texto parcial já gerado.
        """
        ev = on_event or (lambda _e: None)
        cfg = self.cfg

        # Ollama desligado? Tenta subir sozinho se o operador ativou o arranjo
        # automático (Ajustes / aba Ollama da GUI, ou auto_start_ollama no yaml).
        if getattr(cfg, "auto_start_ollama", False) and not self.client.simulated:
            try:
                if not self.client.is_running():
                    from .manager import OllamaManager
                    OllamaManager(cfg).start()
            except Exception:
                pass

        msgs: list[dict] = [{"role": "system", "content": self.system_prompt()}]
        msgs += [m for m in messages if m.get("role") in ("user", "assistant", "tool")]
        final = ""

        for step in range(1, cfg.max_steps + 1):
            if cancel is not None and cancel.is_set():
                ev({"type": "cancelled", "message": final or ""})
                return final or "[interrompido pelo operador]"
            ev({"type": "step", "step": step})
            tools = list(TOOLS)
            if self.native_tools:
                try:
                    tools += self.mcp.openai_tools()  # ferramentas dos conectores MCP
                except Exception:
                    pass
            msgs[0] = {"role": "system", "content": self.system_prompt()}

            content = ""
            calls: list[dict] = []
            cancelled = False
            try:
                for chunk in self.client.chat_stream(
                    cfg.model,
                    msgs,
                    tools=tools,
                    options={"num_ctx": cfg.num_ctx, "temperature": cfg.temperature},
                    cancel=cancel,
                ):
                    m = chunk.get("message") or {}
                    token = m.get("content") or ""
                    if token:
                        content += token
                        ev({"type": "token", "content": token})
                    for c in m.get("tool_calls") or []:
                        if c:
                            calls.append(c)
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                        break
            except OllamaError as exc:
                msg = str(exc)
                low = msg.lower()
                if self.native_tools and ("does not support tools" in low
                                          or "tool not supported" in low
                                          or ("tool" in low and "support" in low)):
                    # Servidor/modelo sem ferramentas nativas -> modo fallback.
                    self.native_tools = False
                    continue
                if "invalid model name" in low:
                    models = []
                    try:
                        models = self.client.list_models()
                    except Exception:
                        pass
                    hint = (
                        f"O nome do modelo '{cfg.model}' é inválido para o Ollama "
                        "(use o formato nome:tag, ex.: hermes3:8b, sem espaços). "
                        "Corrija em Ajustes → modelo, ou com: "
                        "hermes config set model hermes3:8b"
                    )
                    if models:
                        hint += f" Modelos instalados nesta máquina: {', '.join(models)}"
                    elif not self.client.simulated:
                        hint += " Nenhum modelo instalado — rode: ollama pull hermes3:8b"
                    ev({"type": "error", "message": hint})
                    return final or hint
                if "not found" in low and cfg.model.lower() in low:
                    hint = f"Modelo '{cfg.model}' não encontrado. Baixe com: ollama pull {cfg.model}"
                    ev({"type": "error", "message": hint})
                    return final or hint
                ev({"type": "error", "message": msg})
                return final or f"[erro] {msg}"

            if cancelled:
                if content:
                    msgs.append({"role": "assistant", "content": content})
                ev({"type": "cancelled", "message": content or ""})
                return content or "[interrompido pelo operador]"

            assistant: dict = {"role": "assistant", "content": content}
            if calls:
                assistant["tool_calls"] = calls
            msgs.append(assistant)

            # Fallback: o modelo pode tentar chamar ferramenta via JSON no texto.
            if not calls:
                for block in _json_blocks(content):
                    parsed = _as_tool_calls(block)
                    if parsed:
                        calls = parsed
                        break

            if not calls:
                final = content
                ev({"type": "done", "message": content})
                return final

            for call in calls:
                if cancel is not None and cancel.is_set():
                    break  # cancelado durante as ferramentas
                fn = call.get("function") or {}
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                ev({"type": "tool_start", "name": name, "args": args})

                if allow_tool is not None and not allow_tool(name, args):
                    result = "BLOQUEADO pelo operador (confirmação negada)."
                    ev({"type": "tool_end", "name": name, "ok": False, "output": result})
                elif self.mcp.handles(name):
                    # ferramenta de um conector MCP (Figma, GitHub, ...)
                    res = self.mcp.call(name, args)
                    ev({"type": "tool_end", "name": name, "ok": res["ok"],
                        "output": res["output"][:4000]})
                    result = res["output"]
                else:
                    res = execute_tool(name, args, cfg)
                    ev({"type": "tool_end", "name": name, "ok": res["ok"],
                        "output": res["output"][:4000]})
                    result = res["output"]

                msgs.append({"role": "tool", "name": name, "content": result})

        hint = f"Limite de {cfg.max_steps} passes atingido; aumente 'max_steps' se precisar."
        ev({"type": "error", "message": hint})
        return final or hint
