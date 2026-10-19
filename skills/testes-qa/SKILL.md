---
name: testes-qa
description: Escrever e rodar testes — teste, testes, cobertura, pytest, caso de borda, validar comportamento, regressão, suíte e qualidade do código gerado antes de entregar.
---

# Testes e QA (código sem teste é rascunho)

## Regras
1. Toda correção/feature vem com teste que falha antes e passa depois.
2. Teste o COMPORTAMENTO, não a implementação (entre pela API/função
   pública).
3. Cubra: caminho feliz, caso de borda (vazio, zero, unicode, timeout) e
   o erro esperado.
4. RODE a suíte (run_command: `python -m pytest arquivo -x -q` ou o runner
   do projeto) e cole a saída REAL — "deve funcionar" não é evidência.
5. Se não puder testar (sem ambiente), diga explicitamente e explique o
   risco assumido.

## Na entrega
- O que o teste cobre · saída da execução · o que ficou de fora.
