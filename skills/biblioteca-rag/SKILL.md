---
name: biblioteca-rag
description: "Consultar a biblioteca de livros e documentação do operador (RAG local) antes de escrever código: busca verbatim com fonte. Use quando a tarefa precisar de referência, documentação, livro, consulta técnica, citação, padrão oficial ou sintaxe exata, ou quando o operador citar a biblioteca."
---
# Biblioteca do operador — consulta antes de inventar

## A regra
Antes de escrever código sobre um assunto que a biblioteca cobre,
**consulte**: ferramenta `knowledge_search` com a dúvida específica.
A resposta é TRECHO VERBATIM DO LIVRO com a fonte — a fonte da verdade
vem do papel, não da memória do modelo.

## Quando consultar (obrigatório)
- O operador citar um livro, capítulo ou documentação da biblioteca.
- Sintaxe/API exata de que você não tem certeza (evita alucinar assinatura).
- Padrão oficial (arquitetura, estilo, processo) antes de aplicar.

## Como usar
```
knowledge_search({ "query": "reducer estado imutável MVI" })
```
- Consulta ESPECÍFICA ("coroutines Dispatchers IO exemplo") > genérica.
- Cite a fonte na resposta: `📚 livro.pdf (trecho #12)`.
- Se não achar nada: diga que não há na biblioteca — NÃO invente citação.

## Manutenção (operador)
- Livros em `~/.hermes/biblioteca/` (.md/.txt/.pdf com pdftotext).
- Reindexar: `hermes rag` · consultar no terminal: `hermes rag "query"`.

## Verificação
Toda afirmação técnica forte tem fonte da biblioteca OU teste executado.
