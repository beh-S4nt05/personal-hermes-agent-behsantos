# -*- coding: utf-8 -*-
"""🔍 Revisão de diff — v4.5.0 (PR #8, E4).

`betterme revisar` (ou a ferramenta `revisar_diff` no chat): o REVISOR
lê o `git diff HEAD` e emite veredito com arquivo:linha.

GATE ÚNICO pré-push (integração com a varredura):
1. PARTE OBJETIVA (zero LLM): varredura do diff — segredos/CPF/e-mails
   com severidade CRITICO reprovam o diff imediatamente.
2. PARTE SUBJETIVA (LLM LOCAL): o revisor analisa o diff e devolve
   JSON {aprovado, problemas[{arquivo, linha, problema, gravidade}],
   resumo}. Cada problema é VALIDADO contra o diff (o arquivo precisa
   estar nele; linha > 0) — evidência que não confere é descartada.

D2 (lei): código-fonte JAMAIS sai da máquina — a análise do diff roda
no Ollama LOCAL (ou no simulado, em mock). Nada vai ao pool gratuito.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_MAX_DIFF = 60_000        # teto do diff enviado ao revisor local

_PROMPT = """Você é o REVISOR de código do Betterme. Revise o diff abaixo
(quando: antes de commitar/pushar) e procure bugs reais, quebras de
contrato, riscos de segurança e regressões. Não aponte estilo.

DIFF:
```
{diff}
```

Responda APENAS com JSON:
{{"aprovado": true|false,
  "problemas": [{{"arquivo": "caminho", "linha": 12,
                  "problema": "descrição curta",
                  "gravidade": "alta|media|baixa"}}],
  "resumo": "uma frase"}}"""


def _git_diff(raiz: Path) -> str:
    """Diff não commitado (staged + unstaged) vs HEAD."""
    partes = []
    for arg in (["diff", "HEAD"], ["diff", "--cached"]):
        try:
            out = subprocess.run(["git"] + arg, cwd=raiz,
                                 capture_output=True, text=True,
                                 timeout=30)
        except Exception:  # noqa: BLE001
            continue
        if out.returncode != 0 or not out.stdout:
            continue
        partes.append(out.stdout)
    return "".join(partes)


def _veredito_simulado() -> dict:
    """Mock/demo: veredito determinístico do revisor local simulado."""
    return {"aprovado": True, "problemas": [],
            "resumo": "diff revisado localmente (simulado) — nenhum "
                      "problema estrutural encontrado"}


def _julgar_local(cfg, diff: str) -> dict:
    """Roda o revisor no LLM LOCAL (D2 — diff tem código, nada sai)."""
    if cfg.mock:
        return _veredito_simulado()
    from .ollama_client import OllamaClient, timeout_resposta
    cli = OllamaClient(cfg.ollama_url, timeout=timeout_resposta(cfg))
    partes = []
    for ch in cli.chat_stream("", [{"role": "user",
                                    "content": _PROMPT.format(
                                        diff=diff[:_MAX_DIFF])}]):
        t = (ch.get("message") or {}).get("content") or ""
        if t:
            partes.append(t)
    from .specialists import _extrair_json
    j = _extrair_json("".join(partes).strip() or "")
    if not j or "aprovado" not in j:
        return {"aprovado": None, "problemas": [],
                "resumo": "revisor local indisponível/inválido — "
                          "vale só a varredura objetiva"}
    return j


def _validar_problemas(problemas: list, diff: str) -> list[dict]:
    """Evidência validada contra o diff: arquivo presente + linha > 0."""
    validos = []
    for p in problemas or []:
        if not isinstance(p, dict):
            continue
        arq = str(p.get("arquivo", "")).strip()
        try:
            lin = int(p.get("linha") or 0)
        except (TypeError, ValueError):
            lin = 0
        txt = str(p.get("problema", "")).strip()
        if not arq or lin <= 0 or not txt or arq not in diff:
            continue
        sev = str(p.get("gravidade", "media")).lower()
        if sev not in ("alta", "media", "baixa"):
            sev = "media"
        validos.append({"arquivo": arq, "linha": lin, "problema": txt[:200],
                        "gravidade": sev})
    return validos


def revisar(cfg, raiz: Path | None = None, _local=None) -> dict:
    """GATE ÚNICO de entrega: varredura objetiva + revisor local.
    Devolve {ok, aprovado, problemas, criticos, achados, resumo, metodo}."""
    raiz = Path(raiz) if raiz else Path.cwd()
    resultado = {"ok": False, "aprovado": False, "problemas": [],
                 "criticos": 0, "achados": 0, "resumo": "", "metodo": ""}
    diff = _git_diff(raiz)
    if not diff:
        resultado["msg"] = ("nenhum diff para revisar (git diff HEAD "
                            "vazio — já commitado?)")
        return resultado
    # 1) parte objetiva: varredura (CRITICO reprova na hora)
    from .varredura import varrer_diff
    achados = varrer_diff(cfg, raiz)
    criticos = [a for a in achados if a.severidade == "CRITICO"]
    resultado["achados"] = len(achados)
    resultado["criticos"] = len(criticos)
    # 2) parte subjetiva: revisor LOCAL (D2 — código não sai da máquina)
    if _local is not None:
        from .specialists import _extrair_json
        j = _extrair_json(_local(_PROMPT.format(diff=diff[:_MAX_DIFF]))
                          or "") or {}
    else:
        j = _julgar_local(cfg, diff)
    metodo = ("simulado" if (cfg.mock and _local is None)
              else "revisor-local")
    if not j or "aprovado" not in j:
        j, metodo = {"aprovado": None, "problemas": [], "resumo": ""}, \
            "so-varredura"
    problemas = _validar_problemas(j.get("problemas"), diff)
    graves = [p for p in problemas if p["gravidade"] == "alta"]
    # R3 (evidência validada): reprovar exige SUBSTÂNCIA — crítico da
    # varredura, problema grave, ou veredito contra COM problema válido.
    # Juiz que rejeita só com evidência inventada (descartada) não bloqueia.
    reprovado = (bool(criticos) or bool(graves)
                 or (j.get("aprovado") is False and bool(problemas)))
    aprovado = not reprovado
    resultado.update({
        "ok": True, "aprovado": aprovado, "problemas": problemas,
        "resumo": str(j.get("resumo", ""))[:300], "metodo": metodo,
        "diff_chars": len(diff)})
    try:
        from . import activity
        activity.log(cfg, "revisar",
                     f"🔍 diff {len(diff)} chars · {'✔ aprovado' if aprovado else '✖ reprovado'}"
                     f" · {len(problemas)} problema(s) · {len(criticos)} "
                     f"crítico(s) · {metodo}")
    except Exception:  # noqa: BLE001
        pass
    return resultado


def revisar_texto(r: dict) -> str:
    """Formata o veredito para CLI/tool."""
    if not r.get("ok"):
        return f"ℹ️ {r.get('msg', 'nada para revisar')}"
    linhas = [f"🔍 REVISÃO DE DIFF — {r.get('diff_chars', 0)} chars · "
              f"método: {r['metodo']}"]
    linhas.append(f"🛡 varredura: {r['achados']} achado(s) · "
                  f"{r['criticos']} crítico(s)")
    for p in r["problemas"]:
        linhas.append(f"  • {p['arquivo']}:{p['linha']} [{p['gravidade']}] "
                      f"{p['problema']}")
    if r["resumo"]:
        linhas.append(f"🧠 resumo: {r['resumo']}")
    linhas.append("✔ APROVADO" if r["aprovado"] else
                  "✖ REPROVADO — corrija antes do commit/push")
    return "\n".join(linhas)


# ------------------------------------------------------------- CLI
def cmd(args, cfg) -> None:
    """`betterme revisar` — gate único pré-push (exit 1 se reprovado)."""
    raiz = getattr(args, "raiz", None) or Path.cwd()
    r = revisar(cfg, Path(raiz))
    print(revisar_texto(r))
    if r.get("ok") and not r["aprovado"]:
        raise SystemExit(1)
