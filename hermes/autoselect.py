"""✨ Auto-atribuição de modelos por papel (v3.11.3).

Lê os modelos instalados no Ollama e escolhe o melhor para cada papel:
💬 chat · 🎯 orquestrador · 🔍 revisor · ⚡ executor · 🔌 claude.

Critérios (explicáveis — cada escolha vem com o motivo):
- ⚡ executor: modelo de CÓDIGO (qwen-coder, codellama…) ganha bônus —
  escrever/executar código e usar ferramentas é o trabalho dele;
- 🎯 orquestrador / 🔍 revisor: modelo GERAL maior ganha — planejar e
  cobrar critérios é raciocínio, não código;
- 💬 chat: a escolha ATUAL do operador é respeitada (bônus alto);
- 🔌 claude: geral (instrução) — código ajuda menos aqui;
- tamanho (B) conta a favor até o teto de 9B: acima disso o ganho de
  raciocínio não compensa em máquina local.

A leitura é sempre da lista INSTALADA no momento — instalar um modelo
novo e rodar de novo re-atribui tudo sozinho.
"""
from __future__ import annotations

import re

_CODER = re.compile(r"coder|codellama|starcoder|codegemma|deepseek-coder|"
                    r"codeqwen", re.IGNORECASE)
_GERAL = re.compile(r"hermes|qwen|llama|gemma|mistral|phi|granite|mixtral",
                    re.IGNORECASE)

PAPEIS = ("chat", "orchestrator", "reviewer", "executor", "claude")
CHAVES = {"chat": "model", "orchestrator": "orchestrator_model",
          "reviewer": "reviewer_model", "executor": "executor_model",
          "claude": "claude_model"}
ICONES = {"chat": "💬", "orchestrator": "🎯", "reviewer": "🔍",
          "executor": "⚡", "claude": "🔌"}


def _params(nome: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", nome, re.IGNORECASE)
    return float(m.group(1)) if m else 4.0


def _score(nome: str, papel: str, chat_atual: str) -> float:
    p = _params(nome)
    s = min(p, 9.0)                    # raciocínio cresce com o tamanho
    coder = bool(_CODER.search(nome))
    geral = bool(_GERAL.search(nome))
    if papel == "executor":
        s += 6.0 if coder else 0.0     # código é o ofício do executor
    elif papel in ("orchestrator", "reviewer"):
        s += 3.0 if geral else 0.0     # planejar/cobrar = modelo geral
        s -= 2.0 if coder else 0.0     # coder é pior em planejamento geral
    elif papel == "chat":
        if nome == chat_atual:
            s += 8.0                   # respeita a escolha do operador
        s += 1.0 if geral else 0.0
    elif papel == "claude":
        s += 2.0 if geral else 0.0     # Claude Code = seguir instrução
    return s


def choose(models: list[str], chat_atual: str = "",
           max_b: float | None = None) -> dict[str, tuple[str, str]]:
    """Devolve {papel: (modelo, motivo)} para a lista instalada.

    v3.11.4: max_b filtra modelos acima do teto de tamanho (B) — o
    auto-assign jamais entrega um modelo que não roda bem no hardware
    do operador só porque é "maior".""",
    out: dict[str, tuple[str, str]] = {}
    if max_b is not None:
        models = [m for m in models if _params(str(m)) <= float(max_b)]
    if not models:
        return out
    for papel in PAPEIS:
        melhor, ms = "", -1.0
        for m in models:
            s = _score(str(m), papel, chat_atual)
            if s > ms:
                melhor, ms = str(m), s
        p = _params(melhor)
        coder = bool(_CODER.search(melhor))
        if papel == "executor":
            motivo = (f"modelo de código ({p:g}B) — feito para escrever e "
                      "executar código com ferramentas" if coder else
                      f"melhor geral disponível ({p:g}B) — nenhum modelo "
                      "de código instalado")
        elif papel in ("orchestrator", "reviewer"):
            motivo = f"maior modelo geral ({p:g}B) — raciocínio para planejar e cobrar critérios"
        elif papel == "chat":
            motivo = (f"escolha atual do operador ({p:g}B)" if melhor == chat_atual
                      else f"melhor geral para conversa ({p:g}B)")
        else:
            motivo = f"geral para seguir instruções ({p:g}B)"
        out[papel] = (melhor, motivo)
    return out


def run_auto(cfg, models: list[str] | None = None,
             print_fn=print, apply: bool = True) -> dict:
    """Escolhe (e aplica+salva) os melhores modelos por papel."""
    if models is None:
        from .manager import OllamaManager
        st = OllamaManager(cfg).status()
        if not st.get("running") or not st.get("models"):
            print_fn("✖ Ollama desligado ou sem modelos — ligue com: "
                     "hermes ollama start")
            return {"ok": False, "msg": "Ollama desligado ou sem modelos"}
        models = [str(m) for m in st["models"]]
    chat_atual = str(cfg.model or "")
    max_b = float(getattr(cfg, "max_model_b", 9.0) or 9.0)
    esc = choose(models, chat_atual, max_b=max_b)
    fora = [str(m) for m in models if _params(str(m)) > max_b]
    if fora:
        print_fn(f"  ⛔ ignorados acima do teto max_model_b={max_b:g}: "
                 + ", ".join(fora))
    if not esc:
        print_fn("✖ nenhum modelo instalado.")
        return {"ok": False, "msg": "nenhum modelo instalado"}
    if apply:
        cfg.update({CHAVES[p]: v[0] for p, v in esc.items()})
    for papel, (m, motivo) in esc.items():
        print_fn(f"  {ICONES[papel]} {papel:<12} → {m}")
        print_fn(f"      · {motivo}")
    print_fn("✔ papéis atribuídos" + (" e salvos no config" if apply else ""))
    return {"ok": True,
            "assignments": {p: v[0] for p, v in esc.items()},
            "reasons": {p: v[1] for p, v in esc.items()}}
