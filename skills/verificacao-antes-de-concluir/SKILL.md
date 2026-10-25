---
name: verificacao-antes-de-concluir
description: Verificação ANTES de concluir — provar com execução real que o pedido foi atendido, ler a própria resposta em busca de lacunas e só então entregar. Use ao final de QUALQUER tarefa, antes de dizer pronto, concluído, feito, entregue, resolvido, funcionando ou validado.
---

# Verificação antes de concluir

"Pronto" é uma afirmação verificável, não um sentimento. Antes de
escrever qualquer frase de conclusão, execute a verificação.

## O checklist final (na resposta, com evidência)

1. **O pedido foi atendido?** Relia a mensagem ORIGINAL do operador,
   palavra por palavra, e compare com o que você produziu — incluindo os
   detalhes "bobos" (nome do arquivo, caminho, formato).
2. **Rodou de verdade?** Execute e cole a saída real. Arquivo criado →
   mostre o conteúdo/ls. Código → execute com um exemplo. Comando →
   rode e traga stdout. Nada de "deve funcionar".
3. **A resposta se sustenta sozinha?** Relia sua própria resposta como
   se fosse o operador: alguma promessa sem prova? Algum "etc" que era
   para ser lista? Algum passo pulado?
4. **Quebrou nada em volta?** Se tocou em código existente: rode os
   testes que cubram a área.

## Se algo falhar na verificação

NÃO entregue com ressalva escondida. Reporte exatamente o que falhou,
o que você tentou e o estado real — o operador prefere a verdade útil
ao "pronto" falso. Falha declarada é informação; sucesso fingido é bug
com prazo.

## Regra de ouro

A última coisa que você faz numa tarefa não é escrever a conclusão —
é VERIFICAR e só depois escrever a conclusão que a evidência permite.
