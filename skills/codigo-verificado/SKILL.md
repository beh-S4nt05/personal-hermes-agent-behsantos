---
name: codigo-verificado
description: Escrever código que FUNCIONA de verdade — escrever o arquivo, executar com um exemplo real, ler a saída e corrigir o erro antes de entregar. Use quando a tarefa envolver código, script, função, classe, programa, implementar, python, javascript, node, vba, algoritmo, calculadora, aplicativo, website, sistema web ou projeto de software.
---

# Código verificado (nada de código não-executado)

Código que não rodou é uma hipótese, não uma entrega. O 8B pode
alucinar API, variável ou sintaxe — a única prova é a SAÍDA REAL.

## Fluxo obrigatório

1. **Escreva o arquivo** com `write_file` (workspace), completo —
   sem "..." nem "implemente depois".
2. **Execute AGORA**: `run_command` com `python3 arquivo.py`
   (ou `python3 -m py_compile arquivo.py` se não houver exemplo
   viável — e depois rode um exemplo mínimo de qualquer forma).
3. **Leia a saída**: deu erro? CORRIJA o arquivo e rode de novo
   (máx. 3 rodadas) — erro na saída é bug seu, não do usuário.
4. **Entregue**: o código + a saída real da execução + uma frase
   dizendo o que a saída prova. Sem execução colada, não entregue.

## Anti-alucinação (o 8B inventa quando não tem dados)

- Antes de usar uma biblioteca: confirme que ela está instalada
  (`pip show X` ou importe e rode).
- Antes de operar um arquivo de dados: leia o cabeçalho REAL
  (`head`/read_file) — nunca invente nome de coluna.
- Antes de prometer comportamento: rode e mostre. "Deveria funcionar"
  é proibido — "executei e devolveu isto" é o padrão.

## Entrega completa

Script + exemplo de uso + saída real + limites conhecidos (o que
falta para produção). Incompleto declarado > completo fingido.
