# -*- coding: utf-8 -*-
"""🏟️ Arena de provedores — v4.3.0 (PR #6).

"Qual modelo grátis resolve melhor ESTA task?" — medido, não achismo.

A MESMA task roda em TODOS os contendores do pool gratuito, em MODO
RESPOSTA (completion pura: sem ferramentas, sem single-writer, sem
escrever NADA no disco do projeto), com cronômetro. O REVISOR então
ranqueia os resultados lado a lado e recomenda o vencedor.

Privacidade (D2 — lei, igual ao resto do sistema):
- a task vai DLP-mascarada (varredura.mascarar) em QUALQUER payload
  externo: código e segredos jamais saem da máquina;
- o julgamento de qualidade é do modelo LOCAL (Ollama — nada sai);
  indisponível/JSON inválido → heurística objetiva medida.

Nada da arena é persistido: o resultado vive na memória/stdout. A única
escrita é a linha padrão de auditoria no logs/agent.log (regra R8).
"""
from __future__ import annotations

import time

# ------------------------------------------------------------- mock pool
_MOCK_POOL = ("groq", "gemini", "llm7")
_MOCK_MODELO = {"groq": "llama-3.1-8b-instant",
                "gemini": "gemini-2.5-flash",
                "llm7": "gpt-oss:20b"}
# textos/latências determinísticos → ranking estável em testes e demo
_MOCK_TEXTO = {
    "groq": ("Resposta completa em três pontos: 1) o conceito pedido é "
             "explicado de forma direta, com definição e contexto de uso; "
             "2) um exemplo prático ilustra o caso típico e o contra-exemplo "
             "o caso-limite; 3) resumo final em uma frase, pronto para ação."),
    "gemini": ("Resposta em dois pontos: definição objetiva do conceito "
               "pedido, seguida de um exemplo prático de uso cotidiano."),
    "llm7": "Resposta curta: veja a documentação oficial.",
}
_MOCK_LATENCIA = {"groq": 0.02, "gemini": 0.05, "llm7": 0.07}


class _ContendenteMock:
    """Contendente fake determinístico (modo mock/demo): resposta e
    latência fixas por provedor — ranking estável, zero rede."""

    is_external = True
    simulated = True

    def __init__(self, nome: str):
        self.nome = nome
        self.model = _MOCK_MODELO.get(nome, "mock")
        self.prompts: list[str] = []       # gravado p/ testes (T149/T153)

    def chat_stream(self, model, messages, **_kw):
        time.sleep(_MOCK_LATENCIA.get(self.nome, 0.04))
        self.prompts.append(messages[-1].get("content", "") if messages else "")
        yield {"message": {"content": _MOCK_TEXTO.get(self.nome,
                                                      "resposta mock")}}


def candidatos(cfg) -> list[tuple[str, object]]:
    """[(nome, cliente)] aptos à arena: com chave em secrets/ ou anônimos
    (sem_chave). Em mock, pool fake determinístico (demo/testes sem rede)."""
    if cfg.mock:
        return [(nome, _ContendenteMock(nome)) for nome in _MOCK_POOL]
    out: list[tuple[str, object]] = []
    try:
        from .llm_providers import REGISTRY, api_key, ExternalClient
        for nome, info in REGISTRY.items():
            if info.get("sem_chave") or api_key(cfg, nome):
                try:
                    out.append((nome, ExternalClient(cfg, nome)))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------- D2
def _mascarar_task(tarefa: str) -> str:
    try:
        from .varredura import mascarar
        return mascarar(tarefa)
    except Exception:  # noqa: BLE001
        return tarefa


def _completion(cli, modelo: str, prompt: str) -> str:
    """1 completion pura (modo resposta). Levanta em caso de falha."""
    partes = []
    for ch in cli.chat_stream(modelo, [{"role": "user", "content": prompt}]):
        t = (ch.get("message") or {}).get("content") or ""
        if t:
            partes.append(t)
    return "".join(partes).strip()


# ------------------------------------------------------------- revisor
_CRITERIOS = ["sucesso (respondeu sem erro)",
              "adesão (resposta desenvolvida, ≥60 chars)",
              "tamanho (banda saudável 60–6000 chars)",
              "rapidez (≤2× o mais rápido; 2–4× média)"]

_PROMPT_JULG = """Você é o REVISOR da arena. A task entregue aos modelos foi:
"{task}"

Abaixo, as respostas lado a lado:

{bloco}

Ranqueie por QUALIDADE REAL da resposta para a task: correção,
completude e utilidade. Responda APENAS com JSON:
{{"ordem": ["<letra da melhor>", "..."], "motivos": {{"<letra>": "motivo curto"}}}}"""


def _julgar_local(cfg, prompt: str) -> str:
    """1 completion no modelo LOCAL (juiz) — nada sai da máquina (D2).
    Em mock o juiz é simulado e não julga: devolve vazio (a heurística
    assume, mantendo testes/demo determinísticos e rápidos)."""
    if cfg.mock:
        return ""
    from .ollama_client import OllamaClient, timeout_resposta
    cli = OllamaClient(cfg.ollama_url, timeout=timeout_resposta(cfg))
    return _completion(cli, "", prompt)


def _nota_heuristica(r: dict, mais_rapido_ms: float) -> tuple[int, str]:
    """Nota 0–10 por critérios OBJETIVOS medidos (sem achismo)."""
    nota, partes = 4, ["respondeu"]
    n = r["chars"]
    if n >= 60:
        nota += 2
        partes.append("resposta desenvolvida")
    elif n >= 10:
        nota += 1
        partes.append("resposta curta")
    else:
        partes.append("resposta quase vazia")
    if 60 <= n <= 6000:
        nota += 2
        partes.append("tamanho saudável")
    else:
        nota += 1
        partes.append("tamanho fora da banda")
    razao = (r["tempo_ms"] or 1.0) / max(mais_rapido_ms, 1.0)
    if razao <= 2:
        nota += 2
        partes.append("rápido")
    elif razao <= 4:
        nota += 1
        partes.append("velocidade média")
    else:
        partes.append("lento")
    return nota, " · ".join(partes)


def revisar(cfg, tarefa: str, resultados: list[dict], _local=None) -> dict:
    """O REVISOR ranqueia os resultados lado a lado e recomenda.

    1) tenta o juiz LOCAL (prompt com as respostas rotuladas A/B/C…);
       JSON válido com todas as letras → ranking do revisor;
    2) indisponível/inválido → heurística objetiva (critérios medidos).
    Anota ``nota`` (0–10) e ``veredito`` em cada resultado in-place.
    """
    letras = "ABCDEF"
    vivos = [r for r in resultados if r["ok"]]
    metodo, ordem_letras, motivos = "heuristica", None, {}
    if len(vivos) >= 2:
        fn = _local if _local is not None else (lambda p: _julgar_local(cfg, p))
        bloco = "\n\n".join(
            f"RESPOSTA {letras[i]} ({r['provedor']}):\n{r['trecho'][:600]}"
            for i, r in enumerate(vivos[:6]))
        try:
            from .specialists import _extrair_json
            raw = fn(_PROMPT_JULG.format(task=_mascarar_task(tarefa)[:400],
                                         bloco=bloco))
            j = _extrair_json(raw or "") or {}
            ordem = [str(x).strip().upper() for x in (j.get("ordem") or [])]
            esperado = [letras[i] for i in range(min(len(vivos), 6))]
            if ordem and sorted(ordem) == sorted(esperado):
                ordem_letras = ordem
                motivos = {str(k).strip().upper(): str(v)
                           for k, v in (j.get("motivos") or {}).items()}
                metodo = "revisor-local"
        except Exception:  # noqa: BLE001
            ordem_letras = None
    mais_rapido = min((r["tempo_ms"] for r in vivos), default=1.0) or 1.0
    for r in resultados:
        if not r["ok"]:
            r["nota"] = 0
            r["veredito"] = f"falhou — {r['erro'][:80] or 'sem resposta'}"
    for i, r in enumerate(vivos):
        nota_h, why = _nota_heuristica(r, mais_rapido)
        if ordem_letras is not None:
            letra = letras[i]
            pos = ordem_letras.index(letra)
            r["nota"] = max(1, 10 - 2 * pos)
            extra = motivos.get(letra, "").strip()
            r["veredito"] = f"{extra or f'rank {pos + 1} do revisor'} · {why}"
        else:
            r["nota"] = nota_h
            r["veredito"] = why
    return {"metodo": metodo, "criterios": list(_CRITERIOS)}


# ------------------------------------------------------------- rodar
def rodar(cfg, tarefa: str, n: int = 1, _pool=None, _local=None) -> dict:
    """Roda a MESMA task em todos os contendores e devolve o ranking.

    - modo resposta: completion pura, SEM ferramentas, SEM escrita no
      disco do projeto (resultado só na memória/stdout);
    - D2: a task é DLP-mascarada ANTES de qualquer payload externo;
    - ``n`` rodadas por contendor → tempo médio (estabilidade);
    - ``_pool``/``_local`` injetáveis (testes), padrão = pool real/mock.
    """
    tarefa = (tarefa or "").strip()
    if not tarefa:
        return {"ok": False,
                "msg": 'task vazia — uso: betterme arena "<task>" [--n 3]'}
    n = max(1, int(n or 1))
    pool = _pool if _pool is not None else candidatos(cfg)
    if not pool:
        return {"ok": False,
                "msg": "nenhum contendor no pool — ative um provedor grátis: "
                       "betterme provider set groq"}
    task_ext = _mascarar_task(tarefa)          # D2 — sempre, antes de sair
    resultados: list[dict] = []
    for nome, cli in pool:
        modelo = str(getattr(cli, "model", "") or "")
        tempos: list[float] = []
        texto, erro = "", ""
        for _i in range(n):
            t0 = time.perf_counter()
            try:
                texto = _completion(cli, modelo, task_ext)
            except Exception as exc:  # noqa: BLE001
                erro = f"{exc}"[:200]
                break
            tempos.append((time.perf_counter() - t0) * 1000.0)
        if tempos and not texto:
            erro = "resposta vazia"
        resultados.append({
            "provedor": nome, "modelo": modelo,
            "ok": bool(tempos) and bool(texto),
            "tempo_ms": round(sum(tempos) / len(tempos), 1) if tempos else 0.0,
            "chars": len(texto or ""),
            "trecho": (texto or "")[:200],
            "erro": erro,
        })
    revisao = revisar(cfg, tarefa, resultados, _local=_local)
    resultados.sort(key=lambda r: (-r.get("nota", 0), r["tempo_ms"]))
    vencedor = (resultados[0]["provedor"]
                if resultados and resultados[0].get("nota", 0) > 0 else None)
    _auditar(cfg, tarefa, resultados, revisao, vencedor)
    return {"ok": True, "task_chars": len(tarefa),
            "mascarada": task_ext != tarefa, "n": n,
            "resultados": resultados, "vencedor": vencedor, **revisao}


def _auditar(cfg, tarefa, resultados, revisao, vencedor) -> None:
    """R8 (tudo auditado): 1 linha no agent.log — sem conteúdo da task."""
    try:
        from . import activity
        activity.log(cfg, "arena",
                     f"🏟 {len(resultados)} contendores · vencedor: "
                     f"{vencedor or 'nenhum'} · revisor: "
                     f"{revisao.get('metodo')} · task {len(tarefa)} chars")
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------- CLI
def cmd(tarefa: str, n: int, cfg) -> int:
    """`betterme arena "<task>" [--n 3]` — tabela + vencedor."""
    res = rodar(cfg, tarefa, n=n)
    if not res.get("ok"):
        print(f"ℹ️  {res.get('msg', 'nada a fazer')}")
        return 0
    print(f"🏟️  ARENA — task de {res['task_chars']} chars"
          f"{' (DLP aplicado)' if res['mascarada'] else ''}"
          f" · {len(res['resultados'])} contendores × {res['n']} rodada(s)"
          f" · revisor: {res['metodo']}")
    print()
    print(f"  {'#':>2}  {'provedor':<11} {'tempo':>8}  {'nota':>4}  "
          f"{'veredito do revisor':<44} trecho")
    for i, r in enumerate(res["resultados"], 1):
        t = f"{r['tempo_ms']:.0f}ms" if r["ok"] else "—"
        print(f"  {i:>2}  {r['provedor']:<11} {t:>8}  {r['nota']:>4}  "
              f"{r['veredito'][:44]:<44} {r['trecho'][:36]!r}")
    print()
    if res.get("vencedor"):
        v = next(r for r in res["resultados"]
                 if r["provedor"] == res["vencedor"])
        print(f"🏆 vencedor: {v['provedor']} ({v['modelo']}) — nota {v['nota']}")
        print(f"   critérios: {'; '.join(res['criterios'])}")
    else:
        print("🏆 nenhum vencedor — todos os contendores falharam.")
    return 0
