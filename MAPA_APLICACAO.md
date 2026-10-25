# 🗺 Mapa da Aplicação — Betterme Agent

> Como o sistema funciona por dentro: módulos, fluxos, dados, segurança e o
> **contexto de cada ponto**. Documento vivo — atualizado a cada release.
> Gerado na **v3.14.2** (auditoria profunda de código + correção de 12 achados).

---

## 1. Visão geral — o mapa geral

```
                         VOCÊ (operador)
              GUI (navegador/PWA) · CLI (terminal) · TUI
                              │  token de acesso
                              ▼
                   ┌─────────────────────────┐
                   │  betterme server (Flask)  │  ← betterme/server/app.py
                   │  71 rotas /api protegidas│
                   └───────────┬─────────────┘
                               │ escolha por mensagem
               ┌───────────────┴───────────────┐
               ▼                               ▼
      🎯 AGENTE HERMES                🔌 AGENTE CLAUDE CODE
      (pipeline local, Ollama)        (CLI claude, modo leve)
      orchestrator.py                 claude_agent.py
      🎯 decidir → 📋 task            persona SÊNIOR + skill injetada
      ⚡ executar (tools)             + goal da sessão (v3.14.1)
      🔍 revisar (critérios)
               └───────────────┬───────────────┘
                               ▼
                      betterme/tools.py  (FERRAMENTAS)
        run_command · read/write_file · list_dir · sys_info ·
        web_search · web_fetch · diagnostico_sistema · backups ·
        git_run (versionar no projeto) · knowledge_search (RAG)
                               ▼
                    🐧 SUA MÁQUA LOCAL (Linux)
        arquivos · sistema · Ollama · e-mail/agenda (MCP, só leitura)
```

**Os 2 agentes não conversam entre si** — são alternativos por mensagem
(seletor na GUI). O Betterme tem memória persistente e pipeline; o Claude Code
tem as ferramentas próprias (Bash/Read/Edit) e executa por fora do pipeline.

---

## 2. Módulos — papel e dependências de cada arquivo

### Núcleo do agente

| Arquivo | Papel | Depende de |
|---|---|---|
| `config.py` | Config central (`~/.betterme/config.yaml` + defaults + flags). Cria a árvore de diretórios no boot. | — |
| `agent.py` | O **chat 💬** do Betterme: monta prompt (persona + memória + contexto), chama `chat_stream` do Ollama, gera tokens SSE. | config, ollama_client, memory, tools, skills, manager, mcp_client |
| `orchestrator.py` | O **cérebro 🎯**: decide rota (conversar × executar), gera tasks, injeta skills + goal + memória, critérios extras de execução, aprovações. | ollama_client, skills |
| `tools.py` | **Ferramentas** com sandbox (`resolve_path`): leitura na home, escrita só no workspace/skills; `diagnostico_sistema` (bateria única); backups automáticos de edição. | memory, backups |
| `claude_agent.py` | **Agente Claude Code**: modo leve (`--bare`), persona sênior, `_enrich_prompt` (skill + goal), guard de execução (executa comandos que o modelo só escreveu), timeout e cleanup. | orchestrator (skills_for), tools |
| `memory.py` | **Memória de longo prazo** (`memory.json`, atômico + lock): fatos do operador, busca por relevância, prompt_section. | — |
| `skills.py` | Catálogo de **skills** (repo + `~/.betterme/skills/`), instalação de repositórios GitHub, toggle. | — |
| `skills_audit.py` | Auditoria do catálogo: frontmatter, duplicatas, injeção, tamanho. | — |

### Infraestrutura

| Arquivo | Papel |
|---|---|
| `server/app.py` | Servidor Flask: **76 rotas** (chat SSE, orchestrator, Ollama, MCP, skills, logs, tools, conversas, agendador, memória, settings, auditoria, backups, métricas, notificações, receitas, doctor, hooks). Imports lazy → boot rápido. |
| `ollama_client.py` | Cliente HTTP do Ollama (chat, streaming, modelos, pull) + fábrica `get_client` (v3.17.0: provedor externo com fallback). |
| `varredura.py` | 🛡 Segurança/privacidade: scanner de segredos (exit 1 = bloqueia push) e DLP `mascarar()` — código/segredos nunca vão a provedores gratuitos (D2). |
| `project_context.py` | 📋 HERMES.md/AGENTS.md root-to-leaf (global+projeto, cap 32 KiB) + `betterme init`; externo recebe versão DLP. |
| `sandbox_kernel.py` | 🧱 Sandbox de kernel: bubblewrap + seccomp BPF (blocklist), modos read-only/workspace-write, fallback honesto p/ denylist. |
| `autonomy.py` | 🎚 Autonomia 3 níveis (cauteloso/padrao/autonomo) + hard gates inejociáveis + varredura pré-entrega do AUTÔNOMO. |
| `specialists.py` | 🧪 ESPECIALISTAS (ADR-001): veredito JSON com evidência validada em disco, pool grátis c/ fallback, exames de competência, DLP, auditoria. |
| `learning.py` | 📚 Loop de aprendizado: rascunhos de skill/lição em staging, aprovação do operador, skills aprender, busca em conversas. |
| `gateway.py` | 📱 núcleo do gateway: comandos compartilhados, notificação de pendências (id+objetivo truncado, sem conteúdo), decisão approve→HTTP. |
| `telegram_gw.py` | 📱 canal Telegram: long-polling, token secrets 600, allowlist de chats. |
| `whatsapp_gw.py` | 📱 canal WhatsApp via Playwright (grátis/local/removível; experimental, extra opcional). |
| `code_manager.py` | 👔 Gerente de código (Claude) — opt-in consciente com aviso de privacidade (D5). |
| `llm_providers.py` | Provedores LLM externos GRATUITOS (OpenAI-compat): registro groq/gemini/mistral/openrouter/llm7/zai/cohere, chave em secrets 600, fallback local — memória NUNCA sai (regra do operador). v3.17.1: chat_stream usa SEMPRE o modelo do provedor (o Agent passa nome Ollama em cfg.model → 400 + fallback silencioso; T127). |
| `manager.py` | Gerência do Ollama: boot/restart (systemd ou `ollama serve` com log), diagnóstico de ambiente. |
| `autoselect.py` | Auto-atribuição de modelos por papel (lê SEMPRE a lista instalada). |
| `conversations.py` | Sessões persistidas (`conversations/*.json`, atômico): histórico recuperável, busca, export. |
| `scheduler.py` | Agendador (ver §10). |
| `mcp_client.py` | Cliente MCP stdio → e-mail/agenda (somente leitura). |
| `audit.py` | Trilha de auditoria de ferramentas (`audit/`). |
| `activity.py` | Log de atividade humana-legível (`logs/agent.log`). |
| `backups.py` | Backup/restauração de arquivos editados (`backups/`). |
| `daemon.py` / `supervisor.py` | Execução em segundo plano + supervisão. |
| `update.py` | Auto-update via tags do GitHub (com defesa zip-slip). |
| `doctor.py` | Diagnóstico do ambiente (CLI, GPU, versões). |
| `selftest.py` | Bateria de cenários com LLM real (`betterme selftest [--all-models]`). |
| `metrics.py` / `notify.py` / `stt.py` / `recipes.py` / `tui.py` / `cli.py` / `emailcfg.py` / `agendacfg.py` | Métricas jsonl · notificações · voz→texto · receitas prontas · TUI · linha de comando · config de e-mail/agenda. |
| `mcp-servers/*.py` | Servidores MCP (IMAP/SMTP e agenda) — stdlib pura. |

### Hubs (mais importados)
`config` ←7 · `ollama_client` ←6 · `agent` ←5 · `manager` ←5 · `memory` ←3 ·
`tools` ←3 · `skills` ←2 · `orchestrator` ←2 · `mcp_client` ←2.
`server/app.py` importa quase tudo **lazy** (dentro das rotas) — por isso o
grafo estático o mostra isolado: boot rápido e zero ciclo de import.

---

## 3. Fluxo de uma mensagem no chat (o coração)

```
GUI/CLI → POST /api/chat {message, history[-20], session_id, agent}
   1. auth (@protected: token)
   2. sessão: valida id ou cria nova; grava a mensagem do usuário ANTES
      da geração (nunca se perde) · set_current
   3. agente = "claude"? → run_claude()            (ver §4)
   4. agente = "betterme":
      a. 💬 conversa comum? → agent.py responde direto (stream SSE)
      b. 🎯 orquestrador decide: rota conversar × executar
         - objetivo + passos + skills que casam (score ≥ 2, máx. 2)
         - CRIAÇÃO → 🔒 aprovação obrigatória (card na GUI) antes de
           executar E antes de entregar
         - goal da sessão (/goal) entra no contexto
         - memória relevante entra no contexto
      c. ⚡ executor roda os passos com tools (cada chamada auditada,
         com timeout, sandbox e backup de arquivo editado)
      d. 🔍 revisor confere critérios (saída real, não recusa, não
         saída crua; código → ESCRITO+EXECUTADO com SAÍDA REAL)
         - reprovação injusta → garantidor devolve resposta boa
         - máx. 2 tentativas (economia de tokens)
      e. 📦 entrega (aprovação se criação) → resposta final no chat
   4d. 🚀 modo missão (v3.16.0): "missão: <objetivo>" → 2-5 subtasks
       sequenciais, cada uma validada; reprovação → task reescrita e
       re-executada; validação final do objetivo inicial + relatório
   4e. 📁 projeto sem caminho (v3.15.1): task de código/projeto sem
       pasta no pedido → o agente PERGUNTA o caminho; a resposta retoma
       a task com escopo forçado (pasta buscada/criada)
   4f. 🧠 compactação (v3.15.0): perto de 55% do num_ctx, o MEIO da
       conversa vira resumo (LLM com fallback) — tarefa original e
       resultados recentes preservados
   5. tudo vira eventos SSE: session, brain, step, note, token,
      tool_start, tool_end, done, error, cancelled
```

**Modo econômico (padrão)**: 🎯🔍⚡ herdam o modelo do 💬 chat — 1 modelo
residente, zero troças de modelo por task. Por papel só com `--multi`.

---

## 4. Fluxo do agente Claude Code

```
run_claude(cfg, message, history, goal)  ← goal chega desde a v3.14.1
   1. mock? → _simulate (demo sem Ollama)
   2. claude_path() · _cli_version() (cacheada)
   3. _claude_cmd: modo leve --bare --max-turns 4
      --append-system-prompt CLAUDE_LIGHT_PROMPT
      --allowedTools Bash,Read,Edit · cwd = workspace do Betterme
   4. prompt = histórico serializado + _enrich_prompt:
      [SKILL <nome> — conteúdo até 1800 chars] + [🎯 OBJETIVO DA SESSÃO]
   5. Popen → lê JSONL do stdout → emite os MESMOS eventos do chat
   6. guard de execução v3.0.2: modelo escreveu comandos sem rodar?
      → Betterme executa e cola a saída real (auditada)
   7. guard anti-recusa: negou/perguntou em vez de responder?
      → 2ª chamada com correção (_guard=True)
   8. finally: terminate + wait(5s) + kill — sem processo zumbi (v3.14.2)
```

Persona (v3.14.1): **ENGENHEIRO DE SOFTWARE SÊNIOR** — "o especialista da
casa"; RECUSAR TAREFA é FALHA GRAVE; assunto novo → aprende na hora
(Read/Bash); código → arquivo completo + execução com saída colada.

A CLI do Claude Code é **plugin opcional** (v3.15.0): sem ela o Betterme
cobre tudo — a GUI nem mostra a opção e tarefas agendadas caem no loop
nativo com nota. O Ollama fica só com o papel de servir o modelo.

---

## 5. Skills — catálogo, casamento e injeção

- **39 skills** em `skills/` (repo) + `~/.betterme/skills/` (do operador).
- **Nativas de qualquer fonte** (v3.15.0): baixou do GitHub (zip/pasta/
  URL/owner-repo) → `betterme skills import` ou **autoscan** (boot + 10 min
  no agendador; default varre `~/Downloads`, zips incluídos) → skill em
  `~/.betterme/skills/`, ativa por padrão, cache invalidado na hora.
- **Delegação** (v3.15.0): skill casada = MANUAL DA TAREFA no executor; a
  seção `## Verificação` da skill vira critério do 🔍 revisor.
- **Casamento** (`skills_for`): palavras do pedido (≥4 letras, sem
  stopwords) × nome+descrição da skill; **score ≥ 2** (duas palavras).
  - Por que ≥2 e não casar por nome? Ambiguidade real: "memória" (RAM do
    sistema) casaria com `memoria-contexto` (memória do agente). Testado
    e rejeitado na v3.14.1 — o vocabulário correto vive na DESCRIPTION
    (ex.: codigo-verificado cita javascript, node, calculadora…).
- **Injeção**: pipeline 🎯 (T2/T3) recebe até 2 skills; Claude Code
  recebe até 1 (conteúdo até 1800 chars — modo leve enxuto).
- **Criação**: o agente pode propor skills novas → 🔒 aprovação/edição
  obrigatória antes de gravar.
- **Auditoria**: `betterme skills audit` — frontmatter, duplicatas,
  injeção, tamanho, description curta.

---

## 6. Memória e aprendizado (o "melhorar dia a dia")

| Camada | Onde | Como melhora |
|---|---|---|
| Fatos do operador | `memory.json` (atômico+lock) | "lembre que…" · GUI · `betterme memory import` |
| Memória do operador (privada) | **fora do repo**, arquivada em `~/.betterme/` | protocolo de importação |
| Experiência de execução | tasks + auditoria | edições do operador viram few-shot |
| Medição | `betterme selftest [--all-models]` | matriz modelo×cenário + recomendação |
| Skills | catálogo | novas habilidades = novo comportamento |

O pipeline injeta memória relevante por task; o chat injeta `prompt_section`.
O Claude Code é efêmero por request — sua "melhoria" vem da persona + skills
injetadas (memória própria dele: limite conhecido, ver §14).

---

## 7. Dados em disco — `~/.betterme/`

```
~/.betterme/
├── config.yaml                  ← configuração do operador
├── workspace/                   ← cwd das ferramentas; ÚNICO lugar
│                                   onde o agente escreve livremente
├── memory.json                  ← fatos (atômico)
├── conversations/               ← sessões do chat (atômico) + current
├── orchestrator_tasks.jsonl     ← tasks (append-only)
├── session_goals.json           ← /goal por sessão (atômico, v3.14.2)
├── pending_approvals.json       ← fila de aprovação (atômico, v3.14.2)
├── schedules/                   ← tarefas agendadas
├── skills/                      ← skills do operador (escrita permitida)
├── biblioteca/                  ← livros do operador (RAG local)
├── secrets/                     ← credenciais 600 — NUNCA no modelo
├── audit/                       ← trilha de ferramentas
├── backups/                     ← cópias de arquivos editados
├── logs/agent.log · ollama.log  ← atividade
├── notifications.json · metrics.jsonl · heartbeat.json · ollama.pid
```

**Regra de escrita**: state em JSON sempre **tmp + replace** (atômico —
crash no meio não corrompe). Históricos append-only em JSONL com limite
de retenção (20 execuções, saídas ≤4000 chars).

---

## 8. API — 76 rotas em grupos

| Grupo | Rotas |
|---|---|
| GUI/PWA (públicas) | `/` · `/manifest` · `/sw.js` · `/icon-*` · preflight OPTIONS |
| Chat | `/api/chat` (SSE) · `/api/chat/command` (slash) · `/api/chat/approve` · `/api/approvals/pending` |
| Orquestrador | `/api/orchestrator/tasks` · `/stats` · `/api/tasks` (+clear) |
| Ollama | `/api/ollama/models` · `library` · `pull` · `pull/cancel` · `delete` · `restart` · `boot` · `diagnose` · `test` · `auto-assign` · `/api/agent/<action>` |
| Ferramentas | `/api/tools` · `run` · `list_dir` · `read_file` · `write_file` · `sys_info` · `web_search` · `web_fetch` |
| Skills | `/api/skills` · `content` · `toggle` · `install` |
| Conversas | `/api/conversations` · `<sid>` · `search` · `delete` · `current` · `export` |
| Agendador | `/api/schedules` · `toggle` · `delete` · `run` · `live` · `/api/hooks/<sid>` (webhook) |
| Memória/Settings | `/api/memory` (+update/delete) · `/api/settings` |
| Observabilidade | `/api/logs` (+clear/stream SSE) · `/api/audit` · `/api/metrics` · `/api/notifications` (+read) · `/api/status` · `/api/doctor` |
| Outros | `/api/mcp` (+start/restart/add/test) · `/api/backups` (+restore) · `/api/recipes` · `/api/stt` (+status) |

Todas as `/api/*` de dados têm `@protected` (token). Catch-all `/api/<rest>`
responde apenas preflight CORS (204) — sem buraco.

---

## 9. Segurança — camadas empilhadas

1. **Auth**: token em todas as rotas de dados (71 protegidas).
1b. **Privacidade de LLM externo** (v3.17.0): memória/dados pessoais nunca
     são enviados a provedores (injeção só em cliente local); chaves em
     `secrets/` 600; fallback local; ferramentas sempre locais.
2. **Sandbox de arquivos** (`resolve_path`): leitura na home; escrita SOMENTE
   em workspace/ e skills/; pastas sensíveis negadas mesmo com sandbox off.
3. **Segredos**: `secrets/` modo 600, fora do repo, fora do modelo, fora de
   logs/auditoria/config; denylist bloqueia vazamento mesmo se o modelo tentar.
4. **Aprovações**: criação e entrega de tarefas passam pelo operador.
5. **Auditoria**: toda ferramenta registrada (o que rodou, o que devolveu).
6. **Rede**: web_search/web_fetch com timeout e limites de tamanho.
7. **Update**: zip do GitHub validado contra **zip-slip** (v3.14.2) — nenhum
   membro do zip escapa do diretório de destino.
8. **Comandos**: timeout por comando (≤600 s), bateria de diagnóstico com
   teto por seção, guard bloqueia padrões destrutivos (`_BASH_BLOCK_RE`).

---

## 10. Agendador (scheduler.py)

- Loop `tick()` a cada intervalo, em thread daemon; **tick inteiro protegido
  por try/except** — nenhum job derruba o loop.
- **Sem disparo duplo**: `_execute` grava `running=True` no disco ANTES de
  executar; tick pula entradas running.
- Gatilhos: tempo (diário/horário/once) · **watch** (arquivos novos em pasta) ·
  **webhook** (só via POST `/api/hooks/<id>`).
- Retry com backoff (`retry_at_ts`), máximo de tentativas configurável.
- Execução ao vivo: eventos SSE por job (`/api/schedules/live`).
- Tarefa "once" perdida (horário passou +10 min sem rodar) → marcada
  `perdida`, não fica disparando às 3h da manhã.
- Limite conhecido: cada job roda em thread própria, sem semáforo global de
  concorrência (ok para dezenas de jobs; documentado como decisão).

---

## 11. MCP (e-mail/agenda)

`mcp_client.py` fala com servidores stdio (`mcp-servers/*.py`, stdlib pura).
Conta Gmail/Workspace em **somente leitura** (IMAP). Credenciais em
`secrets/`, nunca no modelo. `/api/mcp/test` valida conexão na GUI.

---

## 12. Update e backups

- `betterme update`: consulta a última tag no GitHub → baixa zip → valida
  zip-slip → extrai → aplica preservando `data/`, `.venv` e `.git`.
- `backups.py`: toda edição de arquivo pelo agente gera cópia datada;
  restaurável pela GUI; `prune` mantém o histórico enxuto.

---

## 13. Testes — a rede de proteção

`tests/run_all.py` — **156 casos** (v4.3.0), famílias:
unidades de módulo · sandbox/segurança · pipeline E2E (chat real com
Ollama) · skills (precisão, estresse 30, auditoria) · Claude Code
(persona, skills, goal, guard) · GUI (fonte) · scheduler · conversas ·
memória · update · **QA do QA** (o teste que pega resposta ruim de
verdade em transcript) · selftest/matriz. Padrão de release: 100% verde
+ ruff `E9,F,B,PLE` limpo.

---

## 14. Decisões de arquitetura (o porquê de cada coisa)

| Decisão | Motivo |
|---|---|
| Imports lazy no `server/app.py` | boot rápido, zero ciclo de import |
| Escrita atômica tmp+replace | crash nunca corrompe state |
| Score ≥ 2 no casamento de skills | ambiguidade real (memória RAM × memória do agente) |
| 1 modelo residente (modo econômico) | troca de modelo custa 30-60 s em hardware modesto |
| Zero-build vanilla JS na GUI | sem node_modules, sem build, sem quebrar |
| Guard de execução no Claude | modelo local pequeno às vezes escreve sem rodar |
| Guard anti-recusa | "não sou especialista" é falha de entrega (campo) |
| Skill injetada por CONTEÚDO no Claude | o modelo pequeno não sabe usar só o nome |
| Limites conhecidos | sem handoff Betterme↔Claude na mesma task · Claude sem memória entre sessões · scheduler sem semáforo de concorrência · skills por palavra-chave (não semântica) |

---

## 15. Correções da auditoria v3.14.2 (as pequenas falhas)

| # | Achado | Correção |
|---|---|---|
| 1 | `/goal` ecoado 3× com linhas duplicadas (campo) | guarda `state.cmdBusy` no `runSlash` + comando renderizado 1× |
| 2 | `set_goal`/`_pending_save` gravavam direto | tmp+replace atômico |
| 3 | processo do Claude não era recolhido no finally | `wait(5)` + `kill` |
| 4 | fd do log do Ollama vazava a cada boot | `try/finally: logf.close()` |
| 5 | import deprecated `typing.Iterator` | `collections.abc` |
| 6 | `base64` importado sem uso (email_server) | removido |
| 7 | mcp-servers sem bit executável | `chmod +x` |
| 8-10 | if aninhado · startswith repetido · `check=False` implícito ×5 | explicitados |
| 11 | zip do update sem defesa zip-slip | `_assert_zip_seguro` (testado com zip malicioso) |

Cobertura auditada: grafo de imports, 161 achados de lint triados (56
try-except-pass **intencionais** — sandbox defensivo; 55 blind-except
idem), persistência, scheduler (sem race de disparo duplo), auth de
rotas (71/71), SSE, Popen cleanup, sandbox de caminhos, update, backups.
