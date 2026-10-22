---
name: diagnostico-raiz
description: Método para bugs e comportamentos estranhos — sintoma, hipóteses ordenadas, prova de cada uma com o menor teste possível, causa raiz e correção verificada. Use quando algo "não funciona", "está lento", "dá erro", "comporta-se de forma estranha" ou quando o resultado difere do esperado.
---

# Diagnóstico até a causa raiz

Sintoma ≠ causa. O objetivo não é fazer sumir: é provar POR QUE
acontece e consertar na raiz — senão volta.

## Passos

1. **Reproduza**: sem reprodução confiável não há diagnóstico. Anote o
   comando/ação exato e o resultado observado.
2. **Liste hipóteses** ordenadas da mais provável à menos, ANTES de
   testar. Ex.: porta ocupada? serviço no boot? cache do navegador?
   versão antiga rodando?
3. **Prove uma por uma**, com o menor teste possível de cada:
   - quem escuta a porta: `ss -tlnp | grep :PORTA`
   - o processo existe: `ps aux | grep <nome>`
   - serviço de boot: `systemctl is-enabled <nome>`
   - o servidor responde: `curl -sS <endereço>/api/status`
4. **Aceite o resultado do teste** — mesmo que contradiga sua hipótese
   favorita. Diagnóstico sem prova é palpite.
5. **Causa raiz** → conserto → **teste de regressão**: repita o cenário
   que falhou e prove que agora passa. Documente a lição.

## Armadilha clássica

Sintoma em um lugar, causa em outro: página "viva" com servidor morto
(cache do navegador), erro na tela nascido em patch de 3 versões atrás
(escape de aspas). Sempre pergunte: "o que mais pode produzir exatamente
este sintoma?" antes de acreditar na primeira resposta.
