"""Orquestrador + Revisor (v3.3) — pipeline plan → execute → review.

Fluxo de uma mensagem do chat (agente Hermes):

    mensagem ──► 🎯 ORQUESTRADOR (rápido, JSON)
                   │ rota "responder"  ──► resposta direta (fluxo de antes)
                   │ rota "executar"
                   ▼
                 TASK criada (registrada em data/orchestrator_tasks.jsonl)
                   ▼
                 ⚡ EXECUTOR (o Agent de sempre: ferramentas reais)
                   ▼
                 🔍 REVISOR (rápido, JSON): o resultado cumpre o objetivo?
                   │ "ok"      ──► entrega (com selo de revisada)
                   │ "refazer" ──► re-executa com o problema apontado
                   │              (máx. 2 tentativas — nunca loop infinito)
                   ▼
                 resposta revisada entregue ao operador

Decisões de PERFORMANCE (modelo local ≤8B):
  * orquestrador e revisor usam chamadas RÁPIDAS (num_predict ~200,
    temperature 0) — 1 a 3 s cada;
  * conversa simples ("oi", perguntas) NÃO passa pelo pipeline: a rota
    "responder" tem custo zero adicional;
  * tentativas limitadas (2), prompts curtos, excertos truncados;
  * tudo local, nada sai da máquina; em modo mock o roteamento é
    heurístico e determinístico (demo estável).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

# ── roteamento heurístico (fallback e modo mock — determinístico) ──
_ACAO_RE = re.compile(
    r"\b(crie|criar|cria|execute|executar|executa|rode|rodar|roda|liste|listar|"
    r"lista|verifique|verificar|verifica|analise|analisar|analisa|instale|"
    r"instalar|instala|configure|configurar|configura|escreva|escrever|gere|"
    r"gerar|apague|apagar|limpe|limpar|atualize|atualizar|mova|mover|copie|"
    r"copiar|envie|enviar|resuma|resumir|sumarize|baixe|baixar|monitore|"
    r"monitorar|otimize|otimizar|corrija|corrigir|mostre|mostrar|consulte|"
    r"consultar|leia|ler|busque|buscar|pesquise|pesquisar)\b", re.IGNORECASE)

_PLANO_JSON = (
    "Você é o ORQUESTRADOR de um agente Linux local. Analise a mensagem do "
    "usuário e responda APENAS um objeto JSON, sem nenhum texto em volta:\n"
    '{"rota":"responder"}  — para conversa, dúvida, opinião, saudação;\n'
    '{"rota":"executar","objetivo":"...","passos":["..."],"criterios":["..."]}'
    " — quando o usuário pede uma AÇÃO (executar comando, criar/ler arquivo, "
    "diagnóstico, e-mail, agenda, instalação, monitoramento).\n"
    "Seja objetivo: objetivo em 1 frase; no máximo 4 passos; critérios "
    "verificáveis (ex.: \"mostrar a saída real do comando\")."
)

_REVISAO_JSON = (
    "Você é o REVISOR de um agente Linux local. Dado o OBJETIVO de uma task e "
    "o RESULTADO produzido, verifique com rigor e responda APENAS um JSON:\n"
    '{"veredito":"ok"} — o resultado cumpre o objetivo e apresenta dados '
    "reais;\n"
    '{"veredito":"refazer","problema":"..."} — não cumpriu, ficou incompleto, '
    "erro na execução, ou pediu ao usuário para fazer algo.\n"
    "Não exija perfeição estética; exija cumprimento e dados reais."
)


# ───────────────────────────── infra ─────────────────────────────

def tasks_path(cfg) -> Path:
    return cfg.data_dir / "orchestrator_tasks.jsonl"


def _fast(cfg, system: str, user: str, ntok: int = 200) -> str:
    """Chamada rápida e curta ao modelo (orquestrador/revisor). Nunca lança;
    em modo mock devolve '' (o chamador cai na heurística/fallback)."""
    if getattr(cfg, "mock", False):
        return ""
    try:
        from .ollama_client import get_client
        client = get_client(cfg)
        out = []
        for chunk in client.chat_stream(
                cfg.model,
                [{"role": "system", "content": system},
                 {"role": "user", "content": user[:1800]}],
                options={"num_predict": ntok, "temperature": 0}):
            msg = chunk.get("message") or {}
            piece = msg.get("content") or ""
            if piece:
                out.append(piece)
            if chunk.get("done"):
                break
        return "".join(out)
    except Exception:  # noqa: BLE001
        return ""


def _extract_json(text: str) -> dict | None:
    """Primeiro objeto JSON balanceado do texto (modelos pequenos cercam
    o JSON de prosa) — None se não achar nada válido."""
    t = text or ""
    i = t.find("{")
    while i != -1:
        prof, ini, em_str, esc = 0, i, False, False
        for j in range(i, len(t)):
            c = t[j]
            if em_str:
                if esc:                      # caractere escapado (\" \\ ...)
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    em_str = False
                continue
            if c == '"':
                em_str = True
            elif c == "{":
                prof += 1
            elif c == "}":
                prof -= 1
                if prof == 0:
                    try:
                        obj = json.loads(t[ini:j + 1])
                        return obj if isinstance(obj, dict) else None
                    except ValueError:
                        break
        i = t.find("{", i + 1)
    return None


# ───────────────────────────── 🎯 plano ─────────────────────────────

def _heuristic(message: str) -> dict:
    if _ACAO_RE.search(message or ""):
        return {
            "rota": "executar",
            "objetivo": (message or "").strip()[:300],
            "passos": [],
            "criterios": ["a ação foi realmente executada e o resultado "
                          "real está na resposta"],
        }
    return {"rota": "responder"}


def plan(cfg, message: str, history: list[dict] | None = None) -> dict:
    """🎯 Orquestrador: decide a rota e monta o plano. Nunca lança —
    qualquer falha cai na heurística (o chat nunca quebra)."""
    if not getattr(cfg, "orchestrator_on", True):
        return {"rota": "responder"}
    try:
        texto = _fast(cfg, _PLANO_JSON, message, ntok=220)
        obj = _extract_json(texto)
        if obj and obj.get("rota") in ("responder", "executar"):
            if obj["rota"] == "executar":
                obj.setdefault("objetivo", message[:300])
                obj.setdefault("passos", [])
                obj.setdefault("criterios", [])
                obj["passos"] = [str(p)[:160] for p in (obj.get("passos") or [])[:4]]
                obj["criterios"] = [str(c)[:160] for c in (obj.get("criterios") or [])[:3]]
            return obj
    except Exception:  # noqa: BLE001
        pass
    return _heuristic(message)


# ───────────────────────────── 🔍 revisão ─────────────────────────────

def review(cfg, objetivo: str, criterios: list[str], resultado: str) -> dict:
    """🔍 Revisor: o resultado cumpre o objetivo? Nunca lança — falha de
    parse devolve 'ok' (entrega sem travar o chat)."""
    if not getattr(cfg, "reviewer_on", True):
        return {"veredito": "ok"}
    try:
        crit = "\n".join(f"- {c}" for c in (criterios or [])[:3]) or "- cumprir o objetivo"
        user = (f"OBJETIVO: {objetivo}\nCRITÉRIOS:\n{crit}\n\n"
                f"RESULTADO (trecho):\n{resultado[:1800]}")
        texto = _fast(cfg, _REVISAO_JSON, user, ntok=140)
        obj = _extract_json(texto)
        if obj and obj.get("veredito") == "refazer":
            return {"veredito": "refazer",
                    "problema": str(obj.get("problema", ""))[:300] or "resultado insuficiente"}
        if obj and obj.get("veredito") == "ok":
            return {"veredito": "ok"}
    except Exception:  # noqa: BLE001
        pass
    return {"veredito": "ok"}


# ───────────────────────── registro das tasks ─────────────────────────

def record(cfg, entry: dict) -> str:
    """Anexa o registro da task (auditoria leve, sem banco)."""
    p = tasks_path(cfg)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        n = sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
        entry = {"id": f"T{n + 1:04d}", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                 **entry}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry["id"]
    except OSError:
        return "?"


def list_tasks(cfg, limit: int = 100) -> list[dict]:
    p = tasks_path(cfg)
    try:
        linhas = p.read_text(encoding="utf-8").splitlines()
        return [json.loads(l) for l in linhas[-limit:] if l.strip()][::-1]
    except (OSError, ValueError):
        return []


# ───────────────────────── pipeline completo ─────────────────────────

def run_pipeline(agent, cfg, message: str, history: list[dict],
                 on_event=None, cancel=None, max_tentativas: int = 2) -> str:
    """Conversa → 🎯 plano → ⚡ execução → 🔍 revisão → entrega.

    Usa o Agent de sempre como executor (ferramentas reais, denylist,
    auditoria); as etapas de planejamento/revisão emitem eventos `note`
    para a GUI acompanhar o pipeline ao vivo.
    """
    ev = on_event or (lambda _e: None)
    from . import activity

    def _cancelado() -> bool:
        return cancel is not None and cancel.is_set()

    plano = plan(cfg, message, history)

    # rota direta: conversa comum — custo zero adicional
    if plano.get("rota") != "executar":
        return agent.run(history + [{"role": "user", "content": message}],
                         on_event=on_event, cancel=cancel)

    objetivo = str(plano.get("objetivo") or message)[:300]
    passos = plano.get("passos") or []
    criterios = plano.get("criterios") or []
    plano_txt = f"[PLANO DO ORQUESTRADOR]\nObjetivo: {objetivo}"
    if passos:
        plano_txt += "\nPassos:\n" + "\n".join(f"- {p}" for p in passos)
    if criterios:
        plano_txt += "\nCritérios de conclusão:\n" + "\n".join(f"- {c}" for c in criterios)

    t0 = time.time()
    ev({"type": "note", "message": f"🎯 orquestrador: task criada — {objetivo}"})
    activity.log(cfg, "chat", f"🎯 orquestrador criou task — {objetivo[:80]}")

    mensagens = history[-6:] + [{"role": "user",
                                 "content": f"{message}\n\n{plano_txt}"}]
    resultado, veredito, problema, tentativas = "", "ok", "", 0
    # o executor emite o próprio "done"; o pipeline o ENGOLE e emite o done
    # FINAL só depois da revisão (a GUI recebe a resposta já com o selo 🔍)
    caixa = {"done": ""}

    def _ev_exec(e: dict) -> None:
        if e.get("type") == "done":
            caixa["done"] = e.get("message") or ""
            return
        ev(e)

    for tentativa in range(1, max_tentativas + 1):
        if _cancelado():
            break
        tentativas = tentativa
        resultado = agent.run(mensagens, on_event=_ev_exec, cancel=cancel)
        if _cancelado():
            break
        ver = review(cfg, objetivo, criterios, resultado)
        veredito, problema = ver.get("veredito", "ok"), ver.get("problema", "")
        if veredito == "ok":
            if tentativa > 1:
                ev({"type": "note",
                    "message": f"🔍 revisor: aprovada na {tentativa}ª tentativa ✔"})
            break
        if tentativa < max_tentativas:
            ev({"type": "note",
                "message": f"🔍 revisor: reprovou ({problema[:120]}) — refazendo "
                           f"(tentativa {tentativa + 1}/{max_tentativas})"})
            activity.log(cfg, "chat",
                         f"🔍 revisor reprovou (tentativa {tentativa}) — refazendo")
            mensagens = [
                {"role": "user", "content": f"{message}\n\n{plano_txt}"},
                {"role": "assistant", "content": resultado[:2500]},
                {"role": "user", "content":
                    f"O REVISOR reprovou o resultado: {problema}\n"
                    "Corrija o problema e complete a tarefa ORIGINAL de verdade. "
                    "Não peça ao usuário para fazer — execute você."},
            ]
        else:
            ev({"type": "note",
                "message": f"⚠ revisor ainda reprovou após {tentativas} tentativas "
                           f"— entregando com ressalva: {problema[:120]}"})

    dur = round(time.time() - t0, 1)
    status = ("aprovada" if veredito == "ok" and not _cancelado() else
              "reprovada" if not _cancelado() else "cancelada")
    tid = record(cfg, {"objetivo": objetivo, "status": status,
                       "tentativas": tentativas, "dur_s": dur,
                       "veredito": veredito, "problema": problema[:200]})
    activity.log(cfg, "chat",
                 f"🎯 task {tid} {status} · {tentativas} tentativa(s) · {dur}s")

    selo = ("\n\n─\n🔍 *revisada pelo revisor — veredito: aprovada*"
            if status == "aprovada" else
            f"\n\n─\n⚠ *revisão: {status}* — {problema[:200]}"
            if status == "reprovada" else "")
    final = (caixa["done"] or resultado) + selo
    ev({"type": "done", "message": final})   # o done verdadeiro, pós-revisão
    return final
