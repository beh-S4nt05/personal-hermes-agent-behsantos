# 📘 Betterme Agent — Documentação viva: uso, evolução e funções

**Versão 6.2.0** · gerado em 25/10/2026 · este documento é extraído do
código-fonte (parser AST) e do CHANGELOG — funções, endpoints e versões
refletem exatamente o que está instalado. O histórico detalhado, versão a
versão, está no `CHANGELOG.md`; o manual completo de operação no `docs.md`.

---

## 1. O que é o Betterme Agent

Um **agente pessoal que roda na SUA máquina** (Linux, local-first):
conversa por chat, executa tarefas de verdade (shell, arquivos, web,
e-mail, agenda) usando modelos locais do **Ollama** (≤ 8B), com GUI web
de controle em `localhost:8080` — zero nuvem, zero dado saindo do
computador. O Claude Code entra como 2º agente opcional.

**Princípios que não negociam:**
- 🏠 **local-first**: tudo em `~/.betterme`; funciona offline;
- 🎯 **pipeline padrão**: conversa comum responde direto; pedido de
  tarefa → 🎯 orquestrador → [🔒 aprovação] → ⚡ executor → 🔍 revisor
  → [📦 entrega] → done;
- ✋ **o operador manda**: criação de arquivo exige aprovação/edição
  antes de executar E antes da entrega (desligável);
- 🤝 **o agente executa e entrega** — nunca instrui o usuário a
  executar ou verificar;
- 🔑 **segredos jamais vazam** (denylist, secrets fora do repo);
- 🧠 **aprende com o uso**: edições e reprovações viram experiência do
  planejador; tudo é registrado e medido.

## 2. Como usar no dia a dia

### 2.1 Instalar e atualizar
```bash
./install.sh                  # instalação completa (Debian/Ubuntu/Fedora/Arch)
betterme update                 # ⬇ atualiza em 1 comando (tags do GitHub)
betterme update --check         # só verifica se há versão nova
```
O `update` preserva `data/` (suas conversas, memória, config), `.venv`
e `.git`.

### 2.2 Ligar e desligar (ciclo de vida)
```bash
betterme server                 # ▶ liga a GUI — http://localhost:8080
# Ctrl+C desliga. Não existe serviço no boot por padrão.
```
- Instalação com `install.sh --with-systemd` cria os services
  (`betterme-server`, `betterme-agent`) — `sudo systemctl disable --now
  betterme-server betterme-agent` remove.
- **O "fantasma do cache"**: com o servidor desligado o navegador ainda
  pode abrir a página (service worker guarda a casca). Desde a v3.11.1
  ela exibe um **banner vermelho "server OFFLINE"**. Para limpar de
  vez: F12 → Application → Service Workers → *Unregister* → *Clear
  site data*.

### 2.3 A GUI, aba por aba
| Aba | O que faz |
|---|---|
| **Painel** | status do agente/Ollama, desempenho (tok/s) e **🎯 Saúde do pipeline**: aprovação na 1ª tentativa (%), tentativas médias, duração média, suas edições, skills top, tasks por dia (v3.10) |
| **Chat** | conversa + pipeline; 🔒 aprovação de plano (só criação), 📦 entrega editável; 🔬 por baixo dos panos; `/comandos`; `goal` de sessão; pendências de antes de um restart reaparecem no topo (v3.11) |
| **Ollama** | TODOS os modelos instalados + **papel de cada um** (💬 chat · 🎯 orquestrador · 🔍 revisor · ⚡ executor · 🔌 claude) com atribuição em 1 clique; funciona com servidor desligado (cache) (v3.9) |
| **Skills** | catálogo (18 embutidas), ativar/desativar, criar com `criar-skill`, auditar com `betterme skills audit` (v3.11) |
| **Tarefas** | fila do daemon + ⏰ agendadas |
| **Auditoria / Memória / Ferramentas / Ajustes** | rastro de ações, fatos lembrados, toggles e modelos por papel ao vivo |

### 2.4 O fluxo de aprovação (o coração do controle)
```
pedido de CRIAÇÃO → 🎯 plano → 🔒 você aprova/EDITA/cancela
  → ⚡ execução (ferramentas reais) → 🔍 revisão (âncoras do plano)
  → 📦 entrega → você entrega/EDITA/refaz → ✅ done
```
Cada decisão é registrada em `orchestrator_tasks.jsonl`; **edições
viram experiência** do próximo planejamento (v3.10); pendências
sobrevivem a restart (v3.11). Máximo 2 tentativas automáticas.

### 2.5 CLI completa

| Comando | O que faz |
|---|---|

| `betterme update` | atualiza o agente a partir do GitHub |
| `betterme memory` | memória de longo prazo do agente |
| `betterme import` | importa fatos para a memória (JSON lista ou  |
| `betterme list` | lista os fatos da memória do agente |
| `betterme clear` | apaga TODOS os fatos da memória (reimporte um pacote limpo depois) |
| `betterme skills` | catálogo de skills |
| `betterme import` | importa skills: pasta local, .zip, URL git ou owner/repo |
| `betterme aprender` | transforma arquivo/URL/texto em rascunho de skill (M6.5) |
| `betterme scan` | varre pastas assistidas (ex.: ~/Downloads) e importa skills novas |
| `betterme audit` | audita todas as skills: estrutura, tamanho,  |
| `betterme chat` | chat interativo no terminal |
| `betterme selftest` | 🧪 bateria de aceitação com o LLM real: sem  |
| `betterme provider` | provedores LLM externos gratuitos (memória nunca sai) |
| `betterme list` | lista provedores gratuitos e o atual |
| `betterme set` | ativa um provedor (pede a chave com segurança) |
| `betterme test` | ping + 1 completion real do provedor ativo |
| `betterme off` | volta ao Ollama local |
| `betterme varredura` | varre segredos/dados pessoais antes de expor código (pré-push) |
| `betterme init` | cria HERMES.md (instruções duráveis do projeto) |
| `betterme autonomia` | nível de autonomia do agente (cauteloso|padrao|autonomo) |
| `betterme gerente` | gerente de código (Claude Code) — opt-in consciente |
| `betterme telegram` | canal Telegram: controle e aprovação pelo celular |
| `betterme whatsapp` | canal WhatsApp via Playwright — grátis, local, removível |
| `betterme arena` | 🏟️ roda a MESMA task nos provedores grátis e ranqueia (v4.3.0) |
| `betterme grafo` | 🗺️ grafo de código: onde está a lógica de X? (v4.4.0) |
| `betterme build` | constrói o grafo AST do projeto (SQLite no data-dir) |
| `betterme query` | busca símbolos por nome (função/classe/método) |
| `betterme path` | traça o caminho de chamadas A → B |
| `betterme revisar` | 🔍 revisa o git diff HEAD (gate único pré-push; v4.5.0) |
| `betterme transcrever` | extrai áudio (ffmpeg) → whisper.cpp  |
| `betterme vida` | 🌅 Modo Vida: relatório diário + curadoria de  |
| `betterme fluxos` | ⚙️ fluxos n8n LOCAIS — automações visuais no  |
| `betterme aprendidos` | rascunhos de skills/lições esperando sua aprovação |
| `betterme conversas` | conversas passadas do agente |
| `betterme rag` | biblioteca de livros (RAG local): indexa ou consulta |
| `betterme doctor` | diagnostica a conexão Ollama↔Python (com geração de teste) |
| `betterme email` | configura contas de e-mail (MCP email_*) |
| `betterme agenda` | agenda Google Calendar — somente leitura (MCP agenda_*) |
| `betterme status` | status do agente e do Ollama |
| `betterme run` | executa uma tarefa única |
| `betterme boot` | 🔘 iniciar com o sistema — Windows | macOS |  |
| `betterme daemon` | roda o daemon em primeiro plano |
| `betterme server` | sobe a GUI web de controle |
| `betterme agent` | controla o agente (ligar/desligar) |
| `betterme ollama` | controla o servidor Ollama |
| `betterme tasks` | lista tarefas da fila e resultados |
| `betterme schedule` | tarefas agendadas (⏰) |
| `betterme config` | configuração |
| `betterme models` | lista modelos locais do Ollama |
| `betterme auto` | ✨ auto-atribui o melhor modelo instalado  |

Subcomandos: `betterme skills audit` (auditar o catálogo), `betterme config set/get`, `betterme server --host/--port/--token`.


## 3. Modificações — o que foi feito (v1.0.0 → v6.2.0)

40 releases. Tabela extraída do CHANGELOG (a versão detalhada de cada
uma está lá):

| Versão | Marca |
|---|---|

| **v6.2.0** | ⚡ PERFORMANCE + BOOTSTRAP COMPLETO (3º achado de campo) |
| **v6.1.0** | 🧩 DISPOSITIVO UNIVERSAL (Windows | macOS | Linux, x86-64 e ARM64) |
| **v6.0.2** | 🔧 INSTALAÇÃO EDITÁVEL ROBUSTA (correção de teste real #2) |
| **v6.0.1** | 🧷 AUTOCURA DOS COMANDOS `betterme` (correção de teste real) |
| **v6.0.0** | 🖥️ MULTIPLATAFORMA: Windows | macOS | Linux (PR #12) |
| **v5.1.0** | ⚙️ FLUXOS N8N LOCAIS (PR #11) |
| **v5.0.0** | 🌅 MODO VIDA (PR #10) |
| **v4.6.0** | 🎙️ MULTIMODAL LOCAL (PR #9, E5) |
| **v4.5.0** | 🔍 REVISÃO DE DIFF (PR #8, E4) |
| **v4.4.0** | 🗺️ GRAFO DE CÓDIGO (PR #7, E3) |
| **v4.3.0** | 🏟️ ARENA DE PROVEDORES (PR #6) |
| **v4.2.0** | 📱 GATEWAY DE MENSAGENS: Telegram + WhatsApp (PR #5) |
| **v4.1.0** | 🏷️ BETTERME: o agente muda de nome (PR #4 do roadmap) |
| **v4.1.0** | 🏷️ BETTERME: o agente muda de nome (PR #4 do roadmap) |
| **v4.0.0** | 🚀 A ENTRADA NO MODELO COMPLETO DE AGENTES DE IA |
| **v4.0.0** | 🚀 A ENTRADA NO MODELO COMPLETO DE AGENTES DE IA |
| **v3.17.1** | 🩹 hotfix: provedor externo nunca atendia (modelo errado no payload) |
| **v3.17.0** | 🔌 provedores LLM externos GRATUITOS, com privacidade dura |
| **v3.16.1** | 🧠 memória gerenciável: list/clear + pacote do operador v2 por tópicos |
| **v3.16.0** | 🚀 MODO MISSÃO: autonomia com subtasks encadeadas |
| **v3.15.1** | 📁 contrato do projeto: o agente sempre pede (ou recebe) o caminho |
| **v3.15.0** | 🚀 assistente completo, independente e sem perda de contexto |
| **v3.14.2** | 🗺 Mapa da aplicação + auditoria profunda (12 correções) |
| **v3.14.1** | 🎭✦ Claude sênior com skills e goal (fim do "não sou especialista") |
| **v3.14.0** | 🧪 passada de QA sênior: análise estática + QA do QA + matriz de todos os modelos |
| **v3.13.3** | 🔬 código só entrega executado + `hermes selftest` (LLM real) |
| **v3.13.2** | 🔎 diagnóstico do dispositivo em UMA chamada |
| **v3.13.1** | 🩹🔓 dois bugs reais do campo (recusa vazia + home bloqueada) |
| **v3.13.0** | ⚡💪 autonomia barata: cache de planos + skills do dia a dia |
| **v3.12.0** | 🧠 transferência de memória + 4 skills do agente sênior |
| **v3.11.5** | ⚡🧽 fim da lentidão e das respostas sujas (regressão da v3.11.3) |
| **v3.11.4** | 🛡 auto-assign respeita o hardware (teto max_model_b) |
| **v3.11.3** | ✨ auto-atribuição dos melhores modelos por papel |
| **v3.11.2** | 🩹 GUI volta a funcionar no navegador (SyntaxError da v3.9) |
| **v3.11.1** | 🚨 banner "server OFFLINE" (fim do fantasma do cache) |
| **v3.11.0** | 🔁🛡 estado sobrevive a restart + auditoria de skills |
| **v3.10.1** | 🧪 aceitação: melhoria prometida × melhoria medida |
| **v3.10.0** | 🧠⬇📊 o orquestrador aprende + update em 1 comando + painel de saúde |
| **v3.9.0** | 🧠 aba Ollama: todos os modelos instalados + papel de cada um |
| **v3.8.0** | ✦ catálogo de 18 skills curadas · 🔍 4º papel de modelo · 🧪 bateria E2E/integração/performance/estresse |
| **v3.7.0** | 🎭 modelos por papel (sem paralelismo) · 🗨 respostas entendíveis · 🧰 Ferramentas reconstruídas |
| **v3.6.0** | 🛠 lições da primeira bateria real do operador (5 correções de comportamento) |
| **v3.5.0** | 🧠 mente sênior no orquestrador/revisor · 🛡 fim do bug "não recebo a resposta" |
| **v3.4.0** | ⌨️ comandos /na GUI · 🔬 por baixo dos panos · ✦ skills no pipeline · 🔒 aprovação de criação |
| **v3.3.0** | 🎯 Orquestrador + ⚡ Executor + 🔍 Revisor (pipeline de tasks) |
| **v3.2.0** | 📱 GUI responsiva (celular/tablet) + instalável como app (PWA) |
| **v3.1.3** | 🔎 E-mail somente leitura por padrão · 🗓 Agenda Google · 🌀 guard anti-loop |
| **v3.1.2** | 📧 e-mail com 2FA/OAuth (XOAUTH2 + device code) |
| **v3.1.1** | 📡 Log ao vivo mostra TODA a atividade (bug real) |
| **v3.1.0** | 📧 MCP de e-mail (leitura + envio, credenciais à prova de vazamento) |
| **v3.0.2** | guard de execução (fim do "escreve o comando e não roda") |
| **v3.0.1** | revisão crítica (segurança + correções) |
| **v3.0.0** | a grande atualização (confiança · poder · inteligência) |
| **v2.2.8** | Claude Code autodiagnóstico + fallback de CLI antiga |
| **v2.2.7** | guard anti-loop no agente |
| **v2.2.6** | Claude Code em modo leve (fim do "fora de si") |
| **v2.2.5** | fim do "JSON solto" (modelos pequenos) |
| **v2.2.4** | prompt enxuto + indicador de modo real |
| **v2.2.3** | diagnóstico de velocidade na GUI |
| **v2.2.2** | Claude Code: fallback de modelo local |
| **v2.2.1** | respostas mais rápidas (keep_alive + num_predict) |
| **v2.2.0** | ditado por voz (🎤 Whisper local) |
| **v2.1.0** | acesso à web (🌐 pesquisa e leitura de páginas) |
| **v2.0.2** | catálogo com curadoria "leves ≤7B" (máquinas com ~10 GB de RAM) |
| **v2.0.1** | Claude Code integrado ao Ollama por padrão |
| **v2.0.0** | ferramentas manuais, Claude Code, catálogo de LMMs e conversas completas |
| **v1.5.0** | execução ao vivo + memória persistente |
| **v1.4.0** | tarefas agendadas (⏰) |
| **v1.3.1** | tempo de geração da resposta |
| **v1.3.0** | memória de conversas (histórico + zerar + restauração) |
| **v1.2.0** | espera robusta + "A trabalhar…" |
| **v1.1.1** | blindagem PyYAML |
| **v1.1.0** | "Visão completa" (a versão da demo online) |
| **v1.0.0** | versão inicial |

**A linha evolutiva em 4 atos:**
- **v1.x — fundação**: chat com Ollama, memória de conversas, tarefas
  agendadas, execução ao vivo, memória persistente;
- **v2.x — poder**: ferramentas manuais, Claude Code, catálogo de LMMs
  leves, acesso à web, ditado por voz (Whisper), robustez p/ modelos
  pequenos (anti-loop, JSON solto, modo leve);
- **v3.0–v3.2 — plataforma**: GUI web de controle completa (OAuth
  e-mail/agenda, auditoria, métricas, backups, scheduler, supervisor,
  anti-CSRF), daemon/receitas, MCP de e-mail, PWA offline;
- **v3.3–v3.11 — inteligência com controle**: pipeline 🎯⚡🔍 (v3.3),
  comandos na GUI + skills + aprovação de criação (v3.4), mente sênior +
  garantidor do done (v3.5), lições da bateria real (v3.6), modelos por
  papel sem paralelismo (v3.7), 18 skills + bateria E2E (v3.8), aba
  Ollama com papéis (v3.9), memória de experiência + update + painel de
  saúde com testes de aceitação (v3.10), estado persistente + auditoria
  de skills + banner offline (v3.11).

## 4. Modificações em andamento (como o projeto evolui)

**Processo permanente:** cada mudança vira release versionada (tag no
GitHub + zip), a suíte `tests/run_all.py` cresce junto (88 casos hoje:
unitários, E2E, integração, performance e estresse), o repositório
público não contém dado pessoal, e `git grep` anti-segredo roda antes
de todo push.

**Backlog priorizado (decidido com o operador):**
1. harness de testes contra Ollama REAL (opcional, roda verde só onde
   há Ollama instalado);
2. tasks encadeadas (multi-step) — a decisão será justificada pelos
   dados do painel de saúde em uso real;
3. Claude Code dentro do pipeline (hoje atua como 2º agente à parte);
4. HTTPS/túnel para acesso externo — reabrir quando virar necessidade
   concreta;
5. curadoria incremental de skills até ~100 (qualidade > quantidade;
   cada nova skill passa pela auditoria).


## 5. Arquitetura e arquivos de dados

```
navegador ─ GUI (index.html, vanilla JS)
   │  HTTP/SSE
   ▼
betterme server (Flask/waitress, porta 8080) ── CLI `betterme …`
   │                          │
   ▼                          ▼
🎯 orchestrator ────────── ⚡ agent.py ──🔧 tools (shell/web/arquivos)
   │ skills ✦                    │
   ▼                              ▼
🔍 revisão ──► entrega      Ollama (localhost:11434) · Claude Code
   │
   ▼  registro/aprendizado
~/.betterme/ (dados — tabela abaixo)
```

**Arquivos em `~/.betterme/` (data_dir):**

| Caminho | O que guarda |
|---|---|

| `config.yaml` | ⚙️ configuração do operador (modelos por papel, toggles, host/port) |
| `conversations/` | 🗂 conversas completas, por sessão |
| `orchestrator_tasks.jsonl` | 🎯 REGISTRO de cada task do pipeline — status, tentativas, duração, veredito, edições do operador (v3.3+; campos de experiência v3.10). Fonte do painel de saúde e da memória de experiência |
| `session_goals.json` | 🎯 goals de sessão (/goal) — sobrevivem a restart (v3.11) |
| `pending_approvals.json` | 🔒/📦 aprovações pendentes — sobrevivem a restart (v3.11) |
| `ollama_models_cache.json` | 🧠 últimos modelos vistos — aba Ollama funciona com servidor desligado (v3.9) |
| `memory.json` | 🧠 memória de longo prazo (fatos via `lembrar`) |
| `metrics.jsonl` | 📊 métricas de uso |
| `notifications.json` | 🔔 notificações |
| `heartbeat.json` | 💓 batimento do daemon |
| `ollama.pid` | 📍 PID do Ollama gerenciado |
| `schedules/` | ⏰ tarefas agendadas |
| `tasks/` | 🔄 fila e resultados do daemon |
| `audit/` | 🧾 auditoria de ações |
| `logs/` | 📜 logs (Log ao vivo da GUI) |
| `backups/` | 💾 backups automáticos |
| `secrets/` | 🔑 credenciais — chmod 600, NUNCA no repo nem no modelo |
| `skills/` | ✦ skills do usuário (além das 18 embutidas) |
| `workspace/` | 🧰 área de trabalho do agente |

## 6. Referência de funções (gerada do código-fonte)

### betterme/orchestrator.py — 🎯 o coração do pipeline: planeja (lendo a conversa, a experiência e o goal), aplica skills, submete aos portões de aprovação, executa, revisa, registra cada task e aprende com as edições do operador

| Função | O que faz |
|---|---|
| `tasks_path(cfg)` | — |
| `model_for(cfg, role)` | Modelo de um PAPEL (orquestrador/executor). Vazio = cfg.model. Um modelo por vez: o pipeline é SEQUENCIAL — o Ollama ca… |
| `_fast(cfg, system, user, ntok, stage, model)` | Chamada rápida e curta ao modelo (orquestrador/revisor). Nunca lança; em modo mock devolve '' (o chamador cai na heurís… |
| `_extract_json(text)` | Primeiro objeto JSON balanceado do texto (modelos pequenos cercam o JSON de prosa) — None se não achar nada válido. |
| `_extra_criterios(message)` | Critérios estruturais por CLASSE de tarefa (v3.13.3): código só entrega com saída de execução real colada na resposta. |
| `_heuristic(message)` | — |
| `_plan_key(cfg, message)` | — |
| `_cache_invalidate(cfg)` | — |
| `plan(cfg, message, history)` | 🎯 Orquestrador: decide a rota e monta o plano. Nunca lança — qualquer falha cai na heurística (o chat nunca quebra). |
| `review(cfg, objetivo, criterios, resultado)` | 🔍 Revisor: o resultado cumpre o objetivo? Nunca lança — falha de parse devolve 'ok' (entrega sem travar o chat). |
| `record(cfg, entry, tid)` | Anexa o registro da task (auditoria leve, sem banco). |
| `experience(cfg, limit)` | v3.10 🧠: o orquestrador APRENDE — as últimas tasks (resultados, reprovações e EDIÇÕES do operador) viram contexto do pl… |
| `_next_id(cfg)` | — |
| `list_tasks(cfg, limit)` | — |
| `_goals_path(cfg)` | — |
| `_detectar_projetos(message)` | Referências de pasta no pedido (absolutas ou ~/...), em ordem. Ignora URLs (nada precede a barra), frações/datas (24/09… |
| `_ambiente_txt(projeto)` | v3.15.0 (PR#1): ambiente do projeto injetado no executor — o padrão do Claude Code (cwd, data, SO, git, memória do proj… |
| `load_goals(cfg)` | v3.11: goals de sessão voltam do disco ao subir o servidor. |
| `set_goal(session_id, texto, cfg)` | — |
| `get_goal(session_id, cfg)` | — |
| `skills_for(cfg, text, max_skills)` | Skills ATIVAS relevantes ao texto (por palavras-chave da descrição). Devolve [{name, path, score}] — no máximo 2, score… |
| `_skill_criterios(skills)` | v3.15.0 (PR#3): DELEGAÇÃO — a seção '## Verificação' da skill que casou vira critérios que o 🔍 revisor vai cobrar na en… |
| `_skill_conteudo(cfg, skills)` | Conteúdo das SKILLs selecionadas (para injetar no executor). |
| `_pending_path(cfg)` | — |
| `_pending_save(cfg, dados)` | — |
| `_pending_load(cfg)` | — |
| `list_pending(cfg)` | v3.11: pendências que sobreviveram a um restart (🔒/📦). |
| `peek_pending(cfg, tid)` | — |
| `pop_pending(cfg, tid)` | — |
| `request_approval(tid, timeout, check, cfg, meta)` | Bloqueia até o operador decidir (ou esgotar o tempo). Devolve (ação, edição): aprovar\|editar\|cancelar\|refazer\|entregar … |
| `approve(tid, action, edit)` | Registra a decisão do operador (chamado pelo endpoint da GUI). |
| `_pergunta_caminho(message, goal, session_id)` | — |
| `_pedir_caminho(ev, message, goal, session_id)` | Emite os eventos e devolve a pergunta (uso nos 2 caminhos de rota). |
| `_quer_projeto_sem_caminho(cfg, message, resume_plan)` | v3.15.1: task de código/projeto para INICIAR, sem pasta no pedido. |
| `run_pipeline(agent, cfg, message, history, on_event, cancel, max_tentativas, goal, session_id, resume_plan, resume_tid, extra_criterios, resultado_meta)` | Conversa → 🎯 plano → [🔒 aprovação p/ criação] → ⚡ execução → 🔍 revisão → [🔒 entrega editável p/ criação] → done. Emite … |

### betterme/agent.py — 💬 o executor: conversa com o Ollama com streaming de tokens e uso das ferramentas

**classe `Agent`** — —

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_score_tool` | Similaridade barata (overlap de palavras) entre pergunta e ferramenta. |
| `_select_mcp_tools` | v3.0: com muitas ferramentas MCP, injeta só as relevantes à pergunta … |
| `_prompt_key` | Chave de invalidação do cache: muda só quando algo relevante muda. |
| `system_prompt` | — |
| `_resumir` | Resumo curto do meio da conversa — LLM se der, senão corte determinís… |
| `_compactar` | v3.15.0 (PR#3): compactação de contexto (padrão Claude Code). Perto d… |
| `run` | Executa uma tarefa/conversa. `messages` sem o prompt de sistema. allo… |

| Função | O que faz |
|---|---|
| `_now_line()` | Data/hora fresca — entra NO FINAL do prompt, fora do cache, para o prefixo (parte cacheada) ficar estável entre mensage… |
| `_json_blocks(text)` | Extrai blocos ```json ...``` (ou json solto) do texto do modelo. |
| `_bare_tool_call(text)` | Detecta chamada de ferramenta em JSON SEM cercas de código. Modelos pequenos às vezes respondem com o JSON cru (com ou … |
| `_as_tool_calls(block)` | Normaliza {"tool":..,"args":..} / {"name":..,"arguments":..} para o formato da API. |

### betterme/server/app.py — 🌐 a API REST + GUI web (Flask/waitress): todos os endpoints, streaming do chat, aprovações, painel e páginas

**84 endpoints HTTP:**

| Método e rota | O que faz |
|---|---|
| `GET /` | index |
| `GET /fluxos` | fluxos_page |
| `GET /api/fluxos/status` | fluxos_status |
| `GET /manifest.webmanifest` | manifest |
| `GET /sw.js` | service_worker |
| `GET /icon-<int:size>.png` | pwa_icon |
| `GET /api/orchestrator/tasks` | orchestrator_tasks |
| `GET /api/orchestrator/stats` | Funil do pipeline a partir das tasks registradas: aprovação na 1ª tentativa, refações, edições do operador, skills mais… |
| `POST /api/chat/command` | Comandos slash do chat da GUI (mesmos do terminal, e /goal). |
| `GET /api/approvals/pending` | v3.11: pendências que sobreviveram a restart + retomadas. |
| `POST /api/chat/approve` | Decisão do operador num portão de aprovação (✅/✏️/⛔). |
| `GET /api/status` | status |
| `POST /api/agent/<action>` | agent_action |
| `POST /api/ollama/<action>` | ollama_action |
| `GET /api/ollama/diagnose` | ollama_diagnose |
| `POST /api/ollama/test` | Validação completa da conexão, incluindo geração de teste real. |
| `POST /api/ollama/auto-assign` | v3.11.3 ✨: escolhe e salva o melhor modelo instalado para cada papel (chat/orquestrador/revisor/executor/claude). |
| `GET /api/ollama/models` | TODOS os modelos instalados + qual papel cada um exerce. v3.9: com o servidor desligado, devolve a ÚLTIMA lista conheci… |
| `POST /api/ollama/pull` | Baixa um modelo streamando o progresso (NDJSON). |
| `POST /api/ollama/delete` | ollama_delete |
| `POST /api/ollama/restart` | ollama_restart |
| `POST /api/ollama/boot` | Liga/desliga a inicialização do Ollama junto do sistema. |
| `GET /api/mcp` | mcp_status |
| `POST /api/mcp/start` | mcp_start |
| `POST /api/mcp/restart` | mcp_restart |
| `GET /api/skills` | skills_list |
| `GET /api/skills/content` | skills_content |
| `GET /api/especialistas` | especialistas_state |
| `GET /api/autonomia` | autonomia_get |
| `POST /api/autonomia` | autonomia_set |
| `GET /api/aprendizados` | aprendidos_get |
| `POST /api/aprendidos` | aprendidos_post |
| `GET /api/gerente` | gerente_get |
| `POST /api/gerente` | gerente_post |
| `POST /api/skills/toggle` | skills_toggle |
| `POST /api/skills/install` | skills_install |
| `GET /api/logs` | logs |
| `POST /api/logs/clear` | logs_clear |
| `GET /api/logs/stream` | logs_stream |
| `POST /api/chat` | chat |
| `GET /api/tools` | Catálogo das funções padrão do agente (ferramentas nativas + MCP). |
| `POST /api/tools/run` | Terminal rápido — mesma segurança do agente (denylist + timeout). |
| `POST /api/tools/list_dir` | tools_list_dir |
| `POST /api/tools/read_file` | tools_read_file |
| `POST /api/tools/write_file` | tools_write_file |
| `POST /api/tools/sys_info` | tools_sys_info |
| `POST /api/tools/web_search` | tools_web_search |
| `POST /api/tools/web_fetch` | tools_web_fetch |
| `GET /api/stt/status` | stt_status |
| `POST /api/stt` | stt_transcribe |
| `GET /api/ollama/library` | Busca modelos: curadoria popular + biblioteca oficial (ollama.com). |
| `POST /api/ollama/pull/cancel` | ollama_pull_cancel |
| `GET /api/conversations` | conversations_list |
| `GET /api/conversations/<sid>` | conversations_get |
| `GET /api/conversations/search` | conversations_search |
| `POST /api/conversations/delete` | conversations_delete |
| `POST /api/conversations/current` | conversations_current |
| `GET /api/tasks` | tasks_get |
| `POST /api/tasks` | tasks_post |
| `POST /api/tasks/clear` | tasks_clear |
| `GET /api/schedules` | schedules_list |
| `POST /api/schedules` | schedules_create |
| `POST /api/schedules/toggle` | schedules_toggle |
| `POST /api/schedules/delete` | schedules_delete |
| `POST /api/schedules/run` | schedules_run |
| `GET /api/schedules/live` | schedules_live |
| `GET /api/memory` | memory_list |
| `POST /api/memory` | memory_add |
| `POST /api/memory/update` | memory_update |
| `POST /api/memory/delete` | memory_delete |
| `GET /api/settings` | settings_get |
| `POST /api/settings` | settings_post |
| `GET /api/audit` | audit_query |
| `GET /api/backups` | backups_list |
| `POST /api/backups/restore` | backups_restore |
| `GET /api/metrics` | metrics_view |
| `GET /api/notifications` | notifications_list |
| `POST /api/notifications/read` | notifications_read |
| `GET /api/recipes` | recipes_list |
| `GET /api/doctor` | doctor_check |
| `POST /api/hooks/<sid>` | hook_run |
| `GET /api/conversations/<sid>/export` | conversation_export |
| `POST /api/mcp/add` | mcp_add |
| `POST /api/mcp/test` | mcp_test |

### app.py — helpers — 🌐 a API REST + GUI web (Flask/waitress): todos os endpoints, streaming do chat, aprovações, painel e páginas

| Função | O que faz |
|---|---|
| `create_app(cfg)` | — |
| `serve(cfg, host, port)` | — |

### betterme/cli.py — ⌨️ todos os comandos `betterme` do terminal

| Função | O que faz |
|---|---|
| `_cfg(args)` | — |
| `_p(text)` | — |
| `_ok(msg)` | — |
| `_fail(msg)` | — |
| `cmd_status(args)` | — |
| `cmd_agent(args)` | — |
| `cmd_email(args)` | Configura contas de e-mail para o servidor MCP (credenciais locais). |
| `cmd_agenda(args)` | Agenda Google Calendar — somente leitura (MCP agenda_*). |
| `cmd_doctor(args)` | Diagnóstico completo: config -> Ollama (com geração real) -> agente. |
| `cmd_ollama(args)` | — |
| `cmd_run(args)` | — |
| `cmd_chat(args)` | — |
| `cmd_update(args)` | Atualiza o projeto a partir do GitHub (tags oficiais do repo). |
| `cmd_memory_import(args)` | v3.12: importa fatos para a memória do agente (JSON lista de strings, ou texto com um fato por linha). Duplicados são p… |
| `cmd_rag(args)` | v3.15.0 (PR#2): biblioteca local (RAG) — indexar e consultar. |
| `cmd_skills_import(args)` | v3.15.0 (PR#3): importa skills de pasta local, .zip, URL ou owner/repo. |
| `cmd_skills_scan(args)` | v3.15.0 (PR#3): varre as pastas assistidas e importa skills novas. |
| `cmd_selftest(args)` | v3.13.3: bateria de aceitação com LLM REAL (pula sem Ollama). |
| `cmd_skills_audit(args)` | v3.11: audita o catálogo de skills (estrutura, tamanho, injeção). |
| `cmd_daemon(args)` | — |
| `cmd_boot(args)` | v6.0.0: iniciar com o sistema (Windows \| macOS \| Linux). |
| `cmd_server(args)` | — |
| `cmd_schedule(args)` | — |
| `cmd_tasks(args)` | — |
| `cmd_config(args)` | — |
| `cmd_provider(args)` | v3.17.0: provedores LLM externos GRATUITOS (memória nunca sai). |
| `cmd_varredura(args)` | v4.0.0: varre segredos/dados pessoais — 1 se houver crítico. |
| `cmd_init(args)` | v4.0.0: cria HERMES.md de partida no projeto. |
| `cmd_autonomia(args)` | v4.0.0: vê/muda o nível de autonomia (cauteloso\|padrao\|autonomo). |
| `cmd_gerente(args)` | v4.0.0 (M7, D5): gerente de código (Claude) — opt-in consciente. |
| `cmd_telegram(args)` | v4.2.0 (PR#5): canal Telegram (token em secrets, allowlist). |
| `cmd_whatsapp(args)` | v4.2.0 (PR#5): canal WhatsApp via Playwright (local, removível). |
| `cmd_arena(args)` | v4.3.0 (PR#6): arena — mesma task nos provedores grátis, ranking medido. |
| `cmd_grafo(args)` | v4.4.0 (PR#7): grafo de código (onde está a lógica de X?). |
| `cmd_revisar(args)` | v4.5.0 (PR#8): revisão de diff — gate único pré-push. |
| `cmd_multimodal(args)` | v4.6.0 (PR#9): transcrição local de áudio/vídeo (→ RAG). |
| `cmd_vida(args)` | v5.0.0 (PR#10): Modo Vida — relatório diário + curadoria. |
| `cmd_fluxos(args)` | v5.1.0 (PR#11): fluxos n8n locais (setup/start/stop/remover). |
| `cmd_aprendidos(args)` | v4.0.0 (M6.5): rascunhos de aprendizado (aprovação do operador). |
| `cmd_skills_aprender(args)` | v4.0.0 (M6.5): transforma documento/texto/URL em rascunho de skill. |
| `cmd_conversas_buscar(args)` | v4.0.0 (M6.5): busca textual nas conversas passadas. |
| `cmd_memory_list(args)` | v3.16.1: lista os fatos da memória do agente. |
| `cmd_memory_clear(args)` | v3.16.1: apaga TODOS os fatos da memória (para reimportar um pacote organizado sem duplicatas). Pede confirmação, salvo… |
| `cmd_models(args)` | — |
| `cmd_models_auto(args)` | v3.11.3: escolhe o melhor modelo instalado para cada papel. |
| `build_parser()` | — |
| `main(argv)` | — |

### betterme/tools.py — 🔧 ferramentas do agente: shell, arquivos, web, lembrar… (com denylist de segurança)

**classe `ToolError`** — —

| Função | O que faz |
|---|---|
| `is_dangerous(command)` | — |
| `touches_secrets(command)` | — |
| `_truncate(text, limit)` | — |
| `validar_escopo_projeto(path, cfg)` | Valida (sem criar) a pasta de projeto declarada pelo operador. |
| `task_scope(path, cfg)` | Ativa a pasta do projeto para ESTA task: percorre/cria o caminho, vira o cwd dos comandos e libera leitura+escrita DENT… |
| `scope_dir()` | Pasta do projeto ativa nesta thread (None = workspace padrão). |
| `resolve_path(path, cfg, write)` | Resolve caminho com as regras de sandbox. write=True (write_file): sempre restrito ao workspace + skills. write=False (… |
| `run_command(args, cfg)` | — |
| `read_file(args, cfg)` | — |
| `write_file(args, cfg)` | — |
| `list_dir(args, cfg)` | — |
| `_read_proc(path)` | — |
| `_human_size(n)` | — |
| `_human_uptime(seconds)` | — |
| `diagnostico_sistema(_args, cfg)` | v3.13.2: o diagnóstico inteiro NUMA chamada só. Devolve digesto real e compacto — o executor interpreta, não flailha em… |
| `sys_info(_args, cfg)` | — |
| `_web_enabled(cfg)` | — |
| `_ddg_decode(url)` | O DuckDuckGo devolve links-rediretor .../l/?uddg=<url real>. |
| `_html_to_text(page)` | — |
| `web_search(args, cfg)` | — |
| `web_fetch(args, cfg)` | — |
| `lembrar(args, cfg)` | — |
| `esquecer(args, cfg)` | — |
| `_backups_tool(args, cfg)` | — |
| `git_run(args, cfg)` | v3.15.0 (PR#2): git com subcomandos permitidos, no projeto da task. |
| `gerente_codigo_tool(args, cfg)` | v4.0.0 (M7, D5): delega uma task de CÓDIGO ao gerente Claude (só se o operador ativou com `betterme gerente on --yes`). |
| `conversas_buscar(args, cfg)` | v4.0.0 (M6.5): busca nas conversas passadas (decisões antigas). |
| `especialista_tool(args, cfg)` | v4.0.0 (M6): o cérebro invoca um especialista (revisor, debugger, pesquisador, seguranca) para um caso pontual — veredi… |
| `knowledge_search(args, cfg)` | v3.15.0 (PR#2): RAG local — trechos verbatim com fonte. |
| `fluxos_chamar(args, cfg)` | v5.1.0 (PR#11): dispara workflow n8n local por webhook. |
| `revisar_diff(args, cfg)` | v4.5.0 (PR#8): revisão de diff — veredito com arquivo:linha. |
| `grafo_query(args, cfg)` | v4.4.0 (PR#7): grafo de código — onde está a lógica de X? (zero tokens). |
| `execute_tool(name, arguments, cfg, source, agent)` | Executa uma ferramenta e devolve {'ok': bool, 'output': str}. v3.0: toda execução vai para a trilha de auditoria (data/… |
| `tool_summary()` | — |

### betterme/skills.py — ✦ carregador de skills: frontmatter, gatilhos, ativação e instalação

**classe `SkillLoader`** — —

| Método | O que faz |
|---|---|
| `__init__` | — |
| `dirs` | — |
| `user_dir` | — |
| `scan` | — |
| `enabled` | — |
| `catalog` | — |
| `read_skill_md` | Lê um SKILL.md validando que está dentro dos diretórios de skills. |
| `toggle` | — |
| `install_from_github` | Baixa skills de um repositório GitHub (tarball do codeload). Aceita '… |
| `_extract_skills` | — |

| Função | O que faz |
|---|---|
| `_slug(nome, fallback)` | — |
| `find_skill_dirs(root, depth)` | Pastas com SKILL.md válido (name+description) sob `root`. |
| `import_skill_dir(src_dir, cfg)` | Copia UMA pasta de skill para ~/.betterme/skills/<nome>. |
| `_importar_todas(dirs, cfg)` | — |
| `import_from(src, cfg)` | Importa skills de QUALQUER fonte: pasta local, arquivo .zip, URL git/GitHub ou owner/repo (delega no install_from_githu… |
| `autoscan(cfg)` | Varre as pastas assistidas (default ~/Downloads) e importa skills novas — o 'baixei do GitHub, agora é nativa' sem coma… |
| `parse_skill_md(text)` | Separa frontmatter YAML do corpo Markdown. |

### betterme/skills_audit.py — 🛡 auditoria do catálogo: estrutura, tamanho, prompt injection, duplicatas

| Função | O que faz |
|---|---|
| `_frontmatter(texto)` | Separa frontmatter simples (chave: valor) do corpo Markdown. |
| `audit_skill(pasta)` | Audita uma pasta de skill → {name, nivel, problemas[]}. |
| `audit_skills(dirs)` | Audita todos os diretórios de skills + duplicatas de nome. |
| `run_audit(cfg, print_fn)` | Roda a auditoria no catálogo configurado; devolve exit code. |

### betterme/update.py — ⬇ autoatualização: consulta tags no GitHub, baixa o zip e aplica preservando data/.venv/.git

| Função | O que faz |
|---|---|
| `_parse_version(tag)` | 'v3.10.0' → (3,10,0); tags com sufixo (-beta, -rc) ficam (0,). |
| `latest_tag(fetch)` | Última tag do repositório (None se não conseguir consultar). `fetch(url) -> str` injetável para testes offline. |
| `_project_root()` | Raiz da instalação (pasta que contém betterme/ e pyproject.toml). |
| `_assert_zip_seguro(zf, dest_dir)` | v3.14.2: defesa zip-slip — nenhum membro do zip pode escapar do diretório de destino (caminho absoluto ou com '..' é re… |
| `download(tag, dest_dir)` | Baixa e extrai o zip da tag; devolve a raiz extraída. |
| `apply_update(src_root, dest_root, log)` | Copia a nova versão sobre a instalação — preserva data/, .venv e .git. Devolve a lista de itens atualizados. |
| `_venv_python(root)` | Python do venv DO PROJETO (bin/ no Unix, Scripts/ no Windows). |
| `garantir_entry_points(root, log)` | v6.0.1: autocura dos COMANDOS `betterme` (+ alias `hermes`). Entry points são gerados NA INSTALAÇÃO (pip); o update tro… |
| `run(check_only, assume_yes, print_fn)` | Executa o update; devolve código de saída (0 = ok/atualizado). |

### betterme/config.py — ⚙️ Config: defaults, leitura/escrita do config.yaml, skills_dirs, chaves tipadas

**classe `Config`** — Acesso por atributos: cfg.model, cfg.max_steps, ...

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_migrar_legado` | — |
| `_load_file` | — |
| `save` | — |
| `update` | — |
| `as_dict` | — |
| `ensure_dirs` | — |
| `workdir` | — |
| `logfile` | — |
| `heartbeat_path` | — |
| `spool_dir` | — |
| `done_dir` | — |
| `conversations_dir` | — |
| `ollama_pidfile` | — |
| `skills_dirs` | Diretórios de skills: embutidas do projeto + do usuário. |

| Função | O que faz |
|---|---|
| `_env_flag(name)` | — |
| `_coerce(key, value)` | — |

### betterme/memory.py — 🧠 memória de longo prazo (fatos guardados com `lembrar`)

**classe `MemoryStore`** — —

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_read` | — |
| `_write` | — |
| `list_all` | Fatos ordenados do mais recente para o mais antigo. |
| `import_facts` | v3.12: importa fatos (ex.: transferência de contexto de outro agente)… |
| `add` | — |
| `update` | — |
| `delete` | — |
| `_score` | Similaridade barata pergunta↔fato (overlap de palavras). |
| `relevant` | Top-k fatos por relevância à pergunta (mais os 2 mais recentes). |
| `prompt_section` | Seção pronta para o prompt de sistema ('' se não houver fatos). v3.0:… |


### betterme/conversations.py — 🗂 conversas: sessões, histórico, títulos

**classe `ConversationStore`** — —

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_path` | — |
| `_ensure_dir` | — |
| `new_session` | — |
| `save` | — |
| `load` | — |
| `append` | Adiciona uma mensagem à sessão (cria o arquivo se preciso). |
| `list` | — |
| `search` | Busca texto dentro de TODAS as conversas (mín. 2 caracteres). |
| `delete` | — |
| `set_current` | — |
| `get_current` | — |


### betterme/scheduler.py — ⏰ agendador de tarefas periódicas/pontuais

**classe `ScheduleStore`** — —

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_path` | — |
| `_ensure` | — |
| `create` | — |
| `save` | — |
| `load` | — |
| `list_all` | — |
| `public_list` | — |
| `delete` | — |

**classe `Scheduler`** — Loop que dispara as tarefas agendadas (roda dentro do `betterme server`).

| Método | O que faz |
|---|---|
| `__init__` | — |
| `start` | — |
| `stop` | — |
| `_loop` | — |
| `tick` | — |
| `_watch_new_files` | Arquivos novos que casam com o padrão desde a última verificação. |
| `_execute` | — |
| `run_now` | — |

| Função | O que faz |
|---|---|
| `_norm(text)` | — |
| `parse_schedule(text)` | Converte texto em português num spec de agendamento. |
| `human_schedule(spec)` | — |
| `_parse_hm(value)` | — |
| `next_run(entry, now)` | Próxima disparada da tarefa (None se não houver). |
| `is_due(entry, now)` | A tarefa deve disparar AGORA? (next_run é só para exibição.) |
| `execute_entry(cfg, entry, on_event)` | Roda a tarefa agendada de forma desassistida e devolve o resultado. on_event (opcional) recebe os mesmos eventos do cha… |
| `_live_begin(sid, input_text)` | — |
| `_live_push(sid, event)` | — |
| `_live_end(sid, result)` | — |
| `live_status(sid)` | Snapshot do console ao vivo da tarefa (None se nunca rodou neste server). |
| `_system_busy(threshold)` | True se a máquina estiver ocupada (para tarefas 'only_idle'). v3.0.1: o load é comparado RELATIVO ao número de núcleos … |

### betterme/daemon.py — 🔄 daemon: fila de tarefas em segundo plano

| Função | O que faz |
|---|---|
| `log(message)` | — |
| `_write_heartbeat(cfg, status, task, started_at)` | — |
| `enqueue(cfg, text)` | Cria um arquivo de tarefa na fila e devolve o registro. |
| `list_tasks(cfg)` | — |
| `run_daemon(cfg)` | — |

### betterme/manager.py — 🖥 liga/desliga Ollama e daemon, boot systemd, diagnóstico

**classe `DaemonManager`** — Controla o processo do agente (o 'coração' que executa tarefas).

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_heartbeat` | — |
| `status` | — |
| `start` | — |
| `stop` | — |
| `restart` | — |

**classe `OllamaManager`** — Detecta, liga, desliga e *monitora* o servidor Ollama. Fornece a visibilidade que o app desktop do …

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_systemd` | True se existe unidade systemd 'ollama' neste host. |
| `_spawned_pid` | — |
| `_find_pid` | Localiza o PID do servidor Ollama (nosso, systemd ou pgrep). |
| `_proc_info` | PID, uptime e memória RSS do processo do Ollama (via /proc). |
| `_boot_enabled` | — |
| `status` | — |
| `start` | — |
| `stop` | — |
| `restart` | — |
| `set_boot` | Liga/desliga a inicialização do Ollama junto do sistema (systemd). |
| `diagnose` | Verifica a conexão com o Ollama passo a passo. Passos: instalação, se… |

| Função | O que faz |
|---|---|
| `_pid_alive(pid)` | v6.0.0: delega à camada de plataforma — sinais diretos são exclusivos do Unix (no Windows, kill(pid, 0) TERMINA o proce… |
| `_run(cmd, timeout)` | — |
| `python_env_check()` | Confere se as dependências Python estão íntegras. Detecta o caso do PyYAML 'quebrado': `import yaml` funciona mas o pac… |

### betterme/ollama_client.py — 📡 cliente HTTP do Ollama (chat, tags, ps)

**classe `OllamaError`** — Erro de comunicação/execução no Ollama.

**classe `OllamaClient`** — Cliente fino e sem dependências externas além do `requests`.

| Método | O que faz |
|---|---|
| `__init__` | — |
| `is_running` | — |
| `version` | — |
| `list_models` | — |
| `model_details` | Modelos instalados com tamanho e data (API /api/tags completa). |
| `ps` | Modelos carregados em memória/VRAM neste momento (API /api/ps). |
| `delete_model` | — |
| `test_generation` | Geração mínima para validar o caminho completo (mede a latência). |
| `chat_stream` | Gera chunks no formato da API /api/chat (stream=true). - `cancel` (th… |
| `pull` | Baixa um modelo via /api/pull reportando progresso (cancelável). |

**classe `MockOllamaClient`** — Simula o Ollama para demonstração da GUI e do loop do agente.

| Método | O que faz |
|---|---|
| `is_running` | — |
| `version` | — |
| `list_models` | — |
| `chat_stream` | — |
| `pull` | Download simulado com barra visível (e cancelável) na demo. |
| `_fake_message` | — |

| Função | O que faz |
|---|---|
| `get_client(cfg)` | Fábrica: devolve o cliente mock quando cfg.mock for verdadeiro. v3.17.0: com llm_provider externo configurado, devolve … |

### betterme/claude_agent.py — 🔌 agente Claude Code (2º cérebro, modo leve)

| Função | O que faz |
|---|---|
| `_claude_env(cfg)` | Ambiente do subprocesso `claude` — Ollama por padrão. Com claude_use_ollama=True (padrão), o Claude Code é apontado par… |
| `_extract_commands(text)` | Comandos dos blocos ```bash (sem comentários, até 4, ≤500 chars). |
| `_guard_execute(cfg, commands, ev)` | Último recurso: executa os comandos com as ferramentas do Betterme (denylist + timeout + auditoria) e devolve a saída R… |
| `_strip_loops(text)` | Corta runs de linhas idênticas consecutivas → (texto limpo, cortes). |
| `_cli_version(exe)` | Versão da CLI claude (cacheada; '?' se não conseguir ler). |
| `_claude_cmd(exe, cfg, prompt, light)` | Linha de comando do Claude Code (headless, stream JSON). MODO LEVE (Ollama): --bare — o payload enviado ao modelo cai d… |
| `claude_path()` | Caminho do binário `claude` (None se não estiver instalado). |
| `_enrich_prompt(cfg, message, goal)` | v3.14.1: o Claude Code ganha o CONTEXTO do Betterme — a skill que casa com o pedido (CONTEÚDO, não só o nome) e o objet… |
| `_build_prompt(message, history)` | Serializa a conversa anterior + a mensagem nova em um único prompt. |
| `_simulate(message, ev, cancel)` | Resposta simulada (modo demonstração) — mesmo formato de eventos. |
| `run_claude(cfg, message, history, on_event, cancel, goal)` | Executa o Claude Code e devolve a resposta final (texto). Emite os mesmos eventos do chat: step, note, token, tool_star… |
| `_run_impl(cfg, message, history, on_event, cancel, _light, _guard, goal)` | — |

### betterme/mcp_client.py — 🔌 cliente MCP: e-mail, agenda, Figma…

**classe `MCPError`** — —

**classe `BaseMCPServer`** — Handshake JSON-RPC 2.0: initialize -> tools/list -> tools/call.

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_rpc` | — |
| `_notify` | — |
| `start` | — |
| `stop` | — |
| `alive` | — |
| `list_tools` | — |
| `call_tool` | — |

**classe `StdioServer`** — Servidor MCP como processo local, JSON-RPC por linhas no stdin/stdout.

| Método | O que faz |
|---|---|
| `__init__` | — |
| `start` | — |
| `_read_stdout` | — |
| `_read_stderr` | — |
| `_rpc` | — |
| `_notify` | — |
| `alive` | — |
| `stop` | — |

**classe `HTTPServer`** — Servidor MCP via Streamable HTTP (POST JSON-RPC; resposta JSON ou SSE).

| Método | O que faz |
|---|---|
| `__init__` | — |
| `start` | — |
| `_post` | — |
| `_parse` | — |
| `_rpc` | — |
| `_notify` | — |
| `alive` | — |
| `stop` | — |

**classe `MCPManager`** — Gerencia todos os servidores MCP configurados (uma instância por data dir).

| Método | O que faz |
|---|---|
| `__init__` | — |
| `_entries` | — |
| `_make` | — |
| `start_all` | — |
| `_ensure` | — |
| `stop_all` | — |
| `restart` | — |
| `restart_server` | Reinicia UM servidor (usado pelo supervisor de saúde). |
| `openai_tools` | — |
| `handles` | — |
| `call` | — |
| `status` | — |

| Função | O que faz |
|---|---|
| `map_tool_name(server_name, tool_name)` | figma-demo + figma_create_design -> mcp_figma_demo_figma_create_design |
| `_content_to_text(result)` | — |
| `get_manager(cfg)` | — |
| `_shutdown_all()` | — |

### betterme/doctor.py — 🩺 diagnóstico passo a passo Ollama↔Python

| Função | O que faz |
|---|---|
| `run_checks(cfg)` | — |
| `summary(checks)` | — |

### betterme/emailcfg.py — 🔑 OAuth do e-mail (XOAUTH2 + device code)

| Função | O que faz |
|---|---|
| `secrets_path(cfg)` | — |
| `load(cfg)` | — |
| `save(cfg, data)` | — |
| `xoauth2_string(user, token)` | String SASL XOAUTH2 (padrão de OAuth2 para IMAP/SMTP). |
| `refresh_access_token(acc)` | Access token válido — renova com o refresh_token quando expira. |
| `auth_hint(user, error)` | Diagnóstico amigável: por que o login caiu e o que fazer. |
| `_guess_hosts(user)` | Palpites de servidores IMAP/SMTP pelo domínio do e-mail. |
| `_imap_login(acc)` | Tenta login IMAP; devolve (ok, detalhe). |
| `_smtp_login(acc)` | — |
| `probe_account(user, password)` | Descobre (por tentativa) os servidores que aceitam o login. |
| `add_account(cfg, user, password, account_id, readonly)` | Testa, salva (600) e registra a conta; devolve (conta, relatório). readonly=True (PADRÃO): a conta fica em modo SOMENTE… |
| `register_mcp(cfg)` | Garante que o servidor MCP 'email' está no config (com caminho do arquivo de segredos passado por env — nada de senha n… |
| `oauth_device_flow(provider, client_id, client_secret, print_fn, scopes)` | Fluxo OAuth 'device code' (padrão usado por TVs/CLIs): mostramos um código, você abre o link, entra com o 2FA NORMAL do… |
| `add_oauth_account(cfg, user, provider, client_id, client_secret, print_fn, readonly)` | Cria conta via OAuth (device code), valida IMAP/SMTP e salva. |
| `set_modo(cfg, conta, envio)` | Alterna o modo da conta: envio=True libera ENVIO (e exige SMTP válido); envio=False volta para SOMENTE LEITURA (visuali… |
| `status(cfg)` | — |
| `setup_interactive(cfg)` | `betterme email setup` — pergunta contas, testa, salva e registra. |
| `_oauth_wizard(cfg)` | Assistente OAuth dentro do `betterme email setup` (opção 'o'). |

### betterme/agendacfg.py — 🔑 OAuth da agenda Google

| Função | O que faz |
|---|---|
| `secrets_path(cfg)` | — |
| `load(cfg)` | — |
| `save(cfg, data)` | — |
| `_api_get(acc, path, params, api_base)` | GET autenticado na API do Calendar (único verbo usado — leitura). |
| `fmt_event(ev)` | Uma linha legível: 📅 18/10 14:00–15:00 · Título — 📍 Local · 3 participantes. |
| `list_events(cfg, account, dias, limit, a_partir_de_agora)` | Lista eventos (somente leitura) de uma conta da agenda. |
| `add_account(cfg, user, client_id, client_secret, print_fn)` | Adiciona a agenda de uma conta Google via device code (2FA do provedor, sem senha) e valida o acesso somente leitura. |
| `register_mcp(cfg)` | Registra o servidor MCP 'agenda' (secrets via env — nada no config). |
| `status(cfg)` | — |
| `setup_interactive(cfg)` | `betterme agenda oauth` — assistente device code (uma vez por conta). |

### betterme/activity.py — 📝 registro de atividade (o que aconteceu e quando)

| Função | O que faz |
|---|---|
| `log(cfg, source, message, max_bytes)` | Anexa uma linha de atividade ao agent.log (best-effort). |

### betterme/audit.py — 🧾 auditoria de ações do agente

| Função | O que faz |
|---|---|
| `log(cfg, agent, tool, args, ok, output, duration_ms, source)` | Registra uma ação (nunca lança — auditoria não pode derrubar nada). |
| `_chop(args)` | — |
| `query(cfg, agent, tool, limit, day, month)` | Lê os registros mais recentes (filtros opcionais). |
| `tools_summary(cfg)` | Contagem por ferramenta no mês (para o topo da página Auditoria). |

### betterme/backups.py — 💾 backups automáticos dos dados

| Função | O que faz |
|---|---|
| `_safe_name(name)` | — |
| `backup_file(cfg, path)` | Copia `path` (se existir) para a área de backups; devolve o destino. |
| `_origin_key(path)` | — |
| `list_backups(cfg, origin)` | Backups disponíveis (mais recentes primeiro), opcionalmente de um arquivo. |
| `_remember_origin(cfg, backup_rel_id, origin)` | — |
| `restore(cfg, backup_id)` | Devolve o backup `id` ao arquivo de origem (sobrescreve o atual). |
| `prune(cfg, origin, keep)` | Mantém apenas os N backups mais recentes de `origin`; devolve os apagados. |
| `tool_backups(args, cfg)` | — |

### betterme/metrics.py — 📊 métricas de uso (jsonl)

| Função | O que faz |
|---|---|
| `record(cfg, agent, model, duration_s, tokens, tok_s, steps, status)` | — |
| `recent(cfg, limit, agent)` | — |
| `summary(cfg)` | Médias das últimas N respostas (para o painel). |

### betterme/notify.py — 🔔 notificações ao operador

| Função | O que faz |
|---|---|
| `push(cfg, kind, title, body)` | — |
| `list_all(cfg)` | — |
| `unread_count(cfg)` | — |
| `mark_all_read(cfg)` | — |

### betterme/recipes.py — 📋 receitas: fluxos prontos de uso


### betterme/stt.py — 🎤 ditado por voz (Whisper local)

| Função | O que faz |
|---|---|
| `stt_available()` | — |
| `_get_model(name)` | Carrega (e cacheia) o modelo Whisper — download no primeiro uso. |
| `transcribe(cfg, data)` | Transcreve o áudio (bytes webm/ogg/wav/mp3…) e devolve {ok, text}. |

### betterme/supervisor.py — 👁 supervisor: vigia e reinicia processos

**classe `McpSupervisor`** — —

| Método | O que faz |
|---|---|
| `__init__` | — |
| `start` | — |
| `stop` | — |
| `_loop` | — |
| `check_once` | Reinicia servidores mortos; devolve [{name, restarted, error}]. |


### GUI (index.html) — funções JavaScript principais

| Função | O que faz |
|---|---|

| `checkOnline()` | v3.11.1 — detecta servidor offline e exibe o banner vermelho (casca em cache) |
| `store()` | persistência leve no localStorage (preferências da GUI) |
| `toast()` | aviso flutuante |
| `api()` | fetch com token X-Betterme-Token embutido |
| `esc()` | escape de HTML (anti-injeção na renderização) |
| `mdFmt()` | renderização markdown leve das respostas |
| `copyCode()` | copiar bloco de código |
| `refresh()` | atualiza status/painel |
| `agentAction()` | ▶ liga / ■ desliga / ⟳ reinicia o agente (daemon) |
| `ollamaAction()` | liga/desliga o servidor Ollama |
| `startLog()` | log ao vivo da atividade |
| `togglePause()` | pausa/retoma o log ao vivo |
| `scrollChat()` | autoscroll do chat |
| `suggest()` | sugestões de comandos |
| `toolBlock()` | bloco de ferramenta executada (▸ shell, web…) |
| `loadConversations()` | lista conversas da lateral |
| `openConversation()` | abre uma conversa salva |
| `resetChat()` | ＋ nova conversa |
| `deleteConversation()` | apaga conversa |
| `sendChat()` | envia mensagem e consume o streaming (SSE) |
| `stopChat()` | ■ interrompe a geração |
| `handleEvent()` | despacha cada evento do stream (token, note, brain, approval_request, done…) |
| `loadTasks()` | fila de tarefas do daemon |
| `addTask()` | enfileira tarefa |
| `loadSchedules()` | tarefas ⏰ agendadas |
| `schedAdd()` | cria agendamento |
| `schedRun()` | dispara agendamento agora |
| `loadAudit()` | auditoria |
| `loadOrchStats()` | v3.10 — Saúde do pipeline (funil, tentativas, skills top) |
| `loadPerf()` | desempenho (tok/s) do painel |
| `loadMemory()` | memória de longo prazo |
| `loadModels()` | aba Ollama: modelos + papel de cada um |
| `assignRole()` | atribuição de papel em 1 clique (chips da aba Ollama) |
| `loadSkills()` | catálogo de skills |
| `loadSettings()` | ajustes (toggles ao vivo) |
| `renderApproval()` | cartão de aprovação 🔒/📦 com botões ✅/✏️/⛔ (reusado no banner pós-restart) |
| `approveTask()` | posta a decisão no /api/chat/approve |
| `loadPending()` | v3.11 — banner de pendências que sobreviveram a restart |
| `renderBrain()` | bloco 🔬 por baixo dos panos |
| `toggleBrain()` | liga/desliga a visão 🔬 |

*…e mais 80 funções de
renderização e utilidade (`mdFmt`, `bubble`, `toolBlock`, `fmtUp`…).*

## 7. Segurança

- **token** opcional (`betterme server --token` / `auth_token`) — header
  `X-Betterme-Token`; **anti-CSRF**: POST cross-origin sem token é 403;
- **denylist** de comandos perigosos no `tools.py` (shutdown, dd em
  disco, /dev/sd*, fork bomb…);
- **secrets/** com chmod 600 — credenciais NUNCA passam pelo modelo,
  config versionado, logs ou auditoria;
- e-mail e agenda **somente leitura** por padrão;
- `betterme skills audit` — anti-prompt-injection no catálogo;
- `git grep` anti-segredo antes de todo push; repo sem dados pessoais.

## 8. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "Address already in use" na 8080 | outro processo na porta | `sudo lsof -nP -iTCP:8080 -sTCP:LISTEN` → `kill <PID>` |
| GUI "abre" com servidor desligado | casca em cache do service worker | banner vermelho acusa (v3.11.1); F12 → Application → Unregister + Clear site data |
| aba Ollama vazia com servidor off | normal — cache expira | ligue o Ollama (aba Ollama ▶) e recarregue |
| "não recebo a resposta do agente" | era bug v3.4, corrigido v3.5 | se voltar, reporte (garantidor do done ativo) |
| update falha (sem internet) | GitHub inacessível | `betterme update --check`; ou unzip manual do zip da release |
| Ollama lento | modelo pesado p/ a máquina | aba Ollama → ver tok/s no Painel; troque por modelo menor |

---
*Documento gerado por `gen_doc.py` (parser AST + CHANGELOG). Para
regenerar após mudanças: `python3 tools/gen_doc.py`.*
