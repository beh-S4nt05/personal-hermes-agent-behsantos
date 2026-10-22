"""`hermes selftest` — bateria de aceitação com LLM REAL (v3.13.3).

A suíte tests/run_all.py (98 casos) roda 100% em mock: garante o
ESQUELETO, mas não o comportamento do modelo. Este selftest roda os
DOIS: manda pedidos reais ao modelo configurado e verifica o que
importa no campo — entrega não-vazia, sem recusa, com evidência real
(ferramenta usada, código executado, número certo, memória guardada).

Requisitos: Ollama ligado com o modelo configurado. Sem Ollama, o
selftest é PULADO limpo (exit 0) — rode na sua máquina:

    hermes selftest [--timeout 240]
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

# marcas da falha de campo observada no operador (v3.13.1/v3.13.2)
_RECUSA = ["não vou repetir", "pronto para ajudar",
           "não vou repetir chamadas", "sem repetir o conteúdo"]


def _evidencias(events: list[dict]) -> list[str]:
    return [str(e.get("name") or "") for e in events
            if e.get("type") == "tool_start"]


def _setup_dados(cfg) -> None:
    d = Path(cfg.workdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "dados.csv").write_text(
        "produto,valor\ncafe,10\nlivro,20\nteclado,30\n", encoding="utf-8")


def _cenarios() -> list[dict]:
    """Cada cenário: msgs em sequência; checa(final_último, eventos,
    ) -> list[str] de problemas (vazio = aprovado)."""
    def diag(f, evs):
        out = []
        if len(f) < 80:
            out.append(f"entrega curta ({len(f)} chars)")
        if not _evidencias(evs):
            out.append("nenhuma ferramenta usada — possível alucinação")
        return out

    def codigo(f, evs):
        ev = _evidencias(evs)
        out = []
        if "write_file" not in ev:
            out.append("não escreveu arquivo")
        if "run_command" not in ev:
            out.append("não executou o código")
        if "5" not in f:
            out.append("saída real ausente — onde está o 5?")
        return out

    def dados(f, evs):
        ev = _evidencias(evs)
        out = []
        if not ({"read_file", "run_command"} & set(ev)):
            out.append("não leu nenhum dado real")
        if "60" not in f:
            out.append("total 60 ausente — calculou sem ler?")
        return out

    def conhece(f, evs):
        if len(f) < 100:
            return [f"resposta curta demais ({len(f)} chars)"]
        return []

    def memoria(f, evs):
        if "tigrão" not in f.lower():
            return ["apelido não foi lembrado na 2ª conversa"]
        return []

    return [
        {"nome": "diagnóstico do dispositivo",
         "msgs": ["faça uma busca geral no meu sistema e entenda "
                  "meu uso do dispositivo"], "checa": diag},
        {"nome": "código verificado (executa e mostra saída)",
         "msgs": ["crie um script Python soma.py que calcula 2+3 e "
                  "mostre ele funcionando"], "checa": codigo},
        {"nome": "dados reais (lê e calcula certo)",
         "setup": _setup_dados,
         "msgs": ["leia o arquivo dados.csv e diga qual é o total "
                  "da coluna valor"], "checa": dados},
        {"nome": "conhecimento (responde completo)",
         "msgs": ["explique em 3 frases o que é memória swap no Linux"],
         "checa": conhece},
        {"nome": "memória (guarda e usa)",
         "msgs": ["lembre que meu apelido é Tigrão",
                  "qual é o meu apelido?"], "checa": memoria},
    ]


def run(cfg, timeout: int = 240, print_fn=print) -> int:
    """Roda a bateria; devolve exit code (0 = tudo verde OU pulado)."""
    if getattr(cfg, "mock", False):
        print_fn("⏭ selftest PULADO — modo demonstração (mock) não testa "
                 "comportamento real.")
        print_fn("  rode sem mock: hermes selftest")
        return 0
    from .manager import OllamaManager

    st = OllamaManager(cfg).status()
    if not (st.get("running") and st.get("models")):
        print_fn("⏭ selftest PULADO — Ollama desligado ou sem modelos.")
        print_fn("  ligue com: hermes ollama start   (depois: hermes selftest)")
        return 0
    print_fn(f"🧪 hermes selftest · modelo real: {cfg.model}")
    print_fn("  bateria de campo: entrega não-vazia, sem recusa, com "
             "evidência real\n")

    from .config import Config
    from .agent import Agent
    from .orchestrator import run_pipeline

    # ambiente ISOLADO (não toca nos dados do operador), mesmo modelo
    cfg_t = Config(data_dir=tempfile.mkdtemp(prefix="hermes-selftest-"))
    cfg_t.update({"model": str(cfg.model),
                  "orchestrator_model": "", "reviewer_model": "",
                  "executor_model": "", "creation_approval": False})
    agent = Agent(cfg_t)

    ok = falhas = 0
    for c in _cenarios():
        if c.get("setup"):
            c["setup"](cfg_t)
        eventos: list[dict] = []
        cancel = threading.Event()
        resultado = {"final": "", "erro": None}
        estourou = False

        def _rodar(msg: str) -> None:
            try:
                resultado["final"] = run_pipeline(
                    agent, cfg_t, msg, [],
                    on_event=eventos.append, cancel=cancel)
            except Exception as exc:  # noqa: BLE001
                resultado["erro"] = f"{exc.__class__.__name__}: {exc}"

        for msg in c["msgs"]:
            eventos.clear()
            resultado["final"], resultado["erro"] = "", None
            th = threading.Thread(target=_rodar, args=(msg,), daemon=True)
            th.start()
            th.join(timeout)
            if th.is_alive():
                cancel.set()
                estourou = True
                break
        if estourou:
            print_fn(f"  ✖ {c['nome']} — excedeu {timeout}s (cancelado)")
            falhas += 1
            continue
        f = resultado["final"]
        if resultado["erro"]:
            print_fn(f"  ✖ {c['nome']} — erro: {resultado['erro']}")
            falhas += 1
            continue
        problemas = list(c["checa"](f, eventos))
        if any(r in f.lower() for r in _RECUSA):
            problemas.append("recusa em vez de resposta")
        if problemas:
            falhas += 1
            print_fn(f"  ✖ {c['nome']}")
            for pr in problemas:
                print_fn(f"      · {pr}")
            print_fn(f"      entrega: {f[:200]!r}")
        else:
            ok += 1
            print_fn(f"  ✔ {c['nome']}")
    print_fn(f"\nselftest: {ok} ✔ · {falhas} ✖ "
             f"(modelo {cfg_t.model}, {timeout}s/cenário)")
    if falhas:
        print_fn("✖ comportamento reprovado — mande este relatório "
                 "para o responsável pelo agente.")
        return 1
    print_fn("✔ comportamento de campo aprovado com LLM real.")
    return 0
