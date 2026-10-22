---
name: release-disciplinada
description: Publicar versões de software com segurança — bump de versão, changelog honesto, suíte de testes verde, checagem de segredos, tag e pacote. Use quando a tarefa envolver "versão", "release", "publicar", "changelog", "tag", "empacotar" ou distribuir código para outros.
---

# Release disciplinada

Versão publicada é compromisso público. O processo existe para que
nenhuma regressão, segredo ou promessa falsa escape.

## Passos (nesta ordem)

1. **Testes verdes primeiro**: a suíte inteira passa? Vermelho não
   sobe, sem exceção.
2. **Bump de versão** em TODOS os lugares que declaram versão
   (config, pyproject/package.json…). Versão em dois lugares
   diferentes = bug esperando.
3. **Changelog honesto**: o que mudou, por quê, e AS LIÇÕES — bug
   corrigido entra com a causa. Changelog que só lista vitórias mente.
4. **Checagem de segredos** ANTES de qualquer push:
   `git grep -iE "(senha|secret|token|password|api_key)"` — revise cada
   hit. Credencial no repo público é incidente.
5. **Tag e pacote**: tag anotada da versão + zip/pacote testável por
   quem baixa (instalação limpa funciona?).
6. **Push e verificação**: suba, confirme a tag no remoto e teste o
   pacote publicado — o que o usuário baixa é o que vale.

## Regra de ouro

Se a release quebrou algo que funcionava, o próximo changelog começa
admitindo isso. Confiança se constrói em release honesta.
