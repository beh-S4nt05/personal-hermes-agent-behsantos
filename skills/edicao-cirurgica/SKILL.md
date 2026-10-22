---
name: edicao-cirurgica
description: Editar arquivos com precisão cirúrgica — localizar a âncora exata, conferir que ela é única, aplicar um ponto por vez e verificar (compilar/testar) depois de cada mudança. Use quando a tarefa envolver "editar", "modificar", "corrigir", "ajustar", "patch" ou mudar código/config existente sem quebrar o resto.
---

# Edição cirúrgica de arquivos

Alterar código não é reescrever: é substituir o trecho certo, do menor
jeito possível, e PROVAR que nada quebrou.

## Regras

1. **Âncora exata antes de tudo**: leia o arquivo, copie o texto exato
   do trecho a alterar (com a indentação real) e confirme que ele
   aparece UMA vez no arquivo (grep). Âncora genérica = patch no lugar
   errado.
2. **Um ponto por vez**: várias mudanças? Uma de cada vez, com
   verificação entre elas. Nunca um patch gigante.
3. **Nunca reescreva o arquivo inteiro** quando dá para substituir um
   trecho — diff pequeno é revisável e seguro.
4. **Verifique após cada edição**:
   - Python: `python3 -m py_compile <arquivo>`
   - JS/HTML: abra no navegador e veja o console sem erros
   - Config: valide o YAML/JSON
5. **Rollback se quebrou**: se a verificação falhar, reverta a mudança
   e só então investigue — arquivo funcionando > arquivo "quase pronto".

## Por quê

A âncora errada edita o lugar errado em silêncio — o pior tipo de bug.
E verificação imediata encontra o erro enquanto ele tem 3 linhas de
contexto, não 3 dias.
