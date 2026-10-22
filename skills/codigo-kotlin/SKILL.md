---
name: codigo-kotlin
description: "Kotlin profissional: null safety, data classes, coroutines, Gradle Kotlin DSL, Android/Jetpack Compose e Ktor. Use quando a tarefa envolver kotlin, android, jetpack compose, coroutines, gradle kotlin, ktor, apk ou app android."
---
# Kotlin — engenharia de projetos

## Fluxo obrigatório
1. Projeto Gradle (`kotlin("jvm")`) ou Android Studio p/ app.
2. Código idiomático: `val`, data class, expressões `when`.
3. Testes: JUnit 5 (`./gradlew test`) — colar a saída.
4. Build: `./gradlew build` (JDK 17+).

## Decisões de sênior
- **Null safety**: `String?` explícito; `?.` `?:` `let` — nunca `!!`.
- `data class` p/ modelos; `sealed class/interface` p/ estados fechados.
- Coroutines: `suspend` funções + `Dispatchers.IO` p/ rede/disco;
  `viewModelScope`/`lifecycleScope` no Android; **nunca** bloquear a main.
- Compose: UI = função de estado (`@Composable`, estado hoisted).
- Servidor: **Ktor** (leve) ou Spring Boot (completo).

## Estrutura Android/Compose
```
app/src/main/java/pacote/
├── ui/ (tela, componente, tema)   ── estado ↑ eventos ↓
├── data/ (repositório, api)
└── App.kt
```

## Armadilhas comuns
- `!!` em valor que pode ser null (NullPointerException de volta).
- Coroutine global `GlobalScope` (vaza) — usar escopo estruturado.
- Esquecer `buildFeatures { compose = true }` no Gradle.

## Verificação antes de entregar
`./gradlew test build` verdes · app compila · saída real colada.
