# ✅ Checklist pré-release — Betterme

> Lição dos 4 achados de campo (#1 entry points, #2 PEP 660, #3
> performance, #4 agente mudo/alucinado): **testes de happy path verde
> ≠ app que cumpre a função.** Este checklist é GATE — nenhum `git tag`
> sai sem todos os itens fechados.

## 1. Promessas ↔ testes
- [ ] Toda promessa do **GUIA-DE-USO** tem caso de teste correspondente
      (ou a promessa sai do guia). Promessa sem teste é dívida.

## 2. Modos de falha ANTES do happy path
- [ ] Para cada superfície user-facing (chat, tarefas, gateways, GUI):
      o que acontece se o pipeline devolve **vazio**? se a **thread
      morre**? se dá **timeout**? Cada um desses tem teste (padrão T188).
- [ ] Nenhum fluxo termina em **silêncio**: sempre `done` ou `error`.

## 3. Campo → regressão
- [ ] Todo transcript/erro reportado pelo operador vira caso de
      regressão permanente ANTES do próximo tag (#1→fix, #2→fix,
      #3→T180, #4→T188).

## 4. Bateria real (comportamental)
- [ ] Suíte integral em mock: N/N (não valida comportamento de modelo —
      mock é roteiro determinístico).
- [ ] **Na máquina do operador (com Ollama):** 1 jornada real por
      superfície prometida (ex.: "relatório do PC" → tool de diagnóstico
      + dados reais no arquivo) antes de declarar "pronto".

## 5. Qualidade e release
- [ ] ruff `E9,F,B,PLE` limpo · `betterme varredura` sem críticos ·
      `gen_doc.py` regenerado.
- [ ] config.VERSION + pyproject + CHANGELOG + MAPA alinhados · tag +
      push + zip + demo com curl de verificação.
