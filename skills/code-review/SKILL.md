---
name: code-review
description: Revisão de código em dois estágios — conformidade com o objetivo/versus o plano, depois qualidade técnica (padrões, bordas, dívida) — com veredito motivado e achados com arquivo e linha. Use quando revisar, review, análise de código, PR, diff, mudanças antes de commit, qualidade, aprovar ou recusar código.
---

# Code review em dois estágios

Revisar é conferir duas perguntas DIFERENTES, nessa ordem. Pular a
primeira é o erro clássico: código lindo que resolve o problema errado.

## Estágio 1 — CONFORMIDADE (o que pediu?)

- O código faz o que o OBJETIVO pede (não o que ele "quis" fazer)?
- Se havia plano/passos: cada passo foi implementado? Nenhum extra
  não-pedido entrou (feature creep)?
- Contratos visíveis: nomes, assinaturas e formatos que o operador
  especificou estão respeitados?

## Estágio 2 — QUALIDADE (como fez?)

- Erros de borda: entrada vazia, None, divisão por zero, off-by-one,
  encoding, caminho com espaço.
- Tratamento de erro honesto: except que não engole silêncio.
- Duplicação e mortos: código inalcançável, variáveis sem uso.
- Segurança: comando injetável, caminho fora do escopo, segredo
  hardcoded, permissão de arquivo.
- Manutenção: nomes dizem o que fazem? O próximo a ler entende?

## Veredito (obrigatório e motivado)

- **APROVADO** — conforme + qualidade, com o que está bom nomeado.
- **APROVADO COM RESSALVAS** — funciona; liste os ajustes recomendados.
- **REPROVADO** — liste cada achado como `arquivo:linha — problema —
  correção proposta`. Sem arquivo:linha, achado não vale.

## Regra

Todo achado cita arquivo e linha. Todo veredito cabe num parágrafo que
o operador decide ler. Revisão sem evidência é opinião.
