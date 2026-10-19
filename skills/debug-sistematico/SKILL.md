---
name: debug-sistematico
description: Depuração e debug sistemático de erro, bug, falha, crash, exceção, traceback, runtime, script, python, código, exit code, comportamento estranho, não funciona, quebrado ou corrompido — formular hipóteses e isolar a causa com evidências antes de corrigir.
---

# Debug sistemático (nada de chute)

Você depura como um sênior: hipótese → evidência → isolamento → correção →
verificação. CHUTAR correção é proibido.

## Método
1. **Reproduza**: execute o que falha (run_command) e capture o erro REAL
   (mensagem completa, traceback, exit code).
2. **Formule 2-3 hipóteses** de causa e diga qual testa primeiro e por quê.
3. **Isole**: um comando/verificação por hipótese (logs, arquivo de config,
   versão, permissão, rede) — uma variável por vez.
4. **Corrija a CAUSA**, não o sintoma (se o disco encheu, apagar log não é
   a correção — achar quem enche é).
5. **Verifique**: rode de novo e mostre a saída funcionando.

## Na entrega
- Causa raiz em uma frase · evidências (saídas coladas) · o que mudou ·
  prova de que resolvido.
