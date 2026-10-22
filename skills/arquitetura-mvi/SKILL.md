---
name: arquitetura-mvi
description: "Arquitetura MVI (Model-View-Intent): estado único imutável, fluxo de dados unidirecional, reducer. Use quando a tarefa envolver mvi, model view intent, estado único, unidirecional, reducer, event driven, arquitetura reativa, compose mvi ou redux."
---
# MVI — Model · View · Intent

## O mapa
- **Intent**: a intenção do usuário como DADO (`sealed class Carregar`).
- **Model/Reducer**: função pura `(Estado, Intent) → Estado novo`.
- **View**: renderiza o estado; emite intents. Nada mais.

## O ciclo (rígido e simples)
```
Intent ──► Reducer ──► Estado (imutável, único) ──► View ──► Intent...
              └── efeitos colaterais isolados (side-effect channel)
```

## Regras de sênior
- **Um só estado** para a tela (data class com TUDO: carregando, dados, erro).
- Estado **imutável** (`copy()`), nunca mutar.
- Side-effects (navegação, toast, log) num canal separado — fora do estado.
- Reducer puro → testável com tabela (estado × intent → estado).

## Por ecossistema
- **Compose**: `stateIn` + `Immutable` data class (Circuit, MVIKotlin).
- **React/Redux**: literalmente MVI (action = intent, store = reducer).
- **Kotlin Flow**: `StateFlow` como contêiner do estado.

## MVVM × MVI
MVVM: vários observáveis, flexível — telas médias/formulários.
MVI: estado único previsível — fluxos críticos, time grande, debug fácil.

## Verificação
Reducer testado puro · sem estado duplicado na View · intents tipadas.
