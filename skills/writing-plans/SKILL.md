---
name: writing-plans
description: Escrever planos executáveis — tarefa decomposta em passos pequenos, cada um com ação, artefato e forma de verificação, na ordem certa, com riscos tratados. Use quando planejar, plano, roadmap, dividir tarefa, estimar, tarefa grande, multi-etapas, missão, executar em fases ou antes de começar trabalho complexo.
---

# Plano executável (passo que não verifica não é passo)

Plano bom é aquele que outro agente (ou você amanhã) executa sem
precisar pensar de novo. Cada passo é uma ordem pequena e verificável.

## Anatomia do plano

Para CADA passo:
1. **Ação** — verbo + objeto + caminho (ex.: "criar tests/testa_soma.py
   com 3 casos de borda"). Um verbo por passo; dois verbos = dois passos.
2. **Artefato** — o que EXISTIRÁ depois dele (arquivo, saída, resultado).
3. **Verificação** — como saber que deu certo (rodar X e esperar Y;
   conferir que o arquivo contém Z).

## Ordem e dependências

- Passos na ordem em que podem ser executados — sem "faça depois do
  passo que ainda não existe".
- Riscos conhecidos viram passos de mitigação ANTES do passo arriscado
  (ex.: backup antes de migração).
- Primeiro passo = o mais barato que valida a premissa mais arriscada.

## Tamanho

- 3–7 passos para tarefas médias; acima disso, fases com sub-passos.
- Se um passo não cabe em 3 linhas de descrição, ele é uma fase —
  quebre.

## Fechamento

Todo plano termina com um passo de VERIFICAÇÃO FINAL contra o objetivo
original (rodar a suíte, abrir o artefato, reler o pedido) — e um
critério explícito de "está pronto".
