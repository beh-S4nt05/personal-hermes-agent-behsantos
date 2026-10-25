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
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .mcp_client import get_manager
from .ollama_client import OllamaError, get_client
from .skills import SkillLoader
from .tools import TOOLS, TOOL_NAMES, execute_tool

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
{webtools}- lembrar / esquecer: guarda e apaga fatos sobre o usuário (memória permanente).

Boas práticas:
- Sempre INSPECIONE antes de agir (ex.: `df -h`, `free -h`, `ls`, ler arquivos).
- NUNCA simule ou invente a saída de uma ferramenta: CHAME a ferramenta e
  aguarde o resultado real (se pediram dados do sistema, use sys_info).
- Um comando por vez; analise a saída antes do próximo passo.
- Nunca destrua dados: prefira backups (`cp arquivo arquivo.bak`) antes de alterar.
- Comandos perigosos (apagar a raiz, formatar, desligar) são bloqueados automaticamente.
- Ao concluir, resuma o que foi feito, resultados e próximos passos sugeridos.

Contexto da máquina:
- hostname: {hostname}
- workspace: {workdir}
- sandbox de arquivos: {sandbox}

{extra}\
"""

def _now_line() -> str:
    """Data/hora fresca — entra NO FINAL do prompt, fora do cache, para o
    prefixo (parte cacheada) ficar estável entre mensagens."""
    return f"\n\nData/hora local: {time.strftime('%Y-%m-%d %H:%M')}"


# Guard anti-loop: modelos pequenos às vezes repetem a mesma chamada/fala
_ANTILOOP_NUDGE = (
    "ATENÇÃO: você já executou exatamente esta ferramenta com os mesmos "
    "argumentos e o resultado está no histórico acima. NÃO repita a chamada "
    "nem repita o texto — mas NUNCA se recuse a responder: escreva AGORA a "
    "RESPOSTA COMPLETA ao usuário usando os dados que já obteve. "
    "'Estou pronto para ajudar' ou 'não vou repetir' NÃO são respostas — "
    "são falha de entrega. Cite os números/outputs coletados e conclua."
)

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


def _bare_tool_call(text: str) -> list[dict]:
    """Detecta chamada de ferramenta em JSON SEM cercas de código.

    Modelos pequenos às vezes respondem com o JSON cru (com ou sem um
    prefixo de texto curto) em vez de usar a chamada nativa. Retorna [] se
    não parecer uma chamada de ferramenta.
    """
    t = (text or "").strip()
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if (isinstance(obj, dict)
            and {"name", "tool"} & set(obj)
            and {"arguments", "args"} & set(obj)):
        return _as_tool_calls(obj)
    return []


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
        self._prompt_cache: tuple[str, str] | None = None  # v3.0: cache do prompt

    # ------------------------------------------------- seleção de ferramentas
    @staticmethod
    def _score_tool(query: str, tool: dict) -> int:
        """Similaridade barata (overlap de palavras) entre pergunta e ferramenta."""
        import unicodedata

        def words(s: str) -> set[str]:
            s = unicodedata.normalize("NFKD", s.lower())
            s = "".join(c for c in s if c.isascii())
            stop = {"de", "da", "do", "para", "com", "que", "uma", "um", "os",
                    "as", "em", "no", "na", "por", "e", "o", "a", "meu", "minha",
                    "the", "of", "to", "for", "and", "in"}
            return {w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2 and w not in stop}

        fn = tool.get("function") or {}
        q = words(query or "")
        if not q:
            return 0
        tgt = words((fn.get("name") or "") + " " + (fn.get("description") or ""))
        return len(q & tgt)

    def _select_mcp_tools(self, query: str, mcp_tools: list[dict]) -> list[dict]:
        """v3.0: com muitas ferramentas MCP, injeta só as relevantes à pergunta
        (payload menor = modelo pequeno menos confuso e mais rápido)."""
        if (not getattr(self.cfg, "tool_selector", True)
                or len(mcp_tools) <= 8):
            return mcp_tools
        ranked = sorted(mcp_tools,
                        key=lambda t: self._score_tool(query, t), reverse=True)
        return ranked[:8]

    # ------------------------------------------------------- cache do prompt
    def _prompt_key(self, query: str | None) -> str:
        """Chave de invalidação do cache: muda só quando algo relevante muda."""
        parts = [
            str(getattr(self.cfg, "system_prompt_extra", "")),
            str(getattr(self.cfg, "web_access", True)),
            str(getattr(self.cfg, "sandbox", True)),
            str(self.native_tools),
            socket.gethostname(),
            str(query or "")[:400],
        ]
        try:
            for d in self.cfg.skills_dirs:
                for f in sorted(d.glob("*/SKILL.md")):
                    try:
                        st = f.stat()
                        parts.append(f"{f.name}:{st.st_mtime_ns}")
                    except OSError:
                        pass
        except Exception:  # noqa: BLE001
            pass
        try:
            mp = self.cfg.data_dir / "memory.json"
            if mp.exists():
                st = mp.stat()
                parts.append(f"mem:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            pass
        # contexto do projeto (M2): escopo + conteúdo (hash) dos arquivos
        try:
            from .project_context import secao as _pc_secao
            _pcs = _pc_secao(self.cfg)
            if _pcs:
                parts.append(f"pc:{hash(_pcs)}")
        except Exception:  # noqa: BLE001
            pass
        try:
            parts.append("mcp:" + ",".join(sorted(self.mcp._map.keys())))
        except Exception:  # noqa: BLE001
            pass
        return "|".join(parts)

    # -------------------------------------------------------------- prompt
    def system_prompt(self, query: str | None = None) -> str:
        key = self._prompt_key(query)
        if self._prompt_cache and self._prompt_cache[0] == key:
            return self._prompt_cache[1] + _now_line()   # cache + hora fresca
        extra = self.cfg.system_prompt_extra.strip()
        webtools = (
            "- web_search / web_fetch: pesquisa na internet (DuckDuckGo) e lê "
            "páginas.\n  Use SEMPRE que a resposta depender de informação atual "
            "ou quando não tiver certeza de um fato — NUNCA invente dados;\n  "
            "cite as fontes (endereços) na resposta. Em pesquisas e "
            "monitoramentos,\n  siga a skill pesquisa-web (relatórios em "
            "arquivo + fatos úteis na memória).\n"
            if getattr(self.cfg, "web_access", True) else ""
        )
        prompt = SYSTEM_PROMPT.format(
            webtools=webtools,
            hostname=socket.gethostname(),
            workdir=self.cfg.workdir,
            sandbox="ATIVO (apenas o workspace)" if self.cfg.sandbox else "DESATIVADO (caminhos absolutos liberados)",
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
            catalog = self.skills.catalog(query)
            if catalog:
                prompt += "\n\n" + catalog
        except Exception:
            pass
        # contexto do projeto (v4.0.0 M2): HERMES.md/AGENTS.md descoberto
        # no escopo da task + global da máquina — externo recebe versão
        # filtrada pelo DLP (segredos/código censurados, regra D2)
        try:
            from .project_context import secao as _pc_secao, versao_externa
            _pc = _pc_secao(self.cfg)
            if _pc:
                if getattr(self.client, "is_external", False):
                    _pc = versao_externa(_pc)
                prompt += _pc
        except Exception:
            pass
        # memória persistente: fatos sobre o usuário valem para todas as
        # conversas — mas NUNCA para provedores externos (v3.17.0: regra de
        # privacidade do operador; dados pessoais ficam na máquina)
        if not getattr(self.client, "is_external", False):
            try:
                from .memory import MemoryStore
                mem = MemoryStore(self.cfg).prompt_section(query)
                if mem:
                    prompt += mem
            except Exception:
                pass
        self._prompt_cache = (key, prompt)
        return prompt + _now_line()

    # ---------------------------------------------------------------- loop
    # ---------------------------------------- v3.15.0: compactação de contexto
    def _resumir(self, texto: str) -> str:
        """Resumo curto do meio da conversa — LLM se der, senão corte
        determinístico (a task nunca falha por causa do resumo)."""
        try:
            pedaco: list[str] = []
            for chunk in self.client.chat_stream(
                    getattr(self, "model_override", None) or self.cfg.model,
                    [{"role": "user", "content":
                      "Resuma em até 8 linhas curtas o ESSENCIAL desta "
                      "sequência de trabalho (objetivo, achados, arquivos, "
                      "comandos, erros e correções). Sem introdução:\n"
                      + texto[:12000]}],
                    options={"num_predict": 300, "temperature": 0.2}):
                t = (chunk.get("message") or {}).get("content")
                if t:
                    pedaco.append(t)
            r = "".join(pedaco).strip()
            if r:
                return r[:1500]
        except Exception:  # noqa: BLE001
            pass
        linhas = [l.strip()[:120] for l in texto.splitlines() if l.strip()][:8]
        return "\n".join(linhas) or "(nada a resumir)"

    def _compactar(self, msgs: list[dict], ev) -> list[dict]:
        """v3.15.0 (PR#3): compactação de contexto (padrão Claude Code).
        Perto do limite da janela, o MEIO da conversa vira resumo e o
        essencial fica: sistema, tarefa original e resultados recentes."""
        limite = max(int(getattr(self.cfg, "num_ctx", 8192)) * 55 // 100, 800)
        total = sum(len(str(m.get("content") or "")) for m in msgs) // 4
        if total <= limite or len(msgs) <= 6:
            return msgs
        i_tarefa = 1
        for i, m in enumerate(msgs):
            if m.get("role") == "user":
                i_tarefa = i
                break
        k = max(i_tarefa + 2, len(msgs) - 4)
        while k > i_tarefa + 2 and msgs[k].get("role") == "tool":
            k -= 1                    # não órfã: tool precisa do assistant
        meio = msgs[i_tarefa + 1:k]
        if not meio:
            return msgs
        ser = "\n".join(f"[{m.get('role')}] " + str(m.get("content") or "")[:600]
                         for m in meio)
        resumo = self._resumir(ser)
        ev({"type": "note",
            "message": f"🧠 contexto compactado ({len(meio)} mensagens → resumo) "
                       "— tarefa original e resultados recentes preservados"})
        return ([msgs[0], msgs[i_tarefa],
                 {"role": "user",
                  "content": "[CONTEXTO ANTERIOR RESUMIDO — trabalho já feito:\n"
                             + resumo
                             + "\n(continua abaixo com os resultados mais recentes)]"}]
                + msgs[k:])

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

        query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                query = str(m.get("content") or "")
                break
        t0 = time.time()
        msgs: list[dict] = [{"role": "system", "content": self.system_prompt(query)}]
        msgs += [m for m in messages if m.get("role") in ("user", "assistant", "tool")]
        final = ""
        last_sigs: list[tuple[str, str]] = []   # assinaturas do passo anterior
        nudged = False                           # já avisamos sobre repetição?
        calls_used = 0                           # v3.0: orçamento de ferramentas
        max_calls = int(getattr(self, "tool_budget_override", 0)
                        or getattr(cfg, "max_tool_calls", 12) or 12)
        budget_strikes = False                    # já avisamos o orçamento?

        passos_max = int(getattr(self, "steps_override", 0) or cfg.max_steps)
        for step in range(1, passos_max + 1):
            if cancel is not None and cancel.is_set():
                ev({"type": "cancelled", "message": final or ""})
                return final or "[interrompido pelo operador]"
            ev({"type": "step", "step": step, "t": round(time.time() - t0, 1)})
            tools = list(TOOLS)
            if not getattr(cfg, "web_access", True):
                tools = [t for t in tools
                         if t["function"]["name"] not in ("web_search", "web_fetch")]
            if self.native_tools:
                try:
                    # v3.0: só as ferramentas MCP relevantes à pergunta
                    tools += self._select_mcp_tools(
                        query, self.mcp.openai_tools())
                except Exception:
                    pass
            msgs[0] = {"role": "system", "content": self.system_prompt(query)}
            msgs = self._compactar(msgs, ev)   # v3.15.0: sem perder contexto

            content = ""
            calls: list[dict] = []
            cancelled = False
            try:
                gen_options = {"num_ctx": cfg.num_ctx,
                               "temperature": cfg.temperature}
                # respostas mais rápidas: limite de tokens (0 = sem limite)
                num_predict = int(getattr(cfg, "num_predict", 0) or 0)
                if num_predict > 0:
                    gen_options["num_predict"] = num_predict
                for chunk in self.client.chat_stream(
                    getattr(self, "model_override", None) or cfg.model,
                    msgs,
                    tools=tools,
                    options=gen_options,
                    cancel=cancel,
                    keep_alive=getattr(cfg, "keep_alive", "30m"),
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
            # Fallback 2: modelos pequenos escrevem a chamada como JSON solto
            # (sem cercas de código) — e às vezes "inventam" os argumentos.
            # Só executa se o nome for uma ferramenta real; a saída é SEMPRE
            # a verdadeira (nada de dados fabricados pelo modelo).
            if not calls:
                for cand in _bare_tool_call(content):
                    fname = (cand.get("function") or {}).get("name", "")
                    if fname in TOOL_NAMES or self.mcp.handles(fname):
                        calls = [cand]
                        break

            if not calls:
                final = content
                ev({"type": "done", "message": content})
                return final

            # ── anti-loop: chamada idêntica à do passo anterior ──
            sigs = [
                (str((c.get("function") or {}).get("name", "")),
                 json.dumps((c.get("function") or {}).get("arguments") or {},
                            sort_keys=True, ensure_ascii=False))
                for c in calls
            ]
            if sigs and sigs == last_sigs:
                if nudged:
                    # insistiu na repetição: encerra entregando o que já tem
                    final = (content or final or "").strip()
                    final += ("\n\n*(encerrado pelo anti-loop: a ação já foi executada "
                              "e o resultado está acima)*")
                    ev({"type": "done", "message": final})
                    return final
                nudged = True
                msgs.append({"role": "user", "content": _ANTILOOP_NUDGE})
                continue
            last_sigs = sigs
            nudged = False

            def _exec_one(name: str, args):
                """Executa UMA ferramenta (nativa ou MCP) — com auditoria."""
                if self.mcp.handles(name):
                    res = self.mcp.call(name, args)
                    try:
                        from . import audit
                        audit.log(cfg, "hermes", name, args, res["ok"],
                                  res["output"], source="agent")
                    except Exception:  # noqa: BLE001
                        pass
                    return res["ok"], res["output"]
                res = execute_tool(name, args, cfg)
                return res["ok"], res["output"]

            # ── v3.0: orçamento de ferramentas (cadeia infinita não passa) ──
            runnable = calls
            if calls_used >= max_calls:
                for call in calls:
                    fn = call.get("function") or {}
                    msgs.append({
                        "role": "tool", "name": fn.get("name", ""),
                        "content": ("BLOQUEADO: orçamento de ferramentas esgotado "
                                    f"({max_calls} chamadas). Responda ao usuário "
                                    "com o que já coletou.")})
                ev({"type": "note",
                    "message": f"orçamento de ferramentas esgotado ({max_calls})"})
                if budget_strikes:  # 2ª vez seguida: encerra e entrega o parcial
                    final = (content or final or "").strip()
                    final += ("\n\n*(encerrado: orçamento de ferramentas esgotado — "
                              "o que foi coletado está acima)*")
                    ev({"type": "done", "message": final})
                    return final
                budget_strikes = True
                continue
            budget_strikes = False
            calls_used += len(runnable)

            # ── v3.0: ferramentas em paralelo (2+ chamadas no mesmo passo) ──
            if len(runnable) > 1 and allow_tool is None:
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futs = []
                    for call in runnable:
                        fn = call.get("function") or {}
                        name, args = fn.get("name", ""), fn.get("arguments") or {}
                        ev({"type": "tool_start", "name": name, "args": args})
                        futs.append((name, pool.submit(_exec_one, name, args)))
                    for name, fut in futs:
                        ok, result = fut.result()
                        ev({"type": "tool_end", "name": name, "ok": ok,
                            "output": result[:4000]})
                        msgs.append({"role": "tool", "name": name, "content": result})
            else:
                for call in runnable:
                    if cancel is not None and cancel.is_set():
                        break  # cancelado durante as ferramentas
                    fn = call.get("function") or {}
                    name = fn.get("name", "")
                    args = fn.get("arguments") or {}
                    ev({"type": "tool_start", "name": name, "args": args})

                    if allow_tool is not None and not allow_tool(name, args):
                        result = "BLOQUEADO pelo operador (confirmação negada)."
                        ev({"type": "tool_end", "name": name, "ok": False, "output": result})
                    else:
                        ok, result = _exec_one(name, args)
                        ev({"type": "tool_end", "name": name, "ok": ok,
                            "output": result[:4000]})

                    msgs.append({"role": "tool", "name": name, "content": result})

        hint = (f"Limite de {passos_max} passes atingido; aumente 'max_steps' "
                f"se precisar.")
        ev({"type": "error", "message": hint})
        return final or hint
