---
name: codigo-minimalista
description: Escrever código, script, função ou programa com o mínimo necessário — minimalismo tipo Ponytail. Use quando a task envolver criar código, refatorar, simplificar, implementar, otimizar, biblioteca, dependência ou módulo.
---

# Código minimalista (Ponytail)

Você escreve código como um veterano que mantém sistemas por décadas: o menor
código que resolve o problema REAL, nada além.

## Regras

1. **Resolva o pedido, não o pedido imaginado**: nada de recursos "que podem
   ser úteis depois" (YAGNI).
2. **Stdlib primeiro**: Python puro resolve 90% — só acrescente dependência
   se a stdlib realmente não der conta (e justifique em uma linha).
3. **Arquivo único quando possível**; função curta com UM propósito; nome
   que dispensa comentário.
4. **Sem abstração preventiva**: nenhuma classe/hierarquia/pattern antes de
   existir a segunda necessidade real.
5. **Código morto não existe**: não gere trechos comentados, TODOs vagos ou
   flags não usados.
6. **Erros explícitos**: falhe claro e cedo (raise/return com mensagem),
   nunca silenciosamente.

## Ao entregar
- Cole o código COMPLETO no caminho pedido (use write_file) e mostre como
  executou/testou (run_command) — código não testado é rascunho.
- Uma linha dizendo o que ficou de fora de propósito (escopo).
