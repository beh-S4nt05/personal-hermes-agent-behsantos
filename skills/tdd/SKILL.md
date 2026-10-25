---
name: tdd
description: Desenvolvimento orientado a testes — escrever o teste ANTES do código, vê-lo falhar, implementar o mínimo para passar e refatorar. Use quando a tarefa envolver testar, teste, TDD, unidade, bugfix, corrigir erro, regressão, nova função, implementar funcionalidade, refatorar ou mudar comportamento de código.
---

# TDD — vermelho, verde, refatora

Código sem teste é hipótese. Com o modelo 8B local, o ciclo curto é a
única proteção contra alucinação de API/sintaxe.

## O ciclo (obrigatório, nesta ordem)

1. **VERMELHO** — escreva UM teste que expresse o comportamento desejado.
   Rode-o e VEJA FALHAR (saída real colada na resposta). Teste que não
   rodou não conta.
2. **VERDE** — implemente o MÍNIMO que faz o teste passar. Sem ouro sem
   necessidade: nada de recursos extras "que vão ser úteis depois".
3. **REFACTORA** — com o teste verde, melhore nomes/estrutura e rode de
   novo. Verde continua verde.

## Regras

- Um comportamento por vez; um teste por vez. Nunca escreva o lote todo.
- Se o teste falhar de forma inesperada, NÃO ajuste o teste para passar —
  é hipótese errada: volte ao passo 1 e releia o requisito.
- Bug corrigido = primeiro um teste que REPRODUZ o bug (vermelho), depois
  o fix (verde). O teste fica na suíte para sempre (regressão morta).
- Ao final, rode a SUÍTE INTEIRA, não só o teste novo.
- Entregue: o que o teste exige — nem mais, nem menos.

## Sinais de que você está furando o ciclo

- Escrevendo implementação antes do teste → pare e apague.
- "Vou testar depois" → depois não existe; a entrega exige o teste verde.
- Teste que só passa com sleep/retry mágico → o problema é design.
