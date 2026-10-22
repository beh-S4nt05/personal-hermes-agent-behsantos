---
name: codigo-javascript
description: "Projetos JavaScript/Node: ESM vs CommonJS, npm, package.json, Express, testes com node:test. Use quando a tarefa envolver javascript, js, node, npm, express, package.json, react, frontend, servidor node ou api javascript."
---
# JavaScript/Node — engenharia de projetos

## Fluxo obrigatório
1. `npm init -y` → definir `"type": "module"` (ESM moderno).
2. Escrever código ESM (`import`/`export`).
3. Testes: `node --test` (nativo, zero deps) — colar a saída.
4. Rodar: `node arquivo.js` — saída real na entrega.

## Estrutura de referência
```
projeto/
├── package.json        # { "type": "module", scripts, deps }
├── src/index.js        # entrada
├── src/rota.js         # módulos por domínio
└── test/index.test.js  # import { test } from 'node:test'
```

## Decisões de sênior
- **ESM** (`import`) em projeto novo; CommonJS só em legado.
- Express p/ API mínima; rotas finas, lógica em módulos puros (testáveis).
- `async/await` com `try/catch` — nunca `.then()` solto sem `.catch()`.
- Validação de entrada na borda (zod/valibot ou manual).

## Armadilhas comuns
- `==` (coerção) — sempre `===`.
- `this` perdido em callback — arrow function.
- Esquecer `await` (Promise pendente vira silêncio).
- Node desatualizado: checar `node -v` (precisa ≥ 18 p/ `node:test`).

## Verificação antes de entregar
`node --test` verde · `node src/index.js` roda sem exceção · saída colada.
