---
name: atalhos-shell
description: Receitas prontas de uma linha para o dia a dia — busca geral no sistema, entender o uso do dispositivo, diagnóstico geral e saúde da máquina, verificar espaço em disco, encontrar arquivos grandes, ver qual processo pesado come memória RAM, descobrir o dono de uma porta ocupada, fazer backup rápido de uma pasta e limpar arquivos temporários. Use quando o pedido envolver manutenção rápida, verificação de disco, memória, processo lento ou backup simples.
---

# Atalhos shell do dia a dia

Operação comum = comando pronto. Escolha a linha, execute e interprete
a saída em português (número sozinho não é resposta).

## Antes de tudo: diagnóstico geral = UMA chamada

Pedido de "busca geral no sistema / como está o dispositivo / o que
está lento" → chame a ferramenta **`diagnostico_sistema`** UMA vez
(disco, RAM, top processos, maiores pastas, bateria, GPU, logins) e
INTERPRETE o digesto em texto. NÃO fique chamando sys_info/df/free um
por um — cada chamada é um ciclo lento do modelo.

## Receitas

| Pedido | Comando |
|---|---|
| espaço em disco | `df -h /` |
| o que mais ocupa a home | `du -sh ~/* 2>/dev/null \| sort -h \| tail -10` |
| arquivos grandes | `find ~ -type f -size +100M 2>/dev/null \| head -15` |
| processo comendo RAM | `ps aux --sort=-%mem \| head -8` |
| memória livre | `free -h` |
| quem ocupa a porta | `ss -tlnp \| grep :PORTA` |
| backup rápido de pasta | `tar czf backup-$(date +%F).tgz PASTA` |
| quantos arquivos tem | `find PASTA -type f \| wc -l` |
| últimos modificados | `ls -lt \| head` |
| tamanho de uma pasta | `du -sh PASTA` |

## Regras

1. Primeiro o comando de LEITURA (df, ps, ss, du) — ver nunca estraga.
2. Interprete: "74% usado, sobra 52 GB — saudável" e não "74%".
3. Ação destrutiva (rm, kill) só com o PID/alvo CONFIRMADO na saída
   anterior — nunca por nome genérico.
4. Combinou com organizar/limpar arquivos? Use a skill
   organizador-arquivos.
