---
name: debug-sistematico
description: Debug em 4 fases — reproduzir o erro de forma determinística, isolar a causa com evidência, corrigir UMA hipótese por vez e verificar a correção de ponta a ponta. Use quando algo falhar, erro, exception, traceback, bug, não funciona, comportamento estranho, crash, teste vermelho, regressão ou diagnóstico.
---

# Debug sistemático (não chute — evidência)

Chute consome tokens e enterra a causa real. O ciclo de 4 fases é mais
barato até no modelo 8B local.

## Fase 1 — REPRODUZIR

Reproduza o erro com o MENOR comando/arquivo possível, de forma
determinística. Sem reprodução estável não existe debug — existe
adivinhação. Cole a saída REAL do erro (traceback completo).

## Fase 2 — ISOLAR

Encurte o ciclo: comente/bisseque o código até a menor unidade que ainda
falha. Leia a MENSAGEM do erro e o NÚMERO DA LINHA antes de qualquer
hipótese. Pergunte: "o que eu ASSUMO que é verdade aqui?" e teste a
assunção mais barata primeiro (printf/log no ponto exato).

## Fase 3 — HIPÓTESE ÚNICA

Formule UMA hipótese causal ("X é None porque Y não inicializa") e
corrija SÓ ela. Se a hipótese exigir mudar três coisas ao mesmo tempo,
ela está errada — volte à fase 2.

## Fase 4 — VERIFICAR

1. O caso mínimo agora passa (saída colada).
2. A suíte inteira continua verde (nada quebrou em volta).
3. O erro original, do jeito que o operador relatou, não volta.

## Proibido

- "Correção" sem causa identificada (coberturas try/except pass).
- Mudar duas variáveis numa tacada.
- Concluir "está corrigido" sem rodar nada.
