# -*- coding: utf-8 -*-
"""🚀 Modo MISSÃO — autonomia com subtasks encadeadas (v3.16.0).

O operador passa UMA tarefa ("missão: <objetivo>") e o Betterme:
  1. divide em 2-5 SUBTASKS sequenciais (LLM; fallback = a própria task);
  2. executa cada uma como task completa (pipeline 🎯⚡🔍 — com revisor,
     aprovações, escopo de projeto e skills);
  3. VALIDA cada subtask; reprovou → REESCREVE a task (prompt melhorado a
     partir do problema apontado) e tenta de novo;
  4. fecha com a VALIDAÇÃO FINAL do objetivo inicial + relatório.

O objetivo é terminar a task inicial de forma satisfatória — com
evidência real em cada etapa.
"""
from __future__ import annotations

import re

_MISSAO_RE = re.compile(
    r"(?i)^\s*(missão|missao|modo\s+miss[ãa]o)\s*[:\-—]\s*")
MAX_SUBTASKS = 5

_PLANO_MISSAO = (
    "Você é o PLANEJADOR DE MISSÕES do Betterme: engenheiro de software "
    "sênior que divide um objetivo grande em SUBTASKS sequenciais — cada "
    "uma entregável e verificável por evidência real.\n"
    "Regras:\n"
    "- 2 a 5 subtasks, na ORDEM certa (a última completa o objetivo);\n"
    "- cada objetivo: UMA frase com verbo de conclusão, concreta (cite "
    "arquivos/comandos quando der);\n"
    "- critérios VERIFICÁVEIS na resposta (saída real, arquivo existente, "
    "teste verde).\n"
    "Responda APENAS o JSON:\n"
    '{"subtasks":[{"objetivo":"...","criterios":["..."]}]}\n\n'
    "Exemplo — objetivo \"construa um app de tarefas\":\n"
    '{"subtasks":[{"objetivo":"estruturar o projeto com dependências e '
    'entrada executável","criterios":["projeto roda sem erro"]},'
    '{"objetivo":"implementar as telas e a lógica de tarefas",'
    '"criterios":["criar e concluir uma tarefa funciona"]},'
    '{"objetivo":"escrever testes e versionar no git",'
    '"criterios":["testes verdes","commit criado"]}]}'
)

_MELHORAR_TASK = (
    "Uma subtask de uma missão FALHOU. Reescreva a TAREFA (não a resposta) "
    "para que a próxima tentativa consiga: mais concreta, passos menores, "
    "citando comandos e arquivos exatos, evitando o problema apontado.\n"
    "Responda APENAS a nova tarefa reescrita (máximo 3 linhas, sem lista "
    "de raciocínio)."
)


def _planejar_subtasks(cfg, objetivo: str) -> list[dict]:
    """Divide o objetivo em subtasks; fallback = 1 task (o objetivo todo)."""
    try:
        from .orchestrator import _extract_json, _fast
        texto = _fast(cfg, _PLANO_MISSAO, objetivo, ntok=420,
                      stage="🚀 planejador de missão")
        obj = _extract_json(texto)
        subs = (obj or {}).get("subtasks")
        out: list[dict] = []
        for s in (subs or [])[:MAX_SUBTASKS]:
            alvo = str(s.get("objetivo") or "").strip()
            if not alvo:
                continue
            crit = [str(c)[:160] for c in (s.get("criterios") or [])[:3]]
            out.append({"objetivo": alvo[:300], "criterios": crit})
        if out:
            return out
    except Exception:  # noqa: BLE001
        pass
    return [{"objetivo": objetivo[:300], "criterios": []}]


def _task_melhorada(cfg, subtask: str, problema: str, resultado: str) -> str:
    """Reescreve a subtask falha — prompt melhorado a partir do problema."""
    try:
        from .orchestrator import _fast
        user = (f"SUBTASK QUE FALHOU: {subtask}\n"
                f"PROBLEMA APONTADO PELO REVISOR: {problema[:300]}\n"
                f"RESULTADO DA TENTATIVA (trecho): {str(resultado)[:600]}")
        r = _fast(cfg, _MELHORAR_TASK, user, ntok=220,
                  stage="🔁 reescrita de subtask").strip()
        if r:
            return r[:400]
    except Exception:  # noqa: BLE001
        pass
    return (subtask[:300]
            + f"\nAtenção especial: resolva exatamente este problema "
              f"apontado pelo revisor: {problema[:200]}")


def run_mission(agent, cfg, message: str, history: list[dict],
                on_event=None, cancel=None, goal: str = "",
                session_id: str = "") -> str:
    """Executa a missão: subtasks → validação → retry com task melhorada
    → validação final → relatório. Nunca lança."""
    from .orchestrator import (_detectar_projetos, _extra_criterios,
                               _pergunta_caminho, review, run_pipeline)
    ev = on_event or (lambda _e: None)
    objetivo = _MISSAO_RE.sub("", message, count=1).strip() or message

    # pasta do projeto: vem no pedido da missão OU pergunta UMA vez (nunca
    # por subtask — a pendência re-dispara a missão com o caminho)
    pastas = _detectar_projetos(message)
    if (getattr(cfg, "ask_project_path", True)
            and _extra_criterios(objetivo) and not pastas):
        return _pergunta_caminho(message, goal, session_id)
    pasta_txt = (f"\n[Pasta do projeto da missão: {pastas[0]}]" if pastas
                 else "")

    subtasks = _planejar_subtasks(cfg, objetivo)
    n = len(subtasks)
    ev({"type": "note",
        "message": f"🚀 missão iniciada: {n} subtask(s) em sequência"})
    ev({"type": "brain", "stage": "🚀 missão",
        "data": {"objetivo": objetivo[:200],
                 "subtasks": [s["objetivo"][:120] for s in subtasks]}})

    contexto, relatorio, entregas, ok_count = "", [], [], 0
    interrompida = ""
    for i, st in enumerate(subtasks, 1):
        if cancel is not None and cancel.is_set():
            interrompida = "cancelada"
            break
        alvo = st["objetivo"]
        msg_st = (alvo + pasta_txt
                  + (f"\n\n[Missão {i}/{n} — contexto do que já foi feito:"
                     f"\n{contexto[-1200:]}]" if contexto else ""))
        ev({"type": "note", "message": f"🎯 subtask {i}/{n}: {alvo[:90]}"})
        meta: dict = {}
        final = run_pipeline(agent, cfg, msg_st, [], on_event=ev,
                             cancel=cancel, goal=goal, session_id=session_id,
                             extra_criterios=st["criterios"],
                             resultado_meta=meta)
        if cancel is not None and cancel.is_set():
            interrompida = "cancelada"
            break
        if meta.get("veredito") == "cancelada":
            interrompida = "cancelada pelo operador"
            break
        sucesso = meta.get("veredito") == "ok"
        tentativas = 1
        if not sucesso:
            problema = (meta.get("problema")
                        or "entrega sem evidência suficiente")
            ev({"type": "note",
                "message": f"🔁 subtask {i}/{n} reprovada ({problema[:90]}) "
                           "— reescrevendo a task e tentando de novo"})
            melhorada = _task_melhorada(cfg, alvo, problema, final)
            meta = {}
            msg2 = (melhorada + pasta_txt
                    + (f"\n\n[Missão {i}/{n} — tentativa com task melhorada "
                       f"após falha: {problema[:150]}\nContexto já feito:"
                       f"\n{contexto[-900:]}]" if contexto else ""))
            final = run_pipeline(agent, cfg, msg2, [], on_event=ev,
                                 cancel=cancel, goal=goal,
                                 session_id=session_id,
                                 extra_criterios=st["criterios"],
                                 resultado_meta=meta)
            if cancel is not None and cancel.is_set():
                interrompida = "cancelada"
                break
            sucesso = meta.get("veredito") == "ok"
            tentativas = 2
            if sucesso:
                ev({"type": "note",
                    "message": f"✔ subtask {i}/{n} concluída na 2ª tentativa "
                               "(task reescrita)"})
        marca = "✔" if sucesso else "⚠"
        if sucesso:
            ok_count += 1
        contexto += f"\n- subtask {i} {marca} {alvo[:80]}: {final[:280]}"
        relatorio.append(f"  {i}. {marca} {alvo[:100]} ({tentativas} "
                         "tentativa(s))")
        entregas.append(f"[subtask {i} — {alvo[:80]}]\n{final[:700]}")

    # ── validação FINAL: a missão cumpriu o objetivo inicial? ──
    crit_final = ([c for st in subtasks for c in st["criterios"]][:4]
                  or ["o objetivo da missão foi cumprido com evidências reais"])
    ver = review(cfg, f"MISSÃO INICIAL: {objetivo[:250]}", crit_final,
                 "\n\n".join(entregas)[:4000])
    verd_final = ver.get("veredito", "ok")
    if interrompida:
        cab = f"⛔ Missão interrompida ({interrompida})"
    elif verd_final == "ok":
        cab = "🚀 Missão concluída — objetivo inicial atendido"
    else:
        cab = ("🚀 Missão encerrada com ressalvas — "
               + str(ver.get("problema", ""))[:150])
    rel = (f"{cab}\n🎯 Objetivo inicial: {objetivo[:250]}\n"
           f"Subtasks concluídas: {ok_count}/{n}\n"
           + "\n".join(relatorio)
           + f"\n🔍 Validação final do revisor: {verd_final}")
    ev({"type": "done", "message": rel})
    return rel
