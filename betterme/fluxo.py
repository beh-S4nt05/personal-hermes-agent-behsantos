"""⚡ Fluxo leve — orquestração adaptativa em 3 níveis (v6.6.0).

Padrão extraído do Plandex (orquestrador que REGULA a tarefa quebrada
em partes), reimplementado NATIVO e leve — sem servidor, sem Docker,
sem dependência externa (o Plandex em si está parado desde jul/2025 e
com CVE aberta; o PADRÃO é que vale):

  NÍVEL 0 — CONVERSA   → resposta direta: 1 chamada ao cérebro, ZERO
                         planejamento (o planner custava 1 ida inteira
                         ao modelo antes de qualquer "oi").
  NÍVEL 1 — TAREFA     → fluxo clássico: planner enxuto → executor →
                         revisão (fast lane quando não há critérios).
  NÍVEL 2 — COMPLEXA   → decomposição em ETAPAS FOCADAS (padrão
                         Plandex): cada etapa é uma execução enxuta com
                         o contexto acumulado das anteriores; UMA
                         revisão única no consolidado (regulação barata
                         — não 1 revisão por etapa).

Política conservadora: na dúvida, cai para o nível MAIOR (nunca
pula trabalho por otimização). Kill-switch: cfg.fluxo_leve = False.
"""
from __future__ import annotations

import re

# ── nível 0: o que é CONVERSA PURA (nenhuma ação sobre a máquina) ──
# verbos de AÇÃO (sistema/arquivo/comando/pesquisa) → não é conversa
_ACAO_RE = re.compile(
    r"\b(verifiqu\w*|confer\w*|list\w*|listar|rod\w*|execut\w*|rode|"
    r"cri\w*|escrev\w*|salv\w*|grav\w*|apag\w*|delet\w*|remov\w*|"
    r"instal\w*|desinstal\w*|atualiz\w*|baix\w*|suba|subir|envi\w*|"
    r"mostre|mostr\w*|analis\w*|diagnostic\w*|corrig\w*|consert\w*|"
    r"faç\w*|faca|faz\w*|faça|ger\w*|gere|pesquis\w*|busc\w*|procur\w*|"
    r"copi\w*|mov\w*|renomei\w*|format\w*|convert\w*|limp\w*|limpe|"
    r"agend\w*|dispar\w*|monitor\w*|observ\w*|vigie|assist\w*|"
    r"commit\w*|public\w*|publique|edite|editar|abra|abrir|feche|"
    r"fechar|reinicie|reiniciar|desligue|ligue|ligar|desligar|"
    r"configure|configur\w*|mude|mudar|alter\w*|troque|defin\w*)\b",
    re.IGNORECASE)

# assuntos que EXIGEM o pipeline completo (projeto/missão/followup/
# relatório/arquivo…) — conservador: na dúvida não é conversa
_INTENSO_RE = re.compile(
    r"\b(projeto|missão|missao|conclu\w*|continu\w*|refa\w*|anterior|"
    r"tarefa|relatório|relatorio|documento|arquivo|script|código|"
    r"codigo|site|app|sistema|servidor|backup|planilha|banco|"
    r"disco|memória|memoria|processo|rede|porta|log|erro|bug|"
    r"instal\w*|versão|versao|modelo|docker|git)\b",
    re.IGNORECASE)

MAX_ETAPAS = 6


def eh_conversa(msg: str) -> bool:
    """Nível 0? Mensagem é conversa pura (nenhuma ação sobre a
    máquina, nenhum assunto técnico) → pode responder direto."""
    m = (msg or "").strip()
    if not m or len(m) > 500:
        return False
    if "```" in m or "/" in m or "\\" in m:      # código/caminho → ação
        return False
    if _ACAO_RE.search(m) or _INTENSO_RE.search(m):
        return False
    return True


# ── nível 2: decomposição (o padrão Plandex, nativo) ──
def decompor(msg: str, passos: list[str] | None) -> list[str]:
    """Quebra a task em etapas FOCADAS. Fonte preferida: os passos que
    o próprio planner devolveu; senão heurística estrutural (lista
    numerada/marcadores/«;»/«e depois»). Devolve [] se não dá para
    decompor com segurança (≤1 etapa) — aí segue fluxo normal."""
    etapas = [str(p).strip() for p in (passos or []) if str(p).strip()]
    if len(etapas) >= 2:
        return etapas[:MAX_ETAPAS]
    # heurística estrutural sobre a mensagem original — só LISTAS DE
    # VERDADE (itens numerados ou com bullet); prosa multi-linha NÃO é
    # decomposição (lição do T120: a retomada de projeto tem 2 linhas)
    m = (msg or "").strip()
    lista = []
    for ln in m.splitlines():
        st = ln.strip()
        if re.match(r"^\d+[.)]\s+\S", st):
            lista.append(re.sub(r"^\d+[.)]\s+", "", st))
        elif re.match(r"^[-*•·]\s+\S", st):
            lista.append(re.sub(r"^[-*•·]\s+", "", st))
    if 2 <= len(lista) <= MAX_ETAPAS and all(4 <= len(x) <= 200
                                             for x in lista):
        return [x[:160] for x in lista]
    if ";" in m:
        partes = [p.strip() for p in m.split(";") if p.strip()]
        if 2 <= len(partes) <= MAX_ETAPAS and all(4 <= len(p) <= 200
                                                  for p in partes):
            return [p[:160] for p in partes]
    if re.search(r"\be depois\b", m, re.IGNORECASE):
        partes = [p.strip() for p in re.split(r"\be depois\b", m,
                                              flags=re.IGNORECASE)
                  if p.strip()]
        if 2 <= len(partes) <= MAX_ETAPAS:
            return [p[:160] for p in partes]
    return []


def consolidar(etapas: list[tuple[str, str]]) -> str:
    """Junta os resultados das etapas num relatório único com rastro
    (o que saiu de cada parte) — é isso que o revisor avalia."""
    if not etapas:
        return ""
    if len(etapas) == 1:
        return (etapas[0][1] or "").strip()
    partes = []
    for i, (etapa, saida) in enumerate(etapas, 1):
        partes.append(f"### Etapa {i} — {etapa[:100]}\n"
                      f"{(saida or '').strip()}")
    return "\n\n".join(partes)
