"""Contexto de projeto — v4.0.0 (M2).

Instruções duráveis por projeto, no padrão que virou convenção da
indústria (AGENTS.md do Codex / CLAUDE.md do Claude Code / QWEN.md):

- ``BETTERME.md`` global (máquina): ``<data_dir>/BETTERME.md``
- ``BETTERME.md`` do projeto: raiz do projeto em foco (task scope);
  fallbacks legados: ``HERMES.md`` (nome até v4.0) e ``AGENTS.md``
  (compatibilidade com Codex, Qwen Code e outros agentes)
- precedência: BETTERME.md > HERMES.md > AGENTS.md
- teto de 32 KiB no total (mesmo cap do Codex) com marcador de corte

Privacidade: o conteúdo é instrução de projeto, não dado pessoal —
para provedores EXTERNOS a seção vai filtrada pelo DLP ``mascarar()``
(segredos e código censurados; regra D2 da v4.0.0).
"""
from __future__ import annotations

from pathlib import Path

CAP_BYTES = 32 * 1024          # mesmo teto do Codex (AGENTS.md)
_MARCADOR = "<!-- betterme: seção gerenciada pelo betterme init -->"


def _ler(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


def descobrir(cfg, projeto: Path | None = None) -> list[tuple[str, str]]:
    """[(rotulo, texto)] — global primeiro, projeto depois (vence)."""
    achados: list[tuple[str, str]] = []
    # 1) global da máquina
    g = (_ler(Path(cfg.data_dir) / "BETTERME.md")
          or _ler(Path(cfg.data_dir) / "HERMES.md"))
    if g:
        achados.append(("global (máquina)", g))
    # 2) projeto em foco (task scope)
    if projeto is None:
        try:
            from .tools import scope_dir
            projeto = scope_dir()
        except Exception:  # noqa: BLE001
            projeto = None
    if projeto:
        projeto = Path(projeto)
        for nome in ("BETTERME.md", "HERMES.md", "AGENTS.md"):
            t = _ler(projeto / nome)
            if t:
                achados.append((f"{nome} do projeto", t))
                break          # BETTERME.md > HERMES.md > AGENTS.md
    return achados


def secao(cfg, projeto: Path | None = None) -> str:
    """Seção pronta para o system prompt ("" se não houver nada)."""
    achados = descobrir(cfg, projeto)
    if not achados:
        return ""
    blocos = []
    for rotulo, texto in achados:
        blocos.append(f"### Contexto do projeto — {rotulo}\n{texto}")
    saida = "\n\n## 📋 Instruções do projeto (BETTERME.md)\n\n" + \
        "\n\n".join(blocos) + "\n"
    if len(saida.encode("utf-8")) > CAP_BYTES:
        corte = saida.encode("utf-8")[:CAP_BYTES].decode("utf-8",
                                                         errors="ignore")
        saida = corte + "\n…(contexto do projeto truncado em 32 KiB)\n"
    return saida


def versao_externa(secao_texto: str) -> str:
    """Versão da seção segura p/ provedores externos (DLP mascarar)."""
    from .varredura import mascarar
    return mascarar(secao_texto)


def scaffold(caminho: Path) -> tuple[Path, bool]:
    """`betterme init` — cria BETTERME.md de partida no projeto."""
    alvo = Path(caminho) / "BETTERME.md"
    if alvo.exists():
        return alvo, False
    alvo.write_text(
        f"{_MARCADOR}\n"
        "# BETTERME.md — instruções duráveis deste projeto\n\n"
        "O agente lê este arquivo em TODA tarefa neste projeto.\n"
        "Edite à mão quando quiser; mantenha curto e direto.\n\n"
        "## Visão\n"
        "- O que é este projeto (1–2 linhas):\n\n"
        "## Comandos\n"
        "- testes: (ex.: python tests/run_all.py)\n"
        "- lint: (ex.: ruff check --select E9,F,B,PLE .)\n"
        "- executar: \n\n"
        "## Convenções\n"
        "- \n\n"
        "## Limites (o agente NUNCA deve)\n"
        "- \n",
        encoding="utf-8")
    return alvo, True


def cmd(args, cfg) -> None:
    """`betterme init` — scaffold do BETTERME.md."""
    caminho = Path(getattr(args, "caminho", None) or Path.cwd())
    alvo, criado = scaffold(caminho)
    print(f"📋 {alvo} — {'criado' if criado else 'já existia (nada alterado)'}")
    print("   edite à vontade; o agente lê em toda tarefa neste projeto.")
