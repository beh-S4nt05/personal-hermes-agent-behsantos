---
name: codigo-java
description: "Java moderno: Spring Boot, Maven/Gradle, records, streams, JUnit. Use quando a tarefa envolver java, spring, spring boot, maven, gradle java, junit, jvm, war ou jar empresarial."
---
# Java — engenharia de projetos

## Fluxo obrigatório
1. `spring initializr` (start.spring.io) ou `mvn archetype` p/ projeto puro.
2. Java 17+ (records, switch expressions, text blocks).
3. Testes: JUnit 5 + AssertJ (`mvn test`) — colar a saída.
4. Build: `mvn -q package` → `target/*.jar`.

## Estrutura Spring Boot
```
src/main/java/pacote/
├── App.java (@SpringBootApplication)
├── controller/  (REST, fino)
├── service/     (regra de negócio)
├── repository/  (Spring Data JPA)
└── model/       (record/entity)
```

## Decisões de sênior
- `record` p/ DTOs imutáveis; entity JPA só onde persiste.
- Injeção por **construtor** (testável, sem @Autowired em campo).
- Streams p/ transformação (`map/filter/collect`) — legível, não esperto.
- Exceções de negócio + `@ControllerAdvice` (resposta de erro coerente).

## Armadilhas comuns
- Getter/setter para tudo (JavaBeans 2005) — preferir imutabilidade.
- `Optional.get()` sem checar — `orElse/orElseThrow`.
- N+1 em JPA (`fetch`/`@EntityGraph` em relacionamentos).

## Verificação antes de entregar
`mvn test` verde · `java -jar target/app.jar` sobe · saída real.
