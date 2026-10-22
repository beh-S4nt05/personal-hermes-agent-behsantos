"""`hermes selftest` — bateria de aceitação com LLM REAL (v3.13.3).

A suíte tests/run_all.py roda 100% em mock: garante o ESQUELETO, mas
não o comportamento do modelo. Este selftest manda pedidos reais ao
modelo configurado e verifica o que importa no campo — entrega
não-vazia, sem recusa, com evidência real (ferramenta usada, código
executado, número certo, memória guardada).

    hermes selftest                 # bateria com o modelo configurado
    hermes selftest --all-models    # 🧪 matriz: TODOS os modelos instalados
                                    #     × 5 cenários + tempo + recomendação

Requisitos: Ollama ligado. Sem Ollama (ou em mock), PULA limpo (exit 0).
"""
from __future__ import annotations

import tempfile
import threading
import time

# marcas da falha de campo observada no operador (v3.13.1/v3.13.2):
# as frases EXATAS que o hermes3:8b usou quando entregou nada
_RECUSA = ["não vou repetir", "pronto para ajudar",
           "não vou repetir chamadas", "sem repetir o conteúdo"]


def _evidencias(events: list[dict]) -> list[str]:
    return [str(e.get("name") or "") for e in events
            if e.get("type") == "tool_start"]


def _setup_dados(cfg) -> None:
    from pathlib import Path
    d = Path(cfg.workdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "dados.csv").write_text(
        "produto,valor\ncafe,10\nlivro,20\nteclado,30\n", encoding="utf-8")


def _cenarios() -> list[dict]:
    """Cada cenário: msgs em sequência; checa(final, eventos) -> list[str]
    de problemas (vazio = aprovado)."""
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


def _run_cenario(agent, cfg_t, c: dict, timeout: int
                 ) -> tuple[bool, list[str], str, float]:
    """Roda um cenário; devolve (ok, problemas, entrega, duração_s).
    Closures com bind por default-arg (B023-safe)."""
    if c.get("setup"):
        c["setup"](cfg_t)
    eventos: list[dict] = []
    cancel = threading.Event()
    resultado = {"final": "", "erro": None}

    def _rodar(msg, _r=resultado, _e=eventos, _c=cancel):
        from .orchestrator import run_pipeline
        try:
            _r["final"] = run_pipeline(agent, cfg_t, msg, [],
                                       on_event=_e.append, cancel=_c)
        except Exception as exc:  # noqa: BLE001
            _r["erro"] = f"{exc.__class__.__name__}: {exc}"

    t0 = time.time()
    estourou = False
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
    dur = time.time() - t0
    if estourou:
        return False, [f"excedeu {timeout}s (cancelado)"], "", dur
    f = resultado["final"]
    if resultado["erro"]:
        return False, [f"erro: {resultado['erro']}"], f, dur
    problemas = list(c["checa"](f, eventos))
    if any(r in f.lower() for r in _RECUSA):
        problemas.append("recusa em vez de resposta")
    return (not problemas), problemas, f, dur


def _recomenda(resultados: dict[str, dict[str, bool]],
               tempos: dict[str, float]) -> str | None:
    """Melhor modelo: mais cenários ✔; empate → mais rápido."""
    if not resultados:
        return None
    def chave(m):
        oks = sum(1 for v in resultados[m].values() if v)
        return (-oks, tempos.get(m, 9e9))
    ordenados = sorted(resultados, key=chave)
    melhor = ordenados[0]
    if sum(1 for v in resultados[melhor].values() if v) == 0:
        return None
    return melhor


def run(cfg, timeout: int = 240, print_fn=print,
        all_models: bool = False) -> int:
    """Roda a bateria; devolve exit code (0 = verde OU pulado)."""
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

    from .config import Config
    from .agent import Agent

    modelos = ([str(m) for m in st["models"]] if all_models
               else [str(cfg.model)])
    if all_models:
        print_fn(f"🧪 hermes selftest --all-models · {len(modelos)} modelo(s) "
                 f"instalado(s) × {len(_cenarios())} cenários\n")
    else:
        print_fn(f"🧪 hermes selftest · modelo real: {cfg.model}")
        print_fn("  bateria de campo: entrega não-vazia, sem recusa, com "
                 "evidência real\n")

    resultados: dict[str, dict[str, bool]] = {}
    tempos: dict[str, float] = {}
    cenarios = _cenarios()
    for modelo in modelos:
        cfg_t = Config(data_dir=tempfile.mkdtemp(prefix="hermes-selftest-"))
        cfg_t.update({"model": modelo, "orchestrator_model": "",
                      "reviewer_model": "", "executor_model": "",
                      "creation_approval": False})
        agent = Agent(cfg_t)
        resultados[modelo] = {}
        t0m = time.time()
        for c in cenarios:
            ok, problemas, f, _dur = _run_cenario(agent, cfg_t, c, timeout)
            resultados[modelo][c["nome"]] = ok
            if not all_models:                    # modo detalhado
                if ok:
                    print_fn(f"  ✔ {c['nome']}")
                else:
                    print_fn(f"  ✖ {c['nome']}")
                    for pr in problemas:
                        print_fn(f"      · {pr}")
                    print_fn(f"      entrega: {f[:200]!r}")
        tempos[modelo] = time.time() - t0m

    if all_models:
        nomes_c = [c["nome"].split(" (")[0] for c in cenarios]
        cab = f"  {'modelo':<22}" + "".join(f"{n[:9]:>11}" for n in nomes_c) \
              + f"{'tempo':>9}"
        print_fn(cab)
        print_fn("  " + "-" * (len(cab) - 2))
        for m in modelos:
            linha = f"  {m:<22}"
            for c in cenarios:
                linha += f"{'✔' if resultados[m][c['nome']] else '✖':>11}"
            linha += f"{tempos[m]:>7.0f}s"
            print_fn(linha)
        melhor = _recomenda(resultados, tempos)
        if melhor:
            oks = sum(1 for v in resultados[melhor].values() if v)
            print_fn(f"\n  🏆 melhor comportamento: {melhor} "
                     f"({oks}/{len(cenarios)} ✔, {tempos[melhor]:.0f}s no total)")
            print_fn("     aplique com: hermes config set model "
                     f"{melhor} && hermes models auto")
        falhas_total = sum(1 for m in resultados
                           for v in resultados[m].values() if not v)
        print_fn(f"\nselftest matriz: {len(modelos)} modelo(s) · "
                 f"{falhas_total} reprovação(ões) no total")
        if falhas_total:
            print_fn("✖ mande esta matriz para o responsável pelo agente.")
            return 1
        print_fn("✔ todos os modelos aprovados em todos os cenários.")
        return 0

    # modo único
    m = modelos[0]
    falhas = sum(1 for v in resultados[m].values() if not v)
    print_fn(f"\nselftest: {len(cenarios) - falhas} ✔ · {falhas} ✖ "
             f"(modelo {m}, {timeout}s/cenário)")
    if falhas:
        print_fn("✖ comportamento reprovado — mande este relatório "
                 "para o responsável pelo agente.")
        return 1
    print_fn("✔ comportamento de campo aprovado com LLM real.")
    return 0
