# 🔬 Engenharia Reversa — Claude Code × Hermes Agent

> Estudo comparativo dos **2 agentes do operador**, extraindo os pontos
> positivos e diferentes de cada um para aplicar no Hermes Agent.
> out/2026 · base Hermes **v3.14.2** (106/106) · complementa o `MAPA_APLICACAO.md`

---

## 0. Método e limites — o que "engenharia reversa completa" significa aqui

- O Claude Code é um **bundle JS minificado e fechado** — não decompilamos.
- Reconstruímos **100% dos mecanismos públicos** a partir de: documentação
  oficial (code.claude.com), dissecação sistemática do código (VILA-Lab,
  arXiv), análises de prompts extraídos pela comunidade, changelog oficial
  — e dos **transcripts reais do campo do operador** (3 relatos).
- **Ética/legal**: reimplementamos *padrões* com nossas palavras e para o
  nosso contexto (modelo local 8B). Nenhum prompt da Anthropic é copiado.
- O lado **Hermes já foi desmontado** na v3.14.2 → `MAPA_APLICACAO.md`.

---

## 1. Claude Code desmontado — os 10 mecanismos que importam

### 1.1 O loop agêntico (o coração)
Toda task passa por 3 fases que se misturam: **reunir contexto → agir →
verificar resultados**, repetindo até concluir. O loop é um `while(tool_use)`:
o modelo responde texto (terminou) ou chamadas de ferramenta (continua);
o harness executa, injeta o resultado de volta e chama o modelo de novo.
Uma task típica roda **5–50 iterações**. O modelo nunca toca o sistema —
ele *pede*, o harness *executa*.

### 1.2 A descoberta-chave: 98,4% é infraestrutura determinística
A dissecação sistemática (VILA-Lab) mediu: **apenas 1,6% do código do CC é
lógica de decisão de IA**. Todo o resto é determinístico: portões de
permissão, gestão de contexto, roteamento de ferramentas e **recuperação**
(retry com escalagem de limite de saída, compactação reativa, fallback de
modelo). **Implicação para nós:** os guards, sandbox, aprovações e revisor
do Hermes são exatamente a categoria certa — é onde a engenharia de verdade
morava o tempo todo.

### 1.3 Gestão de contexto em 5 estágios
Antes de cada chamada ao modelo, o contexto passa por: **Budget Reduction →
Snip → Microcompact → Context Collapse → Auto-Compact**. O auto-compact
dispara perto do limite da janela (~95%) e o operador pode antecipar
(`/autocompact N`). O pipeline por turno tem 9 passos fixos, do settings
à condição de parada.

### 1.4 O que SOBREVIVE à compactação (a lista de re-injeção)
Esta é a joia do design — após compactar, o CC **re-injeta do disco**:
system prompt · **CLAUDE.md da raiz do projeto** · auto-memory ·
descriptions das skills · **git status fresco** · o plano escrito no plan
mode · **até 5 arquivos lidos/editados recentemente** (re-lidos) · corpos
de skills invocadas (teto 5k/skill, 25k total). Comandos em background
continuam rodando. **Nada importante se perde — só o ruído sai.**

### 1.5 Memória hierárquica e preguiçosa
- `CLAUDE.md` **por subdiretório**: só carrega quando o Claude toca um
  arquivo daquela subpasta (custo de contexto só quando é relevante).
- `AGENTS.md` é aceito no lugar (padrão emergente multi-agente).
- **Auto-memory** (`MEMORY.md`): aprendizados que o próprio agente salva
  trabalhando; primeiras 200 linhas/25KB entram a cada sessão.

### 1.6 Sub-agentes com contrato rico (ferramenta Task)
Cada sub-agente roda em **contexto próprio** (protege o contexto principal
de resultados volumosos), com frontmatter: `model`, `tools`,
`disallowedTools`, `maxTurns`, `background`, `isolation` — e **`memory:
user|project|local` = aprendizado entre sessões com escopo**. Sub-agente
fork roda em background e mantém a saída fora do contexto principal.

### 1.7 Do TodoWrite ao Task tool (a lição do plano vivo)
O CC forçava lista de tarefas rígida (TodoWrite) — e **isso travava o
modelo** no plano original quando ele deveria se adaptar. Substituíram por
um Task tool com dependências, atualização compartilhada entre sub-agentes
e liberdade de alterar/apagar. Modelos mais novos nem expõem mais o
TodoWrite. **Lição: plano visível sim, rígido não.**

### 1.8 Hooks de ciclo de vida (determinístico, configurável)
`PreToolUse`, `PostToolUse`, `SessionStart`, `PreCompact`,
`InstructionsLoaded`… — código do usuário roda em eventos do loop e pode
interceptar, modificar ou **bloquear** chamadas de ferramenta. É o nosso
guard de execução/bash-block, mas configurável externamente.

### 1.9 Montagem dinâmica do prompt
O CC **não tem um system prompt** — monta **dezenas de partes** conforme
modo (Plan/Explore/Delegate), ferramentas ativas e estado da sessão; ~2.900
tokens base + descrições de 18–27 ferramentas. Há um limite explícito entre
a parte cacheável (global) e a por-sessão (memória, projeto, MCP).

### 1.10 As falhas documentadas — o espelho do nosso campo
Issues abertas do próprio CC: sub-agentes que retornam **relatório inteiro
confiante com ZERO chamadas de ferramenta** (investigação alucinada) e
lançamentos que **ecoam blocos de instrução estrangeiros** em vez de
executar. É o mesmo fenômeno da nossa recusa de campo e do `/goal` ecoado —
**com o modelo topo da Anthropic**. A mitigação do CC é infraestrutura
determinística (ver 1.2). O modelo pequeno sofre mais; o antídoto é o mesmo.

---

## 2. Hermes Agent — os pontos fortes que o CC NÃO tem

| Exclusividade do Hermes | Por que importa |
|---|---|
| **🔍 Revisor no loop** (critérios + garantidor) | O CC confia na auto-correção do modelo; nós temos QA externo ao modelo |
| **🔒 Aprovação ANTES de executar e ANTES de entregar** criações | O CC pede permissão por ferramenta; nós por consequência |
| **Guard de execução** (comandos escritos sem rodar → Hermes roda e cola saída real) | Ataca exatamente a falha 1.10 |
| **Guard anti-recusa** (2ª chamada com correção) | "Não sou especialista" é tratado como falha de entrega |
| **Skills com casamento automático** por pedido | No CC, skills são invocadas pelo modelo ou manualmente |
| **Modo econômico** (1 modelo residente, zero trocas por task) | Feito para RTX 2050 / ≤8B — o CC presume frontier model |
| **Scheduler com gatilhos** (tempo, watch de arquivos, webhook) + retry | Autonomia de longo prazo sem ninguém no teclado |
| **`hermes selftest`** (matriz modelo×cenário + recomendação) | Medição objetiva de qualidade do agente |
| **Auditoria + GUI "por baixo dos panos"** | Visibilidade total de cada ferramenta chamada |
| **Local-first, zero nuvem** | O CC é cliente de API da Anthropic |

---

## 3. Matriz comparativa — 18 mecanismos × veredicto

| # | Mecanismo | Claude Code | Hermes v3.14.2 | Veredicto |
|---|---|---|---|---|
| 1 | Loop agêntico | `while(tool_use)` 5–50 iterações | pipeline 🎯⚡🔍 + guards | ✔ manter (temos QA a mais) |
| 2 | IA × determinístico | 1,6% / 98,4% | guards+aprovação+sandbox | ✔ validar e **expandir** |
| 3 | Contexto cheio | 5 estágios + auto-compact | `history[-20:]` sem compactar | ⭐ **PORTAR (Bloco C)** |
| 4 | Sobrevive à compactação | re-injeção seletiva do disco | n/a | ⭐ portar a **lista** (C) |
| 5 | Memória de projeto | CLAUDE.md/AGENTS.md lazy por subpasta | memory.json global + goal | ⭐ **PORTAR (Bloco B)** |
| 6 | Auto-memória | MEMORY.md auto-aprendido ≤200 linhas | fatos manuais + lições | ⭐ portar = **treinável** (B) |
| 7 | Memória por escopo | user/project/local (sub-agente) | global | conceito absorvido no B |
| 8 | Sub-agentes | Task tool, contexto próprio, background | papéis com contextos separados | ✔ equivalente; handoff futuro (D) |
| 9 | Plano | Task tool flexível (evolução do TodoWrite) | passos fixos da task | PORTAR plano **vivo** (D) — flexível |
| 10 | Hooks configuráveis | PreToolUse/PostToolUse/PreCompact… | guards internos fixos | ✖ não portar (over-engineering p/ 1 usuário) |
| 11 | Permissões | 7 modos + classificador ML | aprovação criação/entrega + sandbox | ✔ manter o nosso |
| 12 | Prompt | ~2.9k base + dezenas de partes | persona leve + skill + goal | ✖ **não portar o tamanho** (afoga 8B) |
| 13 | Ferramentas | 18–27, até 10 concorrentes | 10, seriais | ✔ serial (modelo pequeno) |
| 14 | Ambiente no prompt | SO, cwd, data, git status | persona sem ambiente | ⭐ **PORTAR (barato, junto do A)** |
| 15 | Sessões | resume/fork/rewind | conversas + backups + restore | ✔ equivalente |
| 16 | Headless | `-p --output-format stream-json` | `run_claude` bare + SSE | ✔ equivalente |
| 17 | Skills | SKILL.md, progressive disclosure | skills + injeção por conteúdo | ✔ equivalente (v3.14.1) |
| 18 | Falha: responder sem executar | acontece (issues abertas) | guard de execução + anti-recusa | ✔ nossa mitigação é a certa |

---

## 4. Plano de adoção (adaptado a modelo 8B local)

### ⭐ Bloco A — Trabalhar no SEU projeto (corrige o bug de campo)
A calculadora SOLID falhou porque o agente roda no workspace do Hermes e o
sandbox bloqueou a pasta do projeto. O CC **sempre** roda no cwd do projeto.
Portar: detectar caminho de projeto na mensagem → rodar com `cwd` da pasta
declarada → escopo de leitura/escrita estendido **àquela task** (mantendo
denylist de pastas sensíveis e aprovação) → injetar ambiente (cwd, data,
SO, `git status` se for repo).

### ⭐ Bloco B — Aprendizado permanente (diretriz do operador)
O padrão CLAUDE.md + auto-memory do CC, na nossa forma: **lições de campo
viram defesa permanente** (o loop que já aplicamos 3× manualmente, virar
produto: registrar a falha → virar regra/fato/skill versionada) e
**memória de projeto** (`hermes.md` na raiz do projeto, lida ao trabalhar
lá — convenções, comandos de build, decisões). O Claude Code ganha os
**fatos do Hermes** injetados (hoje ele não recebe memória nenhuma).

### ⭐ Bloco C — Compactação de contexto (crítico p/ num_ctx 3072)
Com 3072 tokens de janela, o `history[-20:]` estoura muito antes do que no
CC. Portar o padrão de 5 estágios em versão enxuta: ao aproximar do teto,
**resumir** o histórico via LLM **re-injetando do "disco"**: goal da sessão,
skills ativas, fatos da memória, os 5 arquivos/últimos resultados mais
recentes. Conversa longa custa o mesmo que curta — e nada importante se perde.

### ⭐ Bloco D — Plano vivo + handoff
Checklist de passos **com estado** (feito/andando/bloqueado), re-injetado a
cada passo do executor e visível na GUI — flexível como a lição 1.7 (o
modelo pode propor replanejar). Depois: handoff Hermes↔Claude na mesma task
(o "como conversam" — hoje são alternativos).

### O que NÃO portamos (decisão explícita)

| Item | Motivo |
|---|---|
| Prompt de ~3k+ tokens com dezenas de partes | afoga modelo 8B (provado em campo com hermes3:8b) |
| Ferramentas concorrentes / swarm / worktrees | 1 usuário, GPU 4 GB, modelo pequeno |
| Classificador ML de permissão | aprovação explícita é mais simples e correta p/ 1 operador |
| Prompt caching | é otimização da API Anthropic; Ollama local não cobra por token |
| Hooks configuráveis externamente | os guards internos já cobrem; configurabilidade = superfície de erro |

---

## 5. Validação (como cada bloco prova que funcionou)

1. **Testes de suíte** por bloco (padrão T104+: causal, não só presença).
2. **Cenário de selftest** novo por bloco (ex.: C → "conversa longa não
   perde o goal"; A → "task em pasta externa escreve no lugar certo").
3. **Campo**: o operador repete o teste da calculadora na pasta real
   `/media/Arquivos/projetos/2026/` — critério final de aceite.

---

## 6. Fontes

- Documentação oficial: `code.claude.com/docs/en/` — how-claude-code-works,
  context-window, memory (CLAUDE.md), sub-agents, hooks, best-practices,
  model-config, glossary, changelog.
- VILA-Lab, *Dive into Claude Code* (arXiv 2604.14228 + repositório GitHub) —
  dissecação sistemática: loop, 5 estágios de contexto, 9 passos por turno,
  recuperação, 1,6%/98,4%.
- Análises de prompt montado: dbreunig.com; repositórios
  Piebald-AI/claude-code-system-prompts e ku/claude-code-system-prompts.
- Evolução TodoWrite→Task: daily.dev *Seeing like an agent*; issue
  anthropics/claude-code#2177.
- Falhas de alucinação/eco: issues anthropics/claude-code **#67730** e **#90782**.
- Arquitetura single-threaded: ZenML LLMOps (loop "nO"); codewithmukesh
  (anatomia de sessão); promptlayer (master agent loop).
- **Campo do operador**: 3 relatos de transcript (recusa, alucinação de
  `history`, saída crua, `/goal` ecoado 3×, pasta externa bloqueada).
