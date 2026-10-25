"""Autonomia em 3 níveis — v4.0.0 (M5, decisão D3 do operador).

    CAUTELOSO — gates de criação E de entrega; na TUI, TODO comando
                passa por confirmação do operador.
    PADRÃO    — leitura livre, escrita aprovada (comportamento v3.x):
                gate de criação ativo, entrega editável nas criações.
    AUTÔNOMO  — encadeia missões sem parar nos gates SOFT; ganha
                varredura pré-entrega e relatório auditado.

HARD GATES (inegociáveis em QUALQUER nível — risco #10 do pre-mortem):
comandos perigosos (denylist), segredos (secrets/), escopo de projeto,
sandbox e a regra D2 (código/memória nunca vão a provedores gratuitos).
"""
from __future__ import annotations

NIVEIS = ("cauteloso", "padrao", "autonomo")

DESCRICOES = {
    "cauteloso": "toda ação relevante pede confirmação (criação, entrega "
                 "e cada comando na TUI)",
    "padrao": "leitura livre; escrita aprovada (gate de criação + entrega "
              "editável) — o equilíbrio recomendado",
    "autonomo": "missões encadeadas sem parar nos gates soft; hard gates "
                "sempre ativos + varredura pré-entrega + relatório",
}

HARD_GATES = (
    "comandos perigosos na denylist (is_dangerous) sempre bloqueados",
    "secrets/ nunca é lido pelo agente (credenciais fora do alcance)",
    "escopo do projeto e sandbox continuam valendo (kernel + app)",
    "código e memória NUNCA vão a provedores gratuitos (regra D2)",
)


def nivel(cfg) -> str:
    v = str(getattr(cfg, "autonomia", "padrao") or "padrao").strip().lower()
    return v if v in NIVEIS else "padrao"


def pula_gate_criacao(cfg) -> bool:
    return nivel(cfg) == "autonomo"


def pula_gate_entrega(cfg) -> bool:
    return nivel(cfg) == "autonomo"


def confirma_todo_comando(cfg) -> bool:
    return nivel(cfg) == "cauteloso"


def pre_entrega_varredura(cfg, raiz) -> str:
    """Sufixo de aviso p/ o relatório do modo AUTÔNOMO: varre o projeto
    entregue e denuncia achados críticos (segredo/dado vazando)."""
    try:
        from .varredura import varrer_repo
        crit = [a for a in varrer_repo(cfg, raiz)
                if a.severidade == "CRITICO"]
    except Exception:  # noqa: BLE001
        return ""
    if not crit:
        return ""
    return (f"\n\n🛡 varredura pré-entrega: {len(crit)} achado(s) CRÍTICO(S) "
            f"no projeto — revise antes de publicar "
            f"(ex.: {crit[0].arquivo}:{crit[0].linha} — {crit[0].id}).")


def cmd(args, cfg) -> None:
    """`hermes autonomia [nivel]` — vê ou muda o nível."""
    alvo = str(getattr(args, "nivel", "") or "").strip().lower()
    if not alvo:
        print(f"\n🎚 autonomia atual: {nivel(cfg).upper()}")
        for n in NIVEIS:
            marca = "→" if n == nivel(cfg) else " "
            print(f"  {marca} {n:<10} {DESCRICOES[n]}")
        print("\n  hard gates (sempre ativos, em qualquer nível):")
        for h in HARD_GATES:
            print(f"     • {h}")
        return
    if alvo not in NIVEIS:
        print(f"✖ nível inválido: {alvo!r} — use: {', '.join(NIVEIS)}")
        raise SystemExit(1)
    cfg.update({"autonomia": alvo})
    print(f"🎚 autonomia agora: {alvo.upper()} — {DESCRICOES[alvo]}")
    if alvo == "autonomo":
        print("   (hard gates continuam: " + "; ".join(
            h.split("(")[0].strip() for h in HARD_GATES[:2]) + "…)")
