---
name: cicd-github-actions
description: "CI/CD com GitHub Actions: workflows, matrix, cache, secrets e releases. Use quando a tarefa envolver ci, cd, pipeline, github actions, workflow, integração contínua, deploy automático, testes no pipeline ou release automatizada."
---
# CI/CD — GitHub Actions

## Workflow mínimo (`.github/workflows/ci.yml`)
```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4        # ou setup-java/setup-python
        with: { node-version: 22, cache: npm }
      - run: npm ci                        # instala EXATO do lockfile
      - run: npm test -- --if-present
      - run: npx tsc --noEmit --if-present
```

## Regras de sênior
- **CI falha = merge bloqueado** (branch protection). Sem exceção.
- `npm ci`/`pip install -r` (lockfile) — nunca `npm install` no CI.
- `cache:` do setup (deps) — CI 2-5× mais rápido.
- Matrix p/ multi-versão: `{ strategy: { matrix: { node: [20, 22] } } }`.
- Deploy (`cd.yml`) separado do CI, no evento certo (tag `v*`).

## Segredos
- NUNCA no yaml — `secrets.NOME` (Settings → Secrets → Actions).
- Segredo no log = rodar `hermes` rotação + remover do histórico.

## Release
```
tag v1.2.3 → job release → build → attach artefatos → GitHub Release
```
Changelog por tag; versão semântica (maj.min.patch).

## Armadilhas
- `latest` deploy sem tag (ninguém sabe o que está em produção).
- Workflow sem `permissions:` mínimo (GITHUB_TOKEN largo demais).
- Cache poisoning (cache antigo > lockfile novo).

## Verificação
CI verde no PR · artefato anexado · rollback = redeploy da tag anterior.
