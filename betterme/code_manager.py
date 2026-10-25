"""Gerente de Código (Claude) — v4.0.0 (M7, decisão D5 do operador).

Divisão de papéis: **Betterme é o CÉREBRO MAIN** (orquestra, decide,
lembra, entrega); o **Claude Code é o GERENTE DE CÓDIGO** — quando o
operador ativar explicitamente, tarefas de código podem ser delegadas a
ele, com contrato task → resultado pleno.

Opt-in consciente (regra D5): a ativação AVISA que o código sai da
máquina para a Anthropic — contraste deliberado com a regra D2 (o pool
GRÁTIS nunca recebe código). Desligado por padrão.
"""
from __future__ import annotations
from .contratos import acao_de

AVISO_PRIVACIDADE = (
    "⚠ PRIVACIDADE: ao ativar o gerente de código, as tarefas de código "
    "delegadas a ele serão processadas pelo Claude Code (nuvem da "
    "Anthropic) — ou seja, O CÓDIGO SAI DA SUA MÁQUINA (a memória "
    "pessoal e os segredos continuam NUNCA saindo; só o conteúdo da "
    "task de código vai). O pool gratuito continua SEM código por "
    "regra (D2)."
)


def ativo(cfg) -> bool:
    return str(getattr(cfg, "gerente_codigo", "off") or "off").lower() \
        in ("on", "claude", "sim", "true")


def ativar(cfg, assumir: bool = False) -> tuple[bool, str]:
    """Liga o gerente com confirmação explícita do operador."""
    if ativo(cfg):
        return True, "gerente de código já está ativo."
    if not assumir:
        return False, AVISO_PRIVACIDADE + \
            "\n\nconfirme com: betterme gerente on --yes"
    cfg.update({"gerente_codigo": "on"})
    return True, ("👔 gerente de código ATIVO (Claude Code). O Betterme "
                  "continua sendo o cérebro: ele decide quando delegar.")


def desativar(cfg) -> str:
    cfg.update({"gerente_codigo": "off"})
    return "gerente de código desligado — código 100% local de novo."


def delegar(cfg, task: str, history: list[dict] | None = None,
            on_event=None, goal: str = "") -> str:
    """Cérebro → gerente de código. Retorna o resultado pleno (ou a
    explicação de por que não delegou)."""
    if not task.strip():
        return "ERRO: tarefa vazia — nada a delegar."
    if not ativo(cfg):
        return ("✖ gerente de código DESLIGADO — para delegar tarefas de "
                "código ao Claude, ative com: betterme gerente on --yes "
                "(aviso: o código da task vai para a nuvem Anthropic).")
    from .claude_agent import run_claude
    try:
        from . import activity
        activity.log(cfg, "gerente",
                     f"👔 task de código delegada ao Claude: "
                     f"{task[:80]}")
    except Exception:  # noqa: BLE001
        pass
    return run_claude(cfg, task, history=history or [],
                      on_event=on_event, goal=goal)


def cmd(args, cfg) -> None:
    """`betterme gerente on|off|status`."""
    acao = acao_de(args)
    if acao in ("status", ""):
        estado = "ATIVO (Claude Code)" if ativo(cfg) else "desligado"
        print(f"\n👔 gerente de código: {estado}")
        print("   Betterme = cérebro main (orquestra, decide, entrega);")
        print("   Claude = gerente de código (tarefas de código, opt-in).")
        if not ativo(cfg):
            print(f"\n{AVISO_PRIVACIDADE}")
        return
    if acao in ("on", "ativar"):
        assumir = bool(getattr(args, "yes", False))
        ok, msg = ativar(cfg, assumir=assumir)
        print(("✔ " if ok else "") + msg)
        return
    if acao in ("off", "desativar"):
        print("✔ " + desativar(cfg))
        return
    print(f"✖ ação inválida: {acao!r} (use status|on|off)")
    raise SystemExit(1)
