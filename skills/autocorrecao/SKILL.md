---
name: autocorrecao
description: Quando um comando falha ou dá erro, corrigir localmente e repetir — ler a mensagem de erro real, classificar a causa (caminho errado, dependência ausente, permissão negada, porta ocupada), ajustar o comando e tentar de novo sem replanejar a tarefa inteira. Use quando algo falhou, deu erro, não funcionou, precisar tentar de novo ou o comando retornou mensagem de erro.
---

# Autocorreção de comandos

Erro não é fracasso da tarefa — é informação. Corrija local e siga.

## Fluxo quando um comando falha

1. **Leia a mensagem de erro REAL** (última linha costuma ser a causa:
   "No such file", "Permission denied", "port is already in use",
   "command not found").
2. **Classifique e corrija**:

| Causa | Correção |
|---|---|
| caminho errado / arquivo não existe | `ls` no diretório pai, ache o nome certo, repita corrigido |
| command not found | dependência ausente: instale (`pip install X` / `sudo apt install X`) e repita |
| Permission denied | verifique permissão; `sudo` apenas para ferramenta padrão — nunca em arquivos do operador sem avisar |
| porta já em uso | `ss -tlnp \| grep :PORTA` → trate o dono ou troque a porta |
| timeout / demora | reduza o escopo (menos arquivos, uma pasta por vez) e repita |

3. **Repita O COMANDO AJUSTADO** — a tarefa não volta ao planejamento:
   o objetivo continua válido, só o caminho falhou.
4. **Limite: 2 correções** por comando. Depois disso, pare e reporte
   honesto: o que tentou, o erro exato, e o que impediu.

## Proibido

- Re-planejar a tarefa toda por causa de um erro local.
- Repetir o comando IDÊNTICO esperando resultado diferente.
- Esconder o erro ("não funcionou" sem a mensagem real não serve).
