---
name: codigo-typescript
description: "TypeScript profissional: tsconfig strict, tipagem de domínio, interfaces vs types, build e testes. Use quando a tarefa envolver typescript, ts, tsconfig, tipagem, tipos, interfaces, generics, react com tipos ou node com typescript."
---
# TypeScript — engenharia de projetos

## Fluxo obrigatório
1. `npm i -D typescript` + `tsconfig.json` com `"strict": true`.
2. Modelar o DOMÍNIO primeiro (types/interfaces), depois o código.
3. `npx tsc --noEmit` (typecheck) + testes (`node --test` com tsx).
4. Build: `npx tsc` → `dist/`.

## tsconfig essencial
```json
{ "compilerOptions": { "target": "ES2022", "module": "NodeNext",
  "moduleResolution": "NodeNext", "strict": true, "outDir": "dist",
  "skipLibCheck": true } }
```

## Decisões de sênior
- `interface` p/ objetos extensíveis; `type` p/ uniões/interseções.
- Tipar a fronteira (API/IO) e deixar o meio INFERIR — não anotar tudo.
- `unknown` + validação na entrada; **nunca `any`** (desliga o compilador).
- Union discriminada p/ estados (`{kind:'loading'}|{kind:'ok',data}`).

## Armadilhas comuns
- `!` (non-null) para calar o compilador — validar de verdade.
- `as` cast sem validação — mentira tipada que explode em runtime.
- Enums: preferir `as const` + union de strings.

## Verificação antes de entregar
`npx tsc --noEmit` zero erro · testes verdes · build roda.
