# Changelog

## v4.5.0 — 🔍 REVISÃO DE DIFF (PR #8, E4)

`betterme revisar` (ou "revise o diff" no chat, via ferramenta
`revisar_diff`) — **gate único pré-commit/push**:

- **Parte objetiva (zero LLM):** varredura do diff — segredo/CPF na
  tela → CRITICO reprova na hora, mesmo que o revisor aprove.
- **Parte subjetiva (LLM LOCAL):** o revisor lê o `git diff HEAD`
  (teto de 60 KB) e devolve veredito JSON com problemas
  `{arquivo, linha, problema, gravidade}`. **D2: diff tem código —
  a análise roda no Ollama local, NADA vai ao pool gratuito.**
- **Evidência validada (R3):** problema com arquivo fora do diff é
  descartado; reprovar exige substância (crítico, grave, ou veredito
  contra com problema válido) — juiz que rejeita só com evidência
  inventada não bloqueia.
- CLI com exit code (0 aprovado / 1 reprovado) para usar como gate
  de pipeline; em mock, veredito simulado determinístico.

**Testes:** T161–T163 (bug sutil flagrado + segredo reprova mesmo com
juiz aprovando + evidência inventada descartada · diff limpo passa +
diff vazio orienta · CLI exit codes + tool no catálogo) — **163/163**.

## v4.4.0 — 🗺️ GRAFO DE CÓDIGO (PR #7, E3)

"Onde está a lógica de X?" em milissegundos, **zero tokens**.

**`betterme/grafo.py` + `betterme grafo build|query|path`:**
- AST Python PURO (stdlib) — nenhum código do projeto é executado;
  grafo em SQLite no data-dir (`grafo.db`). O repo inteiro do Betterme
  vira grafo em **~0,6 s** (55 arquivos · 822 símbolos · 10.306 arestas).
- Símbolos: funções, classes e métodos (`modulo.Classe.metodo`) com
  `arquivo:linha` e a primeira linha da docstring.
- Arestas COM PROVENIÊNCIA (estilo Graphify — toda aresta sabe de onde
  foi EXTRAÍDA): `chama` (linha do call), `importa` (linha do import),
  `herda` (linha do class).
- `query` busca por nome (substring, case-insensitive) com contagem de
  chamadas; `path A B` traça o caminho de chamadas por BFS (direcionado)
  mostrando cada salto com `arquivo:linha`.
- Build determinístico (mesma árvore → mesmos símbolos/arestas),
  pula `.venv`/`.git`/`__pycache__`/`node_modules` etc.

**Ferramenta `grafo_query` no cérebro:** o modelo pergunta ao grafo em
vez de ler arquivos às cegas — `{"termo": "..."}` localiza,
`{"de": "A", "para": "B"}` traça o caminho. Sem grafo construído →
orientação honesta ("rode `betterme grafo build`").

**Testes:** T157–T160 (build determinístico + proveniência + repo
inteiro · query acha linha certa · tool no catálogo + path A→B +
sem-caminho direcionado · CLI ponta a ponta) — **160/160**.

## v4.3.0 — 🏟️ ARENA DE PROVEDORES (PR #6)

"Qual modelo grátis resolve melhor ESTA task?" — medido, não achismo.

**`betterme arena "<task>" [--n 3]`:**
- A MESMA task roda em TODOS os contendores do pool gratuito (com chave
  em `secrets/` + anônimos como llm7), em **modo resposta**: completion
  pura, sem ferramentas, sem escrever NADA no disco do projeto.
- Cronômetro por contendedor (`--n` rodadas → tempo médio).
- O **revisor** ranqueia os resultados lado a lado e recomenda o
  vencedor: juiz LOCAL (Ollama — nada sai da máquina); indisponível ou
  JSON inválido → **heurística objetiva** (sucesso, adesão, tamanho,
  rapidez — nota 0–10).
- Saída: tabela (provedor · tempo · nota · veredito do revisor ·
  trecho) + 🏆 vencedor + critérios.

**Privacidade (D2 — lei, como sempre):**
- A task é DLP-mascarada ANTES de qualquer payload externo: código e
  segredos jamais saem (T153 prova).
- Nada da arena é persistido: resultado vive na memória/stdout; a única
  escrita é a linha padrão de auditoria no `logs/agent.log` (T151 prova).

**Mock/demo:** pool fake determinístico (groq/gemini/llm7 com respostas
e latências fixas) — `BETTERME_MOCK=1` roda a arena sem rede e sem
chaves, ranking estável.

**Testes:** T149–T156 (mesma task nos N contendores · revisor com
critérios · nada escrito no disco · contendedor morto não derruba a
rodada · DLP antes do pool · juiz local válido/inválido · CLI ·
candidatos reais por chave) — **156/156**.

## v4.2.0 — 📱 GATEWAY DE MENSAGENS: Telegram + WhatsApp (PR #5)

O Betterme no seu bolso: ver status, listar pendências, **aprovar
missões pelo celular** e conversar — com privacidade dura.

**Telegram (nativo, zero deps novas):**
- Long-polling local da Bot API; token em `secrets/telegram.key` 600
  (nunca em config/logs); allowlist de chat_ids
  (`betterme telegram chat-id` cadastra você com 1 mensagem).
- Comandos: /status /tarefas /aprovar /rejeitar /autonomia /perguntar.
- `betterme telegram status|start|stop|chat-id|autorizar`.

**WhatsApp via Playwright (decisão do operador — grátis, local,
removível):**
- Contexto da política: desde 01/10/2026 a Business API cobra até
  RESPOSTA de serviço (franquia 1.000/mês, depois por mensagem) — mas o
  WhatsApp comum segue grátis. Em vez de terceiros (Z-API e afins, que
  LÊM suas mensagens), o canal abre o **WhatsApp Web no SEU navegador em
  background** (Playwright + Chromium local): custo zero, mensagens na
  sua máquina, e você retira quando quiser.
- Pareamento por QR (`<data>/whatsapp-qr.png`), perfil persistente,
  allowlist de números; `betterme whatsapp setup|start|stop|qr|
  autorizar|remover` (remover apaga perfil/QR/allowlist).
- Playwright é **extra opcional** (`pip install
  "betterme-agent[whatsapp]"`); sem ele o canal desativa com instrução
  clara — nunca quebra. ⚠ Módulo EXPERIMENTAL: automação do WhatsApp
  Web viola os termos da Meta (risco de ban); seletores versionados no
  topo do módulo.

**Núcleo (`gateway.py`):** comandos compartilhados; notificação de
pendências NOVAS (poll em disco) com **id + objetivo truncado — nunca
conteúdo de arquivos/memória/segredos**; decisão via `approve()` do
orquestrador com fallback HTTP para o server local (gateway standalone
funciona com o server no ar); autostart junto do `betterme server`
(flags `telegram_on`/`whatsapp_on`, default off).

**Testes:** T142–T148 (token 600, allowlists, parser, decisão approve→
HTTP, push com privacidade+dedup, pareamento QR com Playwright fake,
degradação sem playwright, remoção, fluxo Telegram E2E com HTTP fake,
autostart). **148/148.**

## v4.1.0 — 🏷️ BETTERME: o agente muda de nome (PR #4 do roadmap)
## v4.1.0 — 🏷️ BETTERME: o agente muda de nome (PR #4 do roadmap)

O Hermes Agent passa a se chamar **Betterme**. Renome completo, com
transição suave — nada quebra na máquina do operador.

**O que mudou:**
- Pacote `hermes/` → `betterme/`; CLI **`betterme`** (com alias legado
  `hermes` mantido instalado para scripts/músculo memorizado);
  `betterme-agent` no pyproject; zips `betterme-agent-*.zip`.
- Identidade: o prompt de sistema apresenta "Você é o Betterme"; GUI,
  TUI e mensagens seguem o novo nome.
- **Migração automática do data-dir**: no primeiro uso com caminho
  default, `~/.hermes` é movido para `~/.betterme` (memória, biblioteca,
  secrets, conversas — tudo junto). Data-dirs explícitos nunca são
  tocados.
- Env vars: `BETTERME_MOCK`/`BETTERME_DATA_DIR` (novas) com fallback
  legado `HERMES_*`; variáveis internas de processos renomeadas com
  fallback nos servidores MCP.
- Instruções de projeto: **`BETTERME.md`** (novo nome), com fallback
  legado `HERMES.md` e compatibilidade `AGENTS.md` — precedência
  BETTERME.md > HERMES.md > AGENTS.md.
- systemd: unidades `betterme-agent.service`/`betterme-server.service`
  (re-registre com `betterme daemon boot`).
- `betterme update` continua funcionando: o mecanismo usa o archive
  oficial do GitHub (independente de nome; redirect cobre futuro rename
  do repositório).

**Bugs de renome pegos pela suíte antes da release:** env dos servidores
MCP fora da leva principal (email/agenda "sem conta configurada") e a
regex de modelos gerais em `autoselect` — `hermes3:8b` (nome do MODELO
Ollama, que não muda) tinha parado de casar, o que desordenaria a
auto-atribuição de papéis.

**Testes:** T141 (identidade, alias, env legado, migração com HOME
falso, data-dir explícito intocado) + T129 estendido (precedência
BETTERME.md). **141/141.**

## v4.0.0 — 🚀 A ENTRADA NO MODELO COMPLETO DE AGENTES DE IA
## v4.0.0 — 🚀 A ENTRADA NO MODELO COMPLETO DE AGENTES DE IA

A virada de filosofia (ADR-001): o Hermes deixa de ser "1 cérebro +
skills" e passa a ser **1 CÉREBRO MAIN + especialistas-como-ferramentas**,
com autonomia em 3 níveis, sandbox de kernel, loop de aprendizado e
gerente de código. Decisões D1–D5 do operador viram lei do código.

**M1 — 🛡 Varredura & DLP (`varredura.py`)**
- `hermes varredura` (exit 1 em CRÍTICO — hook pré-push): 11 padrões
  (chaves Groq/OpenAI/Anthropic/Gemini/GitHub/AWS, chave privada,
  Bearer, senha, CPF, e-mail) + **nomes pessoais do data-dir**
  (`varredura-nomes.txt`, privado).
- `mascarar()` — DLP: TODO payload que sai para provedor gratuito passa
  por ele; **código nunca sai** (regra D2), segredos/CPF/e-mail viram
  `[REDACTED]`; `.varredura-ignore` + `# varredura:ok` p/ falsos
  positivos.

**M2 — 📋 Contexto de projeto (`project_context.py`)**
- `HERMES.md` global (data-dir) + do projeto (task scope); `AGENTS.md`
  aceito por compatibilidade (Codex/Qwen); cap 32 KiB; `hermes init`
  gera o scaffold; externo recebe versão DLP-mascarada.

**M3 — ✦ 6 skills de metodologia PT-BR** (adaptadas do superpowers,
reescritas no nosso modelo — fases, nunca subagentes): tdd,
debug-sistematico, verificacao-antes-de-concluir, code-review,
brainstorming, writing-plans.

**M4 — 🧱 Sandbox de kernel (`sandbox_kernel.py`)**
- bubblewrap (fs/namespaces; read-only/workspace-write; `--unshare-net`)
  + **seccomp blocklist em BPF puro** (13 syscalls, x86_64, EPERM);
  probe real com cache; **fallback honesto** para a denylist de app
  (defesa em profundidade); `sandbox_mode: auto|kernel|app`.

**M5 — 🎚 Autonomia em 3 níveis (`autonomy.py`)**
- CAUTELOSO (confirma tudo, inclusive cada comando na TUI) · PADRÃO
  (v3.x: leitura livre, escrita aprovada) · AUTÔNOMO (encadeia sem
  gates soft, ganha **varredura pré-entrega**). Hard gates
  inejociáveis em qualquer nível (denylist, secrets, escopo, D2).
- `hermes autonomia` + `/autonomia` no chat.

**M6 — 🧪 ESPECIALISTAS (`specialists.py`) — o coração**
- revisor · debugger · pesquisador · seguranca: skill injetada em
  contexto limpo, veredito JSON com **evidência obrigatória checada em
  disco** (arquivo:linha:trecho — nada de alucinação), single-writer
  (propõem, nunca escrevem), profundidade 1.
- **Pool de provedores gratuitos** com token bucket (30 RPM groq) e
  fallback local; DLP no caso externo; **exames de competência** com
  cache (reprovado = desativa e segue — nunca quebra); auditoria de
  cada invocação. Tool `especialista()` no cérebro.

**M6.5 — 📚 Loop de aprendizado (`learning.py`)**
- Missão aprovada com ≥5 ferramentas → **rascunho de skill**; reprovada
  → **rascunho de lição**; aprovação SEMPRE do operador (nem AUTÔNOMO
  auto-aprove); aprovar instala no skills do **data-dir privado**
  (backup `.antigo` + auditoria) ou grava na memória.
- `hermes skills aprender <arquivo|URL|texto>` (= /learn do Qwen);
  **busca em conversas passadas** (CLI `hermes conversas buscar` +
  tool `conversas_buscar`).

**M7 — 👔 Gerente de código (`code_manager.py`, D5)**
- Hermes = cérebro main; Claude = gerente de código, **opt-in
  consciente** (`hermes gerente on --yes`) com aviso explícito: o
  código da task vai à nuvem Anthropic (memória/segredos nunca; pool
  grátis segue sem código por D2). Tool `gerente_codigo`.

**M8 — 🖥 GUI: página 🧪 Agentes** (especialistas+exames, seletor de
autonomia, aprendizados pendentes com aprovar/descartar, gerente) +
endpoints `/api/especialistas` `/api/autonomia` `/api/aprendizados`
`/api/gerente` — vanilla JS inline, zero-build.

**Qualidade:** ruff `E9,F,B,PLE` limpo em TODO o repo (incluindo tests/
e tools/). **140/140 testes** (T128–T140 novos; bug real de privacidade
(skill aprendida indo ao repo público) pego pela própria suíte e
corrigido antes da release).

## v3.17.1 — 🩹 hotfix: provedor externo nunca atendia (modelo errado no payload)

**Achado de teste E2E real** (geração ao vivo via llm7): o `Agent` chama
`chat_stream` com `cfg.model` (nome de modelo OLLAMA, ex. `hermes3:8b`) e o
`ExternalClient` usava esse valor por causa de `model or self.model` — a
requisição saía com modelo Ollama para a API externa → HTTP 400
`model_unavailable` → fallback silencioso para o local em TODO chat. Ou
seja: com `hermes provider set <p>` configurado, o provedor externo
**nunca atendia de verdade** (o `provider test` mascarava, pois testa com
o modelo certo).

**Correção:** `ExternalClient.chat_stream` agora usa SEMPRE o modelo do
provedor (`self.model`: default do registro ou `llm_model`) — nomes
Ollama não existem em APIs externas. T127 trava o contrato: agente +
provedor externo → payload com `gpt-oss:20b` (nunca `hermes3:8b`) e com
`llm_model` customizado é ele quem vai.

**Medidas reais registradas (llm7, anônimo, sem chave):** pedido pequeno
OK (RTT ~1 s); prompt completo do agente sem tools OK; payload COM as 13
ferramentas ≈ 2,6 mil tokens estoura a cota diária anônima → nota do
registro atualizada (llm7 = só para provar que funciona; uso real =
groq com chave grátis).

**Extras:** `tui.py` — fechamento `on_event` agora amarra `state` por
iteração (falso-positivo B023 do ruff ≥0.17 em `while`; comportamento
idêntico). Suite: **127/127**.

## v3.17.0 — 🔌 provedores LLM externos GRATUITOS, com privacidade dura

Pedido do operador: foco em provedores SEM custo; seus dados pessoais
NUNCA vão para provedores externos; a memória fica dentro do agente.
Fonte dos provedores: catálogo comunitário awesome-free-llm-apis
(sincronizado diariamente; endpoints compatíveis com a API OpenAI).

**Registro (todos sem cartão):** groq (llama-3.1-8b-instant, 14.4k
req/dia, dezenas de vezes mais rápido que o local) · gemini (2.5-flash,
1M contexto, 1.5k req/dia) · mistral (modo gratuito) · openrouter
(modelos :free) · llm7 (SEM chave, anônimo) · zai (GLM-4.7-Flash) ·
cohere. Cerebras ficou fora (exige cartão).

**Como funciona:**
- `hermes provider list|set <p> [--model] |test|off` (chave pedida
  escondida, gravada em `secrets/<p>.key` 600 — NUNCA em config.yaml,
  logs ou auditoria); `/provider` no chat mostra o estado (chaves não
  passam pelo chat).
- 1 cliente OpenAI-compatível (`llm_providers.py`) cobre todos:
  streaming SSE, tool_calls completos com argumentos normalizados.
- **Fallback automático**: provedor falhou/429/sem internet antes do
  1º token → Ollama local na hora (registrado no log).
- **🔒 Privacidade (regra dura, T125): a MEMÓRIA do agente (fatos
  pessoais) só é injetada no prompt de clientes LOCAIS — provedores
  externos recebem a task sem memória.** Ferramentas, arquivos e
  execução continuam 100% locais; apenas a inferência do LLM sai.

**Testes:** T124 (registro só-grátis, get_client externo+fallback, chave
em secrets 600 fora do config, mock ignora provedor), T125 (memória
presente no local e AUSENTE no externo), T126 (SSE + tool_calls +
fallback no 1º token). **126/126.**

## v3.16.1 — 🧠 memória gerenciável: list/clear + pacote do operador v2 por tópicos

Pedido do operador: adicionar seus dados organizados POR TÓPICOS para o
agente fazer relações — sem repetir o que já existe.

- **`hermes memory list`** — vê todos os fatos na memória (id + texto).
- **`hermes memory clear`** (com confirmação; `--yes` pula) — apaga tudo,
  para reimportar um pacote organizado com ZERO duplicatas.
- **Pacote do operador v2** (`memoria-do-operador.json`, fora do repo):
  44 fatos com tag de tópico — IDENTIDADE, CONTATO, PREFERÊNCIAS,
  EDUCAÇÃO, CARREIRA, BEH, PROJETOS, TRABALHO-RECENTE, INTERESSES,
  PARCERIA — e 3 fatos **[RELAÇÃO]** que cruzam os temas (stack↔projetos↔
  BEH; certificados↔vagas; preferências valem para tudo). Novo: fatos de
  PARCERIA (conteúdo pessoal só no pacote privado, fora do repo).
  Recuperação validada: perguntas
  relacionais agora puxam os fatos de relação na frente.

**Testes:** T123 (import → list → clear → reimport sem duplicatas +
parsers no help). **123/123.**

## v3.16.0 — 🚀 MODO MISSÃO: autonomia com subtasks encadeadas

Pedido do operador: passar UMA tarefa e o agente gerar as tasks em
sequência, validar se deu certo ou errado e, se errado, tentar de novo
com o prompt/task melhorado — até terminar a task inicial de forma
satisfatória.

**Gatilho**: mensagem começa com `missão: <objetivo>` (ou "modo missão:").
O resto do comportamento segue idêntico.

**O ciclo da missão** (`hermes/mission.py`):
1. **Planeja 2-5 subtasks sequenciais** (LLM; fallback determinístico =
   a própria task), cada uma com objetivo concreto e critérios
   verificáveis;
2. **Executa cada subtask como task completa** — pipeline 🎯⚡🔍 com
   revisor, aprovações, escopo de projeto, skills e fôlego de projeto;
   os **critérios da subtask entram no revisor**;
3. **Valida cada subtask**: reprovada → **reescreve a TASK** (prompt
   melhorado a partir do problema apontado pelo revisor) e executa de
   novo (1 reescrita por subtask; o pipeline interno já faz 2 tentativas);
4. **Contexto acumulado**: cada subtask recebe o resumo do que já foi
   feito (nada recomeça do zero);
5. **Validação FINAL**: o revisor julga o objetivo INICIAL contra as
   entregas acumuladas → relatório com ✔/⚠ por subtask, tentativas e
   veredito final.

**Integrações**: pasta do projeto propagada a TODAS as subtasks (missão
de código sem pasta pergunta o caminho UMA vez e retoma a missão inteira
com ele); cancelamento respeitado em qualquer ponto; eventos `note`/
`brain` visíveis na GUI; `/ajuda` documenta o gatilho.

**Testes:** T121 (gatilho, pergunta de caminho, 2 subtasks sequenciais
com critérios no revisor, contexto acumulado, pasta criada, validação
final), T122 (subtask reprovada → task REESCRITA → 3ª execução conclui,
relatório com tentativas). **122/122.**

## v3.15.1 — 📁 contrato do projeto: o agente sempre pede (ou recebe) o caminho

Diretriz do operador: não é "uma pasta" — TODA vez que ele iniciar um
projeto, o agente pede o caminho, busca o local e/ou cria a pasta.

- **Projeto sem caminho no pedido → PERGUNTA**: task de código/projeto
  sem referência de pausa pausa e devolve a pergunta ("📁 preciso do
  caminho da pasta — será buscada e criada se não existir"). Válida nos
  dois caminhos do orquestrador (criação E "quero iniciar um projeto…",
  com sinal de início robusto contra planner vacilante).
- **A resposta retoma a task no lugar certo**: o caminho informado é
  mesclado ao pedido original, a rota vira executar (a decisão do
  operador prevalece sobre o planner), a pasta é criada se não existir
  e todo o trabalho roda lá (arquivos, execução, git, `hermes.md`).
- **Pendência com educação**: por sessão, TTL de 10 min; "cancela"
  encerra; assunto mudou expira na hora (sem pegadinha); flag
  `ask_project_path` (default ligado) devolve o comportamento antigo.
- Vale só no chat interativo — agendador/`hermes run` seguem direto.

**Testes:** T120 (pergunta→retoma com escopo real→ pasta criada;
cancela; assunto mudou; flag off; TTL; "quero iniciar" sem verbo criar
também pergunta e força a rota). **120/120.**

## v3.15.0 — 🚀 assistente completo, independente e sem perda de contexto

Fechamento do plano de 3 PRs da engenharia reversa (Claude Code ×
Hermes): os pontos positivos de cada um, aplicados ao Hermes.

**PR#1 📁 pasta do projeto (rc1)** — o operador passa a referência de
pasta no pedido (em qualquer ponto do diretório, criada se não
existir); task roda lá com ambiente (cwd/git) e `hermes.md`; configura
do Hermes blindada.

**PR#2 🧠 assistente completo (rc2)** — 11 skills de engenharia (5
linguagens, 4 arquiteturas, CI/CD, RAG); biblioteca local com RAG
determinístico (`hermes rag` + ferramenta `knowledge_search`, trecho
verbatim com fonte); `git_run` autônomo no projeto; fôlego 8 passes/40
ferramentas para código; prompt com catálogo orçado.

**PR#2b ✦ skills nativas + delegação (rc3)** — skill baixada do GitHub
(zip/pasta, autoscan de ~/Downloads no boot e a cada 10 min) vira
nativa NA HORA; a skill casada é o MANUAL DA TAREFA e a seção
`## Verificação` dela vira critério do 🔍 revisor.

**PR#3 🔌 independência + contexto (este release)**:
- 🧠 **compactação de contexto** no loop do agente: perto de 55% do
  `num_ctx`, o MEIO da conversa vira resumo (LLM com fallback
  determinístico) e fica o essencial — tarefa original + resultados
  recentes. Conversa longa custa como curta; nada importante se perde.
- 🔌 **Claude Code é plugin opcional**: `/api/status` anuncia
  `claude_available`, a GUI esconde a opção sem a CLI e tarefas
  agendadas caem no loop Hermes com nota. **O Python gerencia tudo;
  o Ollama só serve o modelo.**
- 🎯 selftest ganha 6º cenário: **projeto real** (pasta externa,
  arquivo criado DE VERDADE, executado e versionado no git).

**Testes:** T117 (compactação enxuta + tarefa preservada + custo zero
em conversa curta), T118 (fallback do agendador + status + GUI),
T119 (cenário projeto). **119/119.**

## PR #2b (v3.15.0-rc3) — ✦ skills nativas de qualquer fonte + delegação

Diretriz do operador: skill baixada do GitHub (ou de qualquer lugar) deve
ser NATIVA na hora, casar com o pedido e DELEGAR a entrega para a skill
certa — sem passo manual.

**1. Baixou → é nativa** (`hermes/skills.py`):
- `hermes skills import <fonte>` — pasta local, arquivo .zip, URL
  git/GitHub ou owner/repo (delega no instalador original);
- **autoscan**: no boot do servidor e a cada 10 min no agendador, o
  Hermes varre as pastas assistidas (default `~/Downloads`) — pastas com
  SKILL.md válido E **zips baixados** são importados para
  `~/.hermes/skills/` (idempotente, zip marcado para não reprocessar,
  nada sobrescrito, atividade registrada). Config: `skills_autoscan`
  (default on) e `skills_watch_dirs`;
- `hermes skills scan` — varredura manual.

**2. Casa → delega** (`orchestrator.py`):
- a skill casada entra no executor como **MANUAL DA TAREFA** ("siga
  estas instruções à risca");
- a seção **`## Verificação` da skill vira critério do 🔍 revisor** —
  a skill define o padrão de aceitação da própria entrega.

**3. Bug pego e corrigido**: `SkillLoader.scan()` cacheava por 5 s —
skill recém-instalada/importada só aparecia depois do TTL. Agora toda
instalação/importação **invalida o cache** (nativa NA HORA) — inclusive
no `install_from_github` original da GUI.

**Testes:** T114 (import pasta+zip, nativa, casa, idempotente), T115
(autoscan pasta+zip, sem duplicar, respeita flag off), T116 (delegação:
manual no executor + critérios `[skill x]` no revisor). **116/116.**

## PR #2 (v3.15.0-rc2) — 🧠 assistente completo: engenharia, RAG, git e fôlego

Diretriz do operador: o agente precisa saber e produzir código em
Python, JavaScript, TypeScript, Kotlin e Java; entender arquiteturas
(MVVM, MVI, MDC, SaaS…); consultar livros como RAG; criar pastas,
gerar arquivos, versionar e fazer CI/CD sozinho — escalável,
auto-suficiente, sem perder contexto e sem alucinar.

**1. 📚 Biblioteca RAG local** (`hermes/knowledge.py` + CLI `hermes rag` +
ferramenta `knowledge_search`): livros em `~/.hermes/biblioteca/`
(.md/.txt/.pdf-via-pdftotext), fatiados e indexados por TF-IDF
(stdlib pura, determinístico). O que entra no contexto é TRECHO
VERBATIM com fonte — anti-alucinação por construção. Consulta no
chat, no terminal (`hermes rag "query"`) e reindexação com `hermes rag`.

**2. 🔧 11 skills de engenharia** (catálogo 28→39): codigo-python,
codigo-javascript, codigo-typescript, codigo-kotlin, codigo-java,
arquitetura-mvvm, arquitetura-mvi, arquitetura-mdc, arquitetura-saas,
cicd-github-actions, biblioteca-rag — fluxo, estrutura de referência,
decisões de sênior, armadilhas e verificação para cada tema.

**3. 🌿 Versionamento autônomo** (ferramenta `git_run`): init, status,
add, commit, log, diff, branch, tag, config LOCAL no projeto da task —
com subcomandos fora da lista bloqueados (push fica via run_command,
se o operador quiser) e `config --global/--system` proibido.

**4. 🫁 Fôlego para projetos** (task de código/projeto): 8 passes e 40
ferramentas no lugar de 4/12 — override sempre restaurado (try/finally).

**5. 📉 Prompt escalável**: o catálogo no prompt virou seção ORÇADA
(top 18 relevantes ao pedido + rodapé com o total) — o catálogo pode
crescer indefinidamente sem inflar o prompt (T12 voltou a caber com
folga: 4568 chars).

Bug pego na revisão: descriptions YAML com ": " quebravam o parse
(skill carregava sem description) — corrigido com aspas + validação.

**Testes:** T110 (RAG: índice, busca com fonte, tool, honestidade sem
match), T111 (git no projeto + bloqueios), T112 (casamento das 11
skills com pedidos reais), T113 (fôlego + restauração). **113/113.**

## PR #1 (v3.15.0-rc1) — 📁 pasta do projeto: trabalhe onde o operador mandar

Regra do operador: ao criar projeto/aplicativo, ele passa a referência de
pasta (já criada ou a criar) no próprio pedido — o agente percorre/cria o
caminho em qualquer ponto do diretório, sem interferir na própria
configuração. Era a falha de campo da calculadora (`/media/Arquivos/
projetos/...` nunca alcançada).

- **Detecção**: referências de pasta no pedido (absolutas ou `~/...`);
  URLs, datas (24/09) e pontuação final ignoradas. Vários candidatos são
  validados em ordem.
- **`task_scope`** (thread-local): percorre/cria o caminho, vira o cwd
  dos comandos e libera leitura+escrita DENTRO da pasta — só desta task.
  Tasks concorrentes não vazam escopo.
- **Blindagem**: home raiz, `~/.hermes` (configuração) e diretórios de
  sistema nunca viram escopo; sandbox segue valendo fora da pasta.
- **Ambiente injetado no executor** (padrão Claude Code): cwd, data, SO,
  git do projeto (branch + alterações) e **`hermes.md`** — memória do
  projeto com as convenções do operador.
- Evento visível `📁 workspace da task: ...`; pasta recusada → `⚠` e
  segue no workspace padrão.

**Testes:** T107 (detecção: pontos no caminho, URLs/datas ignoradas,
sistema/config recusados), T108 (escopo funcional: cwd, escrita,
thread-local, pós-escopo bloqueado), T109 (E2E: ambiente + hermes.md no
prompt, pasta criada, sem referência nada muda). **109/109.**

## v3.14.2 — 🗺 Mapa da aplicação + auditoria profunda (12 correções)

Pedido do operador: antes de novas melhorias, criar mapas da aplicação
com contexto de cada ponto, entender o funcionamento profundamente e
caçar as pequenas falhas.

**Novo documento: `MAPA_APLICACAO.md`** — mapa geral, módulos com papel
e dependências, fluxo do chat (pipeline), fluxo do Claude Code, skills,
memória, dados em disco, 76 rotas da API, camadas de segurança,
agendador, MCP, update/backups, testes e as decisões de arquitetura
(incluindo limites conhecidos).

**Auditoria**: grafo de imports completo · 161 achados de lint triados
um a um (111 intencionais — sandbox defensivo) · persistência ·
scheduler (sem race de disparo duplo — flag running gravada antes de
executar) · auth 71/71 rotas · SSE · cleanup de processos · sandbox de
caminhos · update.

**Correções:**
1. 🐛 **/goal ecoado 3× com linhas duplicadas** (bug de campo): cada
   Enter durante a resposta disparava um POST novo (runSlash sem
   guarda) e o comando era renderizado 2× (span + prefixo). Corrigido
   na raiz, com guarda e render único.
2. `set_goal` e `_pending_save` agora gravam **tmp+replace atômico**
   (crash não corrompe goals/aprovações).
3. Processo do Claude recolhido no finally (`wait`+`kill`) — sem zombie.
4. fd do log do Ollama fechado no pai após spawn (vazamento por boot).
5. Auto-update defende **zip-slip** (`_assert_zip_seguro`, testado com
   zip malicioso).
6-12. import deprecated→collections.abc · import morto removido ·
   mcp-servers executáveis · if aninhado/startswith/check=False
   explicitados.

**Testes:** T104 (goal sem eco, funcional), T105 (escrita atômica +
recolhimento de processo + fd), T106 (zip-slip). **106/106.**

## v3.14.1 — 🎭✦ Claude sênior com skills e goal (fim do "não sou especialista")

Pergunta do operador: como os agentes ativos estão usando as skills —
e por que não usam? Diagnóstico com evidência (auditoria de campo):

**1. 🎭 Persona SÊNIOR no Claude Code** — o transcript mostrou o Claude
recusando ("não sou especialista em Node.js") e entregando links. O
prompt do modo leve dizia apenas "agente prático". Agora: ENGENHEIRO
DE SOFTWARE SÊNIOR ("o especialista da casa"), RECUSAR TAREFA É FALHA
GRAVE, assunto novo → aprende na hora (Read/Bash), código → arquivo
completo + execução com saída colada.

**2. ✦ Skills e 🎯 goal chegam ao Claude** — antes o Claude Code não
recebia NENHUMA skill nem o objetivo da sessão (por design do modo
leve mínimo). Agora `_enrich_prompt` injeta a skill que casa com o
pedido (conteúdo, máx. 1, cortada em 1800 chars) e o goal da sessão —
o mesmo contexto que o Hermes pipeline já tinha.

**3. ✦ codigo-verificado casa com pedidos reais** — descrição ganhou
os gatilhos que faltavam (javascript, node, calculadora, aplicativo,
website…). Nota de engenharia: uma regra de casamento por NOME de
skill foi experimentada e REVERTIDA — "memória" (RAM do sistema)
casava com memoria-contexto (memória do agente): ambiguidade pega
pelos testes de precisão T59/T74. O casamento continua só por
descrição (score >= 2), agora com vocabulário completo.

**Testes:** T102 (persona, skill injetada no prompt do Claude, goal,
enxuto em pedido genérico) e T103 (calculadora/projeto casam;
ambíguo "memória ram" continua NÃO casando; regressões). **103/103.**

## v3.14.0 — 🧪 passada de QA sênior: análise estática + QA do QA + matriz de todos os modelos

Pedido do operador: validação meticulosa para situações REAIS, com
testes de todos os modelos e mínimo de alucinação.

**1. 🔍 Análise estática (ruff) em todo o código** — 29 achados,
todos triados e resolvidos: 4 reais (docstring quebrada no autoselect
que veio da v3.11.4, `raise` sem `from` no memory import, variável
vestigial no claude_agent, closures B023 no selftest) + 25 cosméticos
(imports mortos, f-strings vazias, item duplicado em set). Código
limpo no conjunto E9/F/B/PLE.

**2. 🧪 `hermes selftest --all-models`** — a matriz: TODOS os modelos
instalados × 5 cenários de campo (diagnóstico, código verificado,
dados reais, conhecimento, memória), com tempo por modelo e
RECOMENDAÇÃO (mais ✔; empate → mais rápido). Sai a resposta
mensurável para "qual modelo alucina menos na MINHA máquina".

**3. ✅ QA do QA (T100)** — os checkers do selftest foram testados
contra as falhas REAIS do campo: a recusa literal do transcript do
operador é flagrada; código sem execução flagra; dado errado flagra;
entregas boas passam limpas. Um teste que não consegue falhar não
prova nada — agora ele falha quando deve.

**4. ✅ Validação EFETIVA (não só lógica)** — executada ao vivo:
SSE real pela rede (waitress de verdade: 59 eventos, done chegou
exatamente 1× — o garantidor validado na pilha real), roundtrip real
de ferramentas (write_file + run_command com saída "5" real), sandbox
bloqueando escrita fora do workspace, e diagnostico_sistema já
validado com dados reais do sistema.

**Testes:** T100 (QA do QA), T101 (matriz: pula limpa em mock, flag
--all-models, 5 cenários, recomendação). **101/101.**

## v3.13.3 — 🔬 código só entrega executado + `hermes selftest` (LLM real)

Pergunta do operador: "e se eu pedir OUTROS tipos de tarefa (geração
de código, projetos)? Pode alucinar e entregar errado/incompleto?"

**1. ✅ Critério estrutural para código** — tarefas de código
(`_CODIGO_RE`) ganham critério automático que o REVISOR passa a cobrar:
"o código foi ESCRITO em arquivo e EXECUTADO, com a SAÍDA REAL colada
na resposta". Rastro > opinião do modelo: código que não rodou não
entrega mais. Nova skill `codigo-verificado` (28 no catálogo) ensina o
fluxo completo — escrever, executar, ler saída, corrigir (máx. 3
rodadas), anti-alucinação (biblioteca instalada? coluna REAL do
arquivo?), entrega com limites declarados.

**2. 🧪 `hermes selftest` — bateria de aceitação com LLM REAL** — a
resposta mensurável para "pode alucinar?": 5 cenários de campo
(diagnóstico do dispositivo, código verificado com saída "5", dados
reais com total "60", conhecimento completo, memória que guarda e usa)
verificam entrega não-vazia, SEM recusa, COM evidência de ferramenta.
Pula limpo em mock ou sem Ollama. Rode na sua máquina:
`hermes selftest` — relatório pronto para me mandar quando reprovar.

**Teste:** T99 (critério de execução injetado p/ código e não p/
outros, skill casa com "gere código python para o meu projeto", 5
cenários, pulada limpa em mock, CLI exposta). **99/99.**

## v3.13.2 — 🔎 diagnóstico do dispositivo em UMA chamada

Segunda bateria de campo do operador revelou os três modos de falha do
hermes3:8b sob offload pesado em "busca geral no sistema":
1. **recusa** ("não vou repetir… pronto para ajudar") — entregava nada;
2. **alucinação** — inventou um `history` que nunca rodou e diretórios
   "total 0" (T0011);
3. **saída crua** — respondeu com output de comando sem interpretar
   (T0012).

Causa comum: a tarefa exigia que um 8B lento orquestrasse 9+ chamadas
(sys_info ×9 na auditoria). Modelo fraco + muitas decisões = flail.

**Correção estrutural — nova ferramenta `diagnostico_sistema`:** o
diagnóstico INTEIRO numa chamada só. Bateria fixa somente-leitura
(sistema, disco, memória, top RAM/CPU, maiores pastas da home,
bateria, GPU/VRAM, uptime, últimos logins), digesto real e compacto
(≤4000 chars, cabe no num_ctx 3072). O executor vira interpretador de
dados que já tem — que é o que um 8B faz bem. A skill atalhos-shell
agora direciona: diagnóstico geral = UMA chamada, e sua descrição
casou com o pedido natural ("busca geral no sistema / uso do
dispositivo").

**Blindagem extra:** a mensagem de refazer do revisor agora proíbe
explicitamente recusa E saída crua sem interpretação ("NÃO são
resposta — são falha de entrega").

**Teste:** T98 (digesto real com as seções, compacto, registrado no
catálogo, mensagens de refazer, skill casa com o pedido original).
**98/98.**

## v3.13.1 — 🩹🔓 dois bugs reais do campo (recusa vazia + home bloqueada)

Primeira bateria real do operador no próprio notebook, com Auditoria
como evidência. Dois bugs encontrados e corrigidos:

**1. 🩹 Executor "não vou repetir" e não respondia NADA** — pedido de
diagnóstico: o guard anti-loop dizia "não repita a chamada nem o
texto" e o modelo respondia com uma RECUSA ("Estou pronto para
ajudar") em vez da resposta. Revisor reprovava 2× e a task morria sem
entregar nada (199,5s perdidos). Correção: o nudge agora é explícito
("NUNCA se recuse a responder… 'não vou repetir' NÃO é resposta — cite
os números coletados e conclua") e a mensagem de refazer instrui a
usar os dados JÁ COLETADOS e escrever a resposta final COMPLETA.

**2. 🔓 "Busca geral no sistema" era impossível** — o sandbox bloqueava
a HOME inteira (auditoria: `list_dir ✖ /home/beh-solutions`), e o
agente ficava perdido chamando sys_info 7×. Correção: nova config
`sandbox_home_read` (padrão ligado) — LEITURA da home liberada para
diagnósticos, ESCRITA continua só no workspace, e pastas sensíveis
(~/.ssh, ~/.hermes/secrets, ~/.gnupg, ~/.config, ~/.netrc…) JAMAIS são
lidas — credenciais não entram no contexto do modelo.

**Dica de velocidade documentada** (RTX 2050 4 GB): `hermes config set
num_ctx 3072` — o padrão 8192 força offload pesado do hermes3:8b para
a CPU (0,5–0,7 tok/s medidos pelo operador); contexto menor = mais
camadas na GPU = respostas bem mais rápidas.

**Testes:** T96 (nudge e refazer exigem resposta completa) e T97
(leitura da home ✔ · sensíveis bloqueados ✔ · escrita presa no
workspace ✔ · flag desliga ✔). **97/97.**

## v3.13.0 — ⚡💪 autonomia barata: cache de planos + skills do dia a dia

Pedido do operador: agente executando tarefas do dia a dia de maneira
rápida e simples, "sem ficar pensando muito", com autonomia no longo
prazo e MENOS tokens e repetições.

**1. 💾 Cache de planos** — pedido REPETIDO não gasta planejamento: a
2ª vez com a mesma mensagem (mesma instalação) custa ZERO chamadas ao
modelo. O cache invalida sozinho quando o operador ensina algo novo
(edita plano/entrega ou reprova) — preferência nova, plano novo.
Instalações diferentes não compartilham cache.

**2. ✦ 5 skills de rotina (catálogo: 27)** — problemas do dia a dia
resolvidos com caminho curto:
- `caminho-curto` — o mais barato primeiro: já sei → responso; simples
  → um comando; só tarefa nova merece plano;
- `atalhos-shell` — receitas de 1 linha: disco, RAM, arquivos grandes,
  dono da porta, backup rápido;
- `organizador-arquivos` — downloads/desktop: separar por tipo,
  duplicados por hash, zonas intocáveis (~/.hermes, ~/.ssh), relatório;
- `briefing-diario` — resumo da manhã (agenda, e-mails, ⏰, máquina,
  manchetes) em 8 linhas — AGENDÁVEL, roda sozinho;
- `autocorrecao` — comando falhou? Lê o erro, corrige local, repete —
  sem replanejar a tarefa (máx 2 correções, depois relato honesto).

**3. 🧽 Prompt de sistema mais leve** — o catálogo de skills no prompt
emagreceu (descrições de 90 → 60 chars): 6482 → **5711 chars** por
conversa, com folga para o catálogo crescer.

**Testes:** T94 (cache: repetição = 0 chamadas, edição invalida,
instalações separadas) e T95 (as 5 skills casam com pedidos naturais +
auditoria limpa). **95/95.**

## v3.12.0 — 🧠 transferência de memória + 4 skills do agente sênior

Pedido do operador: passar a memória/contexto acumulado sobre ele PARA
o agente, junto com skills do próprio agente de IA que o atende.

**1. 🧠 `hermes memory import <arquivo>`** — importa fatos para a
memória de longo prazo (injetada em TODAS as conversas e tarefas).
Formato: JSON lista de strings OU texto com um fato por linha
(comentários `#` ignorados). Duplicados são pulados — importar duas
vezes não duplica. O arquivo com o contexto do operador fica FORA do
repo (dado pessoal; repo é público), entregue junto como
`memoria-do-operador.json`.

**2. ✦ 4 skills novas no catálogo (22 no total)** — disciplinas do
agente sênior traduzidas para o formato do Hermes, todas aprovadas na
auditoria:
- `edicao-cirurgica` — âncora exata, um ponto por vez, verificação
  após cada edição, rollback se quebrou;
- `diagnostico-raiz` — sintoma → hipóteses → prova uma a uma → causa
  raiz → teste de regressão (a lição do "localhost fantasma");
- `entrega-verificada` — checklist de 5 perguntas antes de qualquer
  "pronto" (respondi o pedido? evidência? cumpri promessas? claro?
  executei em vez de instruir?);
- `release-disciplinada` — testes verdes, bump, changelog honesto,
  anti-segredo, tag e pacote verificado.

**Testes:** T93 (import JSON/texto, dedupe, erro claro em arquivo
ruim, via CLI). Auditoria: 22/22 limpas. **93/93.**

## v3.11.5 — ⚡🧽 fim da lentidão e das respostas sujas (regressão da v3.11.3)

Regressão real reportada pelo operador: "o agente ficou lento e
incorreto, perdeu as respostas limpas". Causa: o auto-atribuidor
(v3.11.3) colocou o qwen2.5-coder:7b como ⚡ executor — (1) cada task
passou a TROCAR de modelo entre etapas (🎯 hermes3:8b → ⚡ coder → 🔍
hermes3:8b): segundos de swap a cada etapa em GPU de 4 GB sem VRAM
para dois modelos residentes; (2) o executor é quem ESCREVE a
resposta — modelo de código escreve prosa pior.

**Correção 1 — modo econômico por padrão:** `pipeline_single_model:
true` no config. O `hermes models auto` agora deixa 🎯 orquestrador,
🔍 revisor e ⚡ executor **herdando o 💬 chat** (campo vazio = 1 modelo
residente, ZERO trocas) — velocidade e prosa do hermes3:8b de volta.
Por papel continua disponível: `hermes models auto --multi` ou
`pipeline_single_model: false` (para máquina melhor no futuro).

**Correção 2 — experiência enxuta:** o bloco de experiência do
planejador passou de 1600 para **800 chars**, no máximo **4 sinais**,
com sinais FORTES primeiro (edições do operador e reprovações) —
prompt menor = planejamento mais rápido e menos distração para o 8B.

**Testes:** T92 (econômico por padrão: papéis herdam chat e model_for
resolve; --multi e config liberam por papel; experiência prioriza
edição e corta em 800), T80/T90 atualizados ao novo contrato. **92/92.**

## v3.11.4 — 🛡 auto-assign respeita o hardware (teto max_model_b)

Fato novo do operador: GPU RTX 2050 com 4 GB de VRAM. Modelos acima
de ~9B (gemma3:12b = 8.2 GB, qwen3-coder:30b = 19 GB no catálogo)
rodariam com offload pesado — lentos para o uso diário.

**Mudança:** o auto-atribuidor (v3.11.3) agora tem teto de tamanho:
`max_model_b` no config (**padrão 9.0** — filosofia local ≤8B do
projeto). Modelos acima do teto são IGNORADOS na escolha e listados
("⛔ ignorados acima do teto"). Máquina melhor no futuro?
`hermes config set max_model_b 12` libera na hora.

**Teste:** T91 — com gemma3:12b e qwen3-coder:30b "instalados", nenhum
papel os recebe; teto 12 libera a 12b; teto 4 restringe a pequenos;
default e coerce no config conferidos. **91/91.**

## v3.11.3 — ✨ auto-atribuição dos melhores modelos por papel

Pedido do operador: "selecionar automaticamente as melhores LLMs para
cada atividade". Novo `hermes/autoselect.py` lê os modelos INSTALADOS
no Ollama e escolhe o melhor para cada papel, com critérios
explicáveis (cada escolha vem com o motivo):

- ⚡ executor: modelo de CÓDIGO ganha bônus (qwen-coder, codellama…);
- 🎯 orquestrador / 🔍 revisor: modelo GERAL maior (raciocínio);
- 💬 chat: a escolha ATUAL do operador é respeitada;
- 🔌 claude: geral para seguir instruções;
- tamanho (B) conta a favor até o teto de 9B (máquina local).

Na máquina do operador (7 modelos instalados) o resultado é:
💬 🎯 🔍 🔌 hermes3:8b · ⚡ qwen2.5-coder:7b. Instalar um modelo novo e
rodar de novo re-atribui tudo sozinho — a leitura é sempre da lista
instalada no momento.

**Onde:** CLI `hermes models auto` · GUI aba Ollama → botão
"✨ auto-atribuir papéis" · endpoint `POST /api/ollama/auto-assign`
(aplica e salva no config).

**Teste:** T90 — aceitação com a lista REAL do operador (chat respeita
a escolha, orquestrador/revisor = maior geral, executor = modelo de
código, pequenos nunca escolhidos), fallback sem modelo de código,
endpoint persiste, botão na GUI, CLI. **90/90.**

## v3.11.2 — 🩹 GUI volta a funcionar no navegador (SyntaxError da v3.9)

Bug real encontrado PELO OPERADOR na própria máquina: a página abria
com o JavaScript morto — console: `Uncaught SyntaxError (index):1884`,
`ollamaAction is not defined`, `agentAction is not defined` e o log da
GUI parado em "conectando ao stream…".

**Causa:** na v3.9.0, a linha do botão de papel da aba Ollama saiu com
`''` (duas strings justapostas, sem operador) onde deveria estar `\'`
(aspas escapadas) — erro de camada de escape no patch. Um erro de
sintaxe mata o bloco `<script>` INTEIRO: todos os handlers inline
(agentAction, ollamaAction, assignRole…) ficavam indefinidos e a GUI
não respondia a nada. Os testes E2E não viam porque só conversam com a
API — nunca executam JavaScript.

**Correção:** escape correto na linha do `onclick` do `assignRole`.

**Blindagem (T89):** o JS da página agora é PARSEADO de verdade a cada
release (QuickJS — `pip install quickjs` no ambiente de teste; o teste
avisa e pula só o parse se ausente) e todo `onclick` do HTML precisa
apontar para uma função existente. **89/89.**

## v3.11.1 — 🚨 banner "server OFFLINE" (fim do fantasma do cache)

Sintoma real do operador: com o servidor desligado, abrir
`localhost:8080` no navegador ainda "abria a aplicação" — e parecia
rodando full-time. Causa: o service worker (shell offline, v3.2)
serve a CASCA da GUI salva em cache, com as chamadas de API falhando
em silêncio. Nenhum processo roda — mas a página parece viva.

Correção: a GUI agora se autodiagnostica (`/api/status` a cada 5s) e,
sem resposta, exibe um **banner vermelho fixo** no topo:

  ⚠ Hermes server OFFLINE — isto é a casca em cache do navegador (a
  aplicação NÃO está rodando nesta máquina). Ligue com: hermes server

O banner some sozinho quando o servidor volta. T88 cobra o banner, o
detector e o service worker. **88/88.**

## v3.11.0 — 🔁🛡 estado sobrevive a restart + auditoria de skills

Escopo escolhido pelo operador (frentes 1+2 do ranking pós-v3.10).

**1. 🔁 Estado persistente** — goals de sessão e aprovações pendentes
saem da RAM e vão para o disco (`session_goals.json`,
`pending_approvals.json`):
- `/goal` definido antes de um restart continua valendo depois;
- restart no meio do portão de CRIAÇÃO não perde mais a task: o plano
  pendente re-aparece na GUI (banner no topo do chat, mesmo UI de
  aprovar/editar) e, ao decidir, a execução RETOMA em thread nova —
  mesmo id de task, revisão incluída, edição marcada na memória de
  experiência;
- restart no meio do portão de ENTREGA: o texto final re-aparece;
  entregar/editar finaliza e registra na hora; "refazer" é recusado
  com mensagem honesta (a execução já terminou);
- a pendência só sai do disco quando o operador DECIDE — timeout não
  apaga mais trabalho;
- novo endpoint `GET /api/approvals/pending` + banner no chat (8s).

**2. 🛡 `hermes skills audit`** — auditoria automática do catálogo:
frontmatter (name/description), name ≠ pasta, description curta
(gatilhos fracos), tamanho fora do orçamento (8 KB), prompt injection
(7 padrões, com guarda de negação — quem ensina "nunca revele a senha"
não é acusado) e duplicatas de nome declarado. Saída 0 = catálogo
limpo. Hoje: **18/18 limpas**.

**Testes:** T83 (goal sobrevive a restart, /goal na GUI), T84 (plano
pendente re-aparece, edição retoma execução e registra "retomada"),
T85 (entrega pendente finaliza; refazer recusado), T86 (auditoria
detecta injeção/campos/nome/tamanho/duplicata e não acusa negação),
T87 (catálogo real 18/18 limpo). **87/87.**

## v3.10.1 — 🧪 aceitação: melhoria prometida × melhoria medida

O operador pediu prova: "houve melhoria mesmo? está dentro do esperado?"
Cada frente do v3.10.0 virou critério mensurável (T79–T82), com o
resultado esperado definido ANTES da medição — e tudo medido:

- **T79 · 🧠 experiência muda decisão** — esperado: 1 edição do
  operador muda a decisão da task seguinte. Medido: sem histórico o
  planejador decide `executar` (relatório detalhado); após registrar a
  edição "sem preâmbulo", a MESMA mensagem vira `responder`. Cadeia
  completa edição → jsonl → experience() → prompt → decisão.
- **T80 · 🧠 persistência e limites** — esperado: memória no disco, sem
  explodir contexto. Medido: novo processo (outro Config no mesmo
  data_dir) mantém a preferência; janela de 6 tasks; com 30 tasks no
  disco o bloco corta em exatos 1600 chars; histórico vazio não injeta.
- **T81 · ⬇ update ponta a ponta** — esperado: 1 comando atualiza e
  preserva dados. Medido: v3.10.0 → v3.11.0 com download real em
  13 ms; conversas.json intacto; .venv intacto; arquivos locais não
  apagados; downgrade recusado; `--check` avisa sem aplicar.
- **T82 · 📊 painel sem número inventado** — esperado: todos os campos
  conferem com o jsonl bruto. Medido: 120 tasks aleatórias (semente
  fixa), os 8 campos do `/api/orchestrator/stats` idênticos ao
  recálculo independente; 1000 tasks respondem em 6 ms.

**82/82.** Nota honesta: com LLM mockado, T79 prova que o SINAL chega e
muda a decisão de quem o lê; a melhoria de longo prazo (aprovação na
1ª subindo) é medida pelo próprio painel de saúde durante o uso real.

## v3.10.0 — 🧠⬇📊 o orquestrador aprende + update em 1 comando + painel de saúde

Versão escolhida pelo operador (frentes 1+2+3 do diagnóstico de melhorias).

**1. 🧠 Memória de experiência** — o orquestrador agora APRENDE com o
histórico: as últimas tasks registradas em `orchestrator_tasks.jsonl`
(resultados, reprovações, tentativas e, principalmente, as EDIÇÕES do
operador em planos e entregas) entram como contexto do planejamento.
Editar uma entrega uma vez vira preferência permanente: o novo
`experience()` em `orchestrator.py` resume cada task ("o operador
EDITOU a entrega para: …") e o `plan()` injeta isso antes da mensagem
atual. Repetir erro que já foi corrigido ficou sem desculpa.

**2. ⬇ `hermes update`** — fim do ritual unzip+pip manual: o comando
consulta a última tag estável no GitHub, compara com a versão
instalada, baixa o zip da tag e aplica sobre a instalação atual —
preservando `data/`, `.venv` e `.git`. Usa só stdlib (urllib/zipfile).
`hermes update --check` só avisa; `hermes update -y` aplica sem
perguntar (para scripts). Novo módulo `hermes/update.py`.

**3. 📊 Painel de saúde do pipeline** — novo card no Painel da GUI com
o funil completo a partir das tasks reais: aprovação na 1ª tentativa
(%), tentativas médias, duração média, edições do operador, skills mais
usadas e tasks por dia (últimos 14). Novo endpoint
`/api/orchestrator/stats`. Aprovação na 1ª subindo = o orquestrador
está aprendendo com suas edições.

**Testes:** T76 (experiência vira few-shot do planejador, edição de
entrega aparece no prompt), T77 (update offline: última tag estável,
comparação de versões, apply preserva data/.venv), T78 (funil do
painel confere com o jsonl + card na GUI). **78/78.**

## v3.9.0 — 🧠 aba Ollama: todos os modelos instalados + papel de cada um

Pedido do operador: ver TODOS os modelos instalados nativamente na aba
Ollama. A lista já existia, mas tinha dois furos — corrigidos e ampliados:

**1. Servidor desligado ≠ "nenhum modelo":** antes, com o Ollama parado,
a aba mostrava "nenhum modelo instalado" (mentira — estavam no disco).
Agora a última listagem boa fica em cache (data/ollama_models_cache.json)
e é exibida com aviso "⚠ servidor desligado — última lista conhecida
(hh:mm)".

**2. Papel de cada modelo, visível e atribuível na hora:** cada modelo
mostra chips com os papéis que exerce (💬 chat · 🎯 orquestrador · 🔍
revisor · ⚡ executor · 🔌 claude) e botões para atribuir cada papel com
UM clique — clicar de novo no papel ativo volta ao padrão. A lista vem
ordenada (modelo em uso primeiro) e mostra tamanho + data de cada um.

Teste T75: cache com servidor desligado (vazio → cache → papéis via
settings), reflexo dos 4 papéis na resposta e botões na GUI.
Suíte: **75/75**.

## v3.8.0 — ✦ catálogo de 18 skills curadas · 🔍 4º papel de modelo · 🧪 bateria E2E/integração/performance/estresse

**✦ Catálogo de skills curado (do material de pesquisa do operador):**
13 skills novas, filtradas das melhores indicações (Ponytail, debug
sistemático, análise de dados "números só do código", RAG com citação,
segurança/anti-vazamento, testes/QA, PDF/OCR, Power BI/DAX, Excel/VBA,
produção industrial/OEE, relatórios, memória com disciplina, criar-skill)
+ as 5 existentes = **18 ativas**, todas em PT-BR, no formato nativo e
sem scripts executáveis (segurança). Casamento por palavra-chave com
sinônimos — sem falso-positivo (o pedido de RAM não casa com nada, o de
CSV/pandas casa com analise-dados, o de OEE com produção-industrial).

**🔍 Quatro papéis de modelo (os "5-6 modelos, um para cada uso"):**
chat (padrão) · 🎯 orquestrador · 🔍 revisor (novo campo, herda do
orquestrador quando vazio) · ⚡ executor — + o Claude Code. Todos
sequenciais (nunca paralelo). Campos em Ajustes com sugestões.

**🧪 Bateria de testes ampliada (+12 casos, 74 no total):**
- E2E: jornada completa (sessão → /goal → task com skill → selo → tudo
  persistido em conversa/task/métricas) e o portão de criação com
  EDIÇÃO de plano e de entrega;
- Integração: skills×modelos×pipeline (skill certa injetada, modelo do
  papel usado), uma rodada de chat deixa rastro em TODOS os módulos,
  settings desligam o revisor AO VIVO (e o selo some — bug corrigido);
- Performance: plano <0,5s, casamento de skills <1s, JSON em 40 KB de
  lixo <0,4s, 100 tasks <0,5s, endpoints <0,5s, pipeline mock <8s/20s,
  GUI <400 KB;
- Estresse: 12 chats simultâneos (todos entregam 1 done, zero erros),
  rajada de 60 comandos slash, histórico de 60 mensagens + payload de
  8 KB, 30 skills extras no diretório do usuário + 50 fatos de memória.

Correção de bug real encontrada pela bateria: selo "🔍 revisada" era
aplicado mesmo com o revisor desligado.

## v3.7.0 — 🎭 modelos por papel (sem paralelismo) · 🗨 respostas entendíveis · 🧰 Ferramentas reconstruídas

Três pedidos do operador:

**🎭 Um modelo para pensar, outro para executar — SEM rodar em paralelo.**
Decisão de arquitetura: o pipeline é SEQUENCIAL por natureza (planejar →
executar → revisar), então cada PAPEL usa seu modelo, um carregado por
vez — o Ollama faz a troca sozinha (~2-5 s por swap). Paralelo não cabe
no hardware local (dois modelos 8B ≈ 12 GB de VRAM/RAM) e não traria
ganho: as etapas dependem umas das outras. Novos campos em Ajustes:
- 🎯 **modelo do orquestrador/revisor** — raciocínio e instrução
  (sugestões: qwen3:8b, gemma3:12b);
- ⚡ **modelo do executor** — function calling (sugestões:
  qwen3-coder:8b, llama3.1:8b).
Vazio = o modelo padrão do agente (comportamento de antes). O override é
aplicado no ponto único de execução e SEMPRE restaurado (try/finally).

**🗨 Respostas plausíveis e entendíveis pela pessoa que pediu.** O padrão
de qualidade do executor ganhou a regra de COMUNICAÇÃO: escrever para a
PESSOA, explicando o que os dados SIGNIFICAM em português claro (ex.:
"a memória está 41% em uso, sobra 9 GB — saudável"), sem colar saída crua
sem explicação. O revisor passa a cobrar isso (item ENTREGA: "entendível
para a pessoa que pediu"), e o planejador sugere critérios de explicação.

**🧰 Página Ferramentas reconstruída** (o operador reportou botões/inputs
quebrados): novo componente de formulário (.frow) com labels, inputs
flexíveis que não colapsam e botões alinhados — Terminal rápido, Arquivos
e Web reescritos; textarea com altura fixa; previews padronizados.

Testes T61–T62 (modelos por papel: override aplicado durante a execução e
restaurado sempre; ferramentas sem hacks inline; regras de comunicação).
Suíte: **62/62**.

## v3.6.0 — 🛠 lições da primeira bateria real do operador (5 correções de comportamento)

Diagnóstico a partir de um log REAL do operador (Zorin OS, Ollama local):
tarefas simples em parte funcionaram, em parte não. As cinco falhas
observadas foram corrigidas na raiz:

**1. Revisor reprovava resposta BOA com critério inventado** ("falta de
solicitação explícita…"). Agora o revisor é ANCORADO: julga apenas pelo
objetivo e critérios da task, NÃO inventa critérios, ignora perguntas de
cortesia ("precisa de algo mais?") e aprova quando os dados reais estão lá.

**2. Skill errada aplicada** ("✦ resumo-inbox" num pedido de memória RAM
— falso-positivo por palavras genéricas). O casamento de skills agora
ignora palavras genéricas (resumo, detalhado, uso, dados, notebook…);
só termos distintivos pontuam. RAM → nenhuma skill; e-mail → resumo-inbox.

**3. Executor PERGUNTANDO em vez de executar** (4× no log: "poderia
fornecer mais detalhes?"). A retomada pós-reprovação agora é imperativa:
"EXECUTE AGORA, sem perguntar nada a ninguém: <passos numerados com
comandos> … PEDIDO ORIGINAL: …".

**4. Orquestrador sem contexto da conversa** ("está na mesma conversa, o
ideal era você ter acesso a esses dados" → interpretado como pedido de
`ls`, executou literal `/path/to/directory`). O planejador agora recebe
as últimas falas da conversa + a ÚLTIMA TASK registrada quando a mensagem
se refere a trabalho anterior.

**5. "Conclua meu pedido anterior" virava conversa** (2.1s, "me diga
mais detalhes"). Regra de continuação no prompt (com exemplo), palavra
de continuação na heurística e herança da última task.

Passos do plano agora são SEMPRE concretos (comando/ferramenta citado —
ex.: `ps aux --sort=-%mem | head -15`), para o executor de 8B não ter
liberdade de divagar.

Testes T59–T60 reproduzem os casos reais (skill errada, contexto,
follow-up, retomada imperativa). Suíte: **60/60**.

## v3.5.0 — 🧠 mente sênior no orquestrador/revisor · 🛡 fim do bug "não recebo a resposta"

Dois pedidos do operador, tratados na raiz:

**🧠 Uma mente acima de adolescente — um sênior experiente.** Os prompts
do 🎯 orquestrador e do 🔍 revisor foram reescritos como um engenheiro de
sistemas SÊNIOR com 30 anos de estrada: calmo, direto, obcecado por
resultado certo na primeira tentativa:
- orquestrador: lê a INTENÇÃO real do pedido (não só o texto), escreve
  a task como uma ORDEM DE SERVIÇO precisa — objetivo com verbo de
  conclusão, passos curtos que um subordinado executa sem perguntar
  nada, critérios VERIFICÁVEIS — com exemplos firmados no prompt;
- executor: recebe a ordem de serviço + "padrão de qualidade" (completar
  na PRIMEIRA tentativa, trazer EVIDÊNCIA real, nunca pedir ao usuário
  para fazer);
- revisor: o veterano que ASSINA embaixo — checklist de cobrança em 4
  itens (cumprimento · evidência real · proibições · entrega) e aprova
  só se TODOS passarem. "O operador não pode receber retrabalho."

**🛡 Bug recorrente "não recebo a resposta do agente" — erradicado em
duas camadas:** (1) GARANTIDOR no servidor: se qualquer caminho terminar
o stream sem emitir `done`, o resultado final é entregue de qualquer
jeito; (2) GUI defensiva: a resposta final sempre vira bolha — mesmo se
nenhum token tiver sido streamado (done direto) — e quando o final difere
do texto streamado (selo 🔍 da revisão), a bolha é ATUALIZADA com o
conteúdo final. Regressão protegida pelo teste T57 (stub sem done →
garantidor entrega; todos os caminhos emitem exatamente 1 done).

Testes T57–T58. Suíte: **58/58**.

## v3.4.0 — ⌨️ comandos /na GUI · 🔬 por baixo dos panos · ✦ skills no pipeline · 🔒 aprovação de criação

Quatro pedidos do operador, implementados como features permanentes:

**⌨️ Comandos do terminal no chat da GUI (digite `/`):** menu com
autocompletar (setas/Tab) e os mesmos comandos do CLI — e um novo:
- `/goal <texto>` — define o OBJETIVO da sessão; o orquestrador leva em
  conta em cada task (persistido por sessão);
- `/tools` `/skills` `/tasks` `/memoria` `/reset` `/ajuda`.

**🔬 Por baixo dos panos:** botão "🔬 panos" no chat — as decisões do
orquestrador (plano JSON + resposta bruta do modelo), skills aplicadas,
prompt injetado no executor e veredito do revisor aparecem na conversa
em blocos expansíveis. Botão "🧾 fluxo" mostra o fluxo BRUTO completo
(todos os eventos, JSON linha a linha). Preferência fica salva.

**✦ Skills aplicadas automaticamente:** o orquestrador cruza a task com
as skills ATIVAS (aba Skills) por palavras-chave da descrição e injeta
as instruções da SKILL no executor (máx. 2, score mínimo) — com nota
"✦ skills aplicadas: …" para você ver quando aconteceu.

**🔒 Aprovação para tarefas de CRIAÇÃO:** o orquestrador classifica a
task (leitura × criação). Criação (criar/escrever/enviar/instalar…)
pausa ANTES de executar e mostra o plano: ✅ Aprovar · ✏️ Editar
(objetivo e passos) · ⛔ Cancelar. Depois da revisão, pausa de novo na
ENTREGA: o resultado vem EDITÁVEL — ✅ Entregar · 💾 Entregar editada ·
🔁 Refazer. Timeout de 5 min; desligável em Ajustes ("🔒 Aprovação em
tarefas de criação"). Tasks de leitura seguem direto (sem atrito).

Testes T54–T56: comandos (goal/tools/skills/tasks/memoria/ajuda),
seleção de skills por palavra-chave com leitura real do SKILL.md, e o
portão de aprovação PONTA A PONTA no stream real do chat (aprovar →
executar → aprovar entrega → done com selo; cancelar; editar).
Suíte: **56/56**.

## v3.3.0 — 🎯 Orquestrador + ⚡ Executor + 🔍 Revisor (pipeline de tasks)

Diretriz do operador: a conversa deve passar por um ORQUESTRADOR que
entende o que deve ser feito, cria uma TASK, a IA executa, e o resultado
é REVISADO antes de ser entregue.

**O pipeline (só no agente Hermes; Claude Code segue com seus guards):**

    mensagem ─► 🎯 ORQUESTRADOR (chamada rápida, JSON)
                  ├─ "responder"  ─► resposta direta (custo zero extra)
                  └─ "executar"   ─► task criada (registrada + visível)
                                      ─► ⚡ EXECUTOR (Agent de sempre:
                                         ferramentas reais, denylist)
                                      ─► 🔍 REVISOR (cumpriu o objetivo?)
                                           ├─ ok      ─► entrega com selo
                                           └─ refazer ─► re-executa com o
                                              problema apontado (máx. 2)

**Decisões de performance (modelo local ≤8B):** orquestrador e revisor
rodam em chamadas rápidas (num_predict 220/140, temperature 0, ~1-3 s);
conversa simples NÃO entra no pipeline; tentativas limitadas a 2 (nunca
loop infinito); prompts curtos e excertos truncados; em modo mock o
roteamento é heurístico determinístico (demo estável).

**Robustez:** qualquer falha de parse do orquestrador cai na heurística;
do revisor, em "ok" (a entrega nunca trava); o `done` da GUI agora sai
DEPOIS da revisão, com o selo 🔍 na mensagem final.

**GUI:** etapas do pipeline aparecem ao vivo no chat (🎯 task criada,
🔍 reprovou/refazendo, ✔ aprovada); interruptores em Ajustes
("🎯 Orquestrador" e "🔍 Revisor"); histórico de tasks em
`GET /api/orchestrator/tasks` (também em data/orchestrator_tasks.jsonl).

Testes T51–T53: plano/roteamento (JSON, prosa ao redor, lixo→heurística,
flag), vereditos do revisor (ok/refazer/lixo→ok/flag), e o pipeline
ponta a ponta no chat real — task criada, executada, aprovada com selo
no `done`, registrada; conversa comum não gera task. Suíte: **53/53**.

## v3.2.0 — 📱 GUI responsiva (celular/tablet) + instalável como app (PWA)

Diretriz do operador: a GUI deve se adaptar à tela do usuário — e a
aplicação will ganhar acesso mobile.

**Responsivo de verdade (zero build-step mantido — CSS e JS puros):**
- navegação vira **barra inferior fixa e rolável** no celular (alcançável
  com o polegar), com blur e área segura (notch) respeitada;
- chat com **viewport dinâmico (100dvh)** — o teclado do celular não
  esconde mais a caixa de mensagem;
- **inputs com 16px** → o iOS não dá zoom automático ao focar;
- alvos de toque ≥44px, sem hover-fantasma em telas de toque;
- grid de cards, auditoria, modais, toasts e notificações refluem para
  uma coluna; `prefers-reduced-motion` respeitado; tema claro adaptado.

**Instalável como app (PWA):** `manifest.webmanifest` + service worker +
ícones gerados em Python puro (PNG escrito com zlib/struct — sem Pillow).
No celular: "Adicionar à tela inicial" abre em modo standalone, como app.
O worker NUNCA cacheia `/api/*` (dados sempre ao vivo) e só age em
contexto seguro (HTTPS/localhost) — em LAN http ele fica em silêncio.

**Acesso do celular na prática:** no PC, `ip a` mostra o IP da rede; no
celular (mesmo Wi-Fi), abra `http://<ip-do-pc>:8080`. Para instalação
completa do PWA e uso fora de casa, coloque HTTPS na frente (proxy
reverso ou túnel) — documentado no docs.md.

Teste T50: viewport/marcos responsivos, manifest standalone, worker
(api nunca cacheada), ícones PNG válidos (192/512). Suíte: **50/50**.

## v3.1.3 — 🔎 E-mail somente leitura por padrão · 🗓 Agenda Google · 🌀 guard anti-loop

Diretriz do operador: o agente deve **VISUALIZAR** e-mails e agenda das duas
contas Google — sem enviar/redigir (por enquanto, o modelo local ainda não
está pronto para redigir e-mails sozinho).

**E-mail somente leitura POR PADRÃO:** toda conta (nova ou já configurada)
fica em modo visualização — listar, ler e buscar funcionam; o IMAP usa
EXAMINE (não marca mensagens como lidas); ENVIAR é recusado com instrução
clara. Liberação explícita, quando o operador decidir:
`hermes email modo <conta> envio` (volta com `... leitura`).

**Agenda Google Calendar (MCP `agenda_*`) — somente leitura por construção:**
escopo OAuth único `calendar.readonly`; o servidor só faz GET na API — não
existe código que crie, altere ou apague eventos. Ferramentas: `agenda_hoje`,
`agenda_listar`, `agenda_proximo`, `agenda_contas`. Conexão via device code
(`hermes agenda oauth`) com o 2FA do provedor — mesmo client_id do e-mail;
refresh_token no cofre de segredos (600, fora do workspace).

**Guard anti-loop no Claude Code:** quando o modelo local degenera repetindo
a mesma linha até estourar o limite de tokens (caso real: "Acessar
Configurações de Contas do Google:" ×30), o Hermes corta a repetição da
resposta final, avisa na GUI (nota) e registra no log de atividades.

Testes T47–T49: envio recusado → liberado → recusado de novo (cache do
servidor invalida por mtime); agenda ponta a ponta com API falsa (Bearer,
GET-only — POST conta como falha, cache de access_token); corte do loop com
a string real da degeneração. Suíte: **49/49**.

## v3.1.2 — 📧 e-mail com 2FA/OAuth (XOAUTH2 + device code)

Preocupação do operador: "a maioria dos e-mails tem 2FA — vai bloquear o
login". Resposta técnica em duas partes:

**1. 2FA ≠ bloqueio (Gmail & cia):** o caminho continua sendo a SENHA DE
APLICATIVO (existe exatamente para isso). O setup agora detecta o erro
"Gmail exige senha de app" no login e mostra o passo a passo na hora.

**2. Onde senha realmente morreu (Microsoft 365/Outlook/Hotmail):**
implementado **OAuth2 completo**:
- `hermes email oauth` (ou opção 'o' no setup): fluxo **device code** —
  o Hermes mostra um código, você abre o link no navegador e autoriza com
  o **2FA normal do provedor**; nenhuma senha passa pelo terminal;
- **XOAUTH2** (padrão SASL) no IMAP e SMTP, no servidor MCP e no setup;
- **refresh automático**: access token renovado via refresh_token quando
  expira (em cache por chamada — sem regravar o arquivo de segredos);
- diagnóstico por provedor: falha de login no domínio Microsoft →
  "rode hermes email oauth"; Gmail sem app password → instruções exatas.

Tabela de provedores no docs.md (Gmail/Workspace, Microsoft 365, Yahoo,
iCloud, Proton Bridge, servidor próprio). Requer um client_id próprio
(uma vez) para o fluxo OAuth — instruções no setup e no docs.

Testes T44–T46: XOAUTH2 ponta a ponta pelo MCP real (IMAP/SMTP falsos
com AUTHENTICATE/AUTH XOAUTH2 + token endpoint falso; sem senha em texto
nenhuma), device code (código mostrado, pending, denied), refresh com
cache, e hints de diagnóstico. Suíte: **46/46**.

## v3.1.1 — 📡 Log ao vivo mostra TODA a atividade (bug real)

Problema relatado pelo operador: o "Log ao vivo" do Painel não mostrava
as atividades. Causa raiz: o painel faz tail de `data/logs/agent.log`,
mas **somente o daemon escrevia nele** — tudo que acontecia no processo
do `hermes server` (chat, execuções de ferramentas, tarefas agendadas,
MCP, Ollama, ajustes, backups) ficava invisível.

Correção: módulo `hermes/activity.py` — caneta única, thread-safe, com
rotação em 5 MB (mantém `agent.log.1`). Agora o log registra:
- 💬 chat: pergunta recebida + resposta concluída (agente, tempo, tokens,
  passos) e erros de geração;
- ⚙ cada ferramenta executada (nome, argumento principal, ok/erro, ms);
- ⏰ tarefas agendadas: iniciada e concluída (status, duração);
- 🔌 MCP: servidor ativo (nº de ferramentas), falha ao subir, reinício
  pelo supervisor 🩺;
- 🎛 painel: agente/ollama ligado/desligado, configuração alterada
  (chaves), backup restaurado, servidor MCP adicionado;
- 🔧 ferramentas do Claude Code (Bash/Read/Edit dele).

O histórico continua disponível em `/api/logs` (limpar em 🗑) e cada
execução segue na trilha estruturada da aba 🧾 Auditoria.
Testes: T42 (chat+ferramenta+tarefa+ajustes+ação aparecem no log) e
T43 (rotação por tamanho). Suíte: **43/43**.

## v3.1.0 — 📧 MCP de e-mail (leitura + envio, credenciais à prova de vazamento)

Servidor MCP `mcp-servers/email_server.py` (stdlib pura: imaplib/smtplib)
com 5 ferramentas para o agente: `email_list`, `email_read`, `email_search`,
`email_send`, `email_accounts` — mapeadas como `mcp_email_*`.

**Arquitetura anti-vazamento das credenciais** (requisito do operador):
- senhas em `<data>/secrets/email.json` — permissão **600** (diretório 700),
  FORA do workspace do agente (sandbox de arquivos já bloqueava leitura);
- **denylist nova**: `run_command` que tente acessar `secrets/`/`email.json`
  é bloqueado com aviso apontando para as ferramentas `mcp_email_*`;
- as credenciais **nunca passam pelo modelo**: o servidor MCP lê o arquivo
  direto (caminho via env `HERMES_EMAIL_SECRETS`); nada em config.yaml,
  logs, auditoria ou histórico — só o CONTEÚDO dos e-mails trafega;
- teste T41 prova: cat/grep no arquivo → bloqueado; read_file → sandbox;
  senha ausente do config.yaml; arquivo 600.

**Setup em 1 comando**: `hermes email setup` (interativo, testa e descobre
os servidores IMAP/SMTP sozinho — Gmail usa app password de 16 caracteres;
auto-registra o servidor MCP no config). `hermes email test` valida logins;
`hermes email status` mostra o resumo. Envio fica desativado se o SMTP não
validar (conta em modo somente leitura).

**Testes T40**: E2E contra IMAP/SMTP **falsos com protocolo real** (login,
SEARCH, FETCH com literal, AUTH PLAIN): listar 3 mensagens, buscar "prazo",
ler mensagem com assunto UTF-8 codificado, enviar (chega ao SMTP) — tudo
via o conector MCP REAL do Hermes (subprocesso stdio). Suíte: **41/41**.

## v3.0.2 — guard de execução (fim do "escreve o comando e não roda")

Incidente real: o agente 🔌 Claude Code respondia pedidos como "mostre
informações do sistema" ESCREVENDO os comandos em blocos de código (ou
dizendo "você pode verificar com lscpu") — sem nunca chamar a ferramenta
Bash — e às vezes colava saídas INVENTADAS. O usuário tinha que executar
e colar de volta. Correção em 3 camadas:

1. **Diretiva endurecida**: "escrever comando em bloco de código é ERRO;
   quem executa é VOCÊ; resposta sem execução = resposta errada".
2. **Guard de execução**: se a resposta terminar com ZERO chamadas de
   ferramenta E contiver blocos ```bash (ou "pedidos" ao usuário tipo
   "execute o comando", "verifique você"), o Hermes **repete a chamada
   com ordem direta** de usar a ferramenta Bash — o modelo quase sempre
   obedece na 2ª vez.
3. **Último recurso**: se ainda assim não executar, o Hermes **executa os
   comandos ele mesmo** (denylist + timeout + sandbox + auditoria, fonte
   "guard-claude") e entrega a saída REAL — o usuário nunca fica na mão.
   Blocos que não parecem comandos (ex.: saída alucinada colada como
   `PRETTY_NAME="..."`) e comandos com sudo são pulados com aviso.

Testes: T38 (modelo recupera na 2ª chamada e entrega saída real) e
T39 (teimoso: Hermes executa no lugar, saída real + auditoria + bloco
alucinado pulado). Suíte: 39/39.

## v3.0.1 — revisão crítica (segurança + correções)

Revisão de código pós-v3.0.0 com correções encontradas pela própria suíte:

- 🔴 **Anti-CSRF**: qualquer site na web podia dirigir o agente de quem
  roda a GUI sem token (CORS `*` + POST liberado — o navegador da vítima
  fazia o pedido). Agora POSTs cross-origin (Origin ≠ Host) sem token
  válido são **rejeitados com 403**. A GUI legítima (same-origin), a
  preview em iframe sandbox (Origin null), curl e webhooks com token
  continuam funcionando.
- 🟠 **Bug**: criar tarefa com gatilho webhook/watch sem campo "when"
  retornava 400 indevido — gatilhos não dependem de horário.
- 🟠 **Cache do prompt**: a data/hora estava DENTRO do texto cacheado (e
  da chave) — o prefixo estável durava 1 minuto. Agora a hora vai no
  FINAL do prompt, fora do cache: prefixo estável de verdade.
- 🟡 **Load relativo**: "só quando ociosa" comparava load com 2.0 fixo —
  agora é relativo ao nº de núcleos (load 3 num 16-core = ocioso).
- 🟡 waitress: 8 → 16 threads (SSE de log/chat + tarefas simultâneas).
- Testes: suíte ampliada 33 → **37 casos** (anti-CSRF, webhook sem when,
  estabilidade do prefixo, load por núcleo).

## v3.0.0 — a grande atualização (confiança · poder · inteligência)

Baseada no estudo técnico completo do código (19 módulos, ~7.2k linhas).
Todas as melhorias respeitam a filosofia: local-first, modelos ≤8B,
zero build-step, tarefas sem barreiras.

**Controle (confiança)**
- **Backups automáticos**: toda gravação do agente salva a versão anterior
  em `data/backups/` (rotativo, 20/arquivo). Restauração pela GUI
  (Ferramentas → Backups) ou pela nova ferramenta `backups` do agente.
- **Auditoria**: TODA ação (nativa, MCP, Claude Code, GUI) vai para
  `data/audit/audit-YYYY-MM.jsonl` com args, status e duração. Nova aba
  🧾 Auditoria com filtros por agente/ferramenta.
- **Orçamento de ferramentas**: teto de 12 chamadas por resposta
  (`max_tool_calls`) — cadeias infinitas com ferramentas diferentes são
  cortadas e o parcial é entregue.
- Restauração de backup bloqueada fora do workspace (sandbox).

**Automação (poder)**
- **Histórico de execuções** por tarefa (últimas 20, na GUI).
- **Retry com atraso**: "se falhar, tentar de novo" (0–3×, atraso
  configurável) — falha de execução agora conta como falha (bug corrigido:
  antes retornava sempre "ok").
- **Gatilhos**: 🌐 webhook (`POST /api/hooks/<id>`) e 📂 watcher
  ("quando chegar *.pdf em ~/Downloads → faça X").
- **Notificações** 🔔 na GUI: falhas de tarefas e reinícios de MCP.
- **Receitas prontas** 🍳: 6 automações úteis com ativação de 1 clique.
- **Só quando ocioso**: tarefa pode esperar a máquina livrar (loadavg).

**Performance**
- **Cache do prompt de sistema** (invalida por memória/skills/config/minuto).
- **Ferramentas em paralelo** (até 3 simultâneas no mesmo passo).
- **Servidor de produção**: waitress no lugar do dev server do Flask.
- **Painel de desempenho**: tok/s médio + sparkline das últimas 20 respostas.
- **Memória por relevância**: com muitos fatos, injeta os top-k relevantes
  à pergunta em vez de truncar.

**Servers MCP**
- **Supervisor de saúde**: servidor morto renasce sozinho (backoff
  60s→10min) + notificação.
- **Painel**: adicionar servidor pela GUI (sem editar YAML) e testar
  ferramenta via API (`/api/mcp/add`, `/api/mcp/test`).
- **Seleção dinâmica**: com muitas ferramentas MCP, só as 8 mais relevantes
  à pergunta entram no payload (menos delírio de modelo pequeno).

**Design**
- **Markdown rico** nas respostas: títulos, listas, citações, links e
  blocos de código com botão **copiar**.
- **Tema claro/escuro** (🌙/☀ no cabeçalho, persistente).
- **Visão ao vivo** com tempo por passo e tok/s ao vivo.
- **Doctor** 🩺: wizard na primeira execução + `hermes doctor` estendido
  (Ollama, modelo, voz, Claude Code, segurança).
- **Exportar conversa** em .md/.json (⬇ no Chat).

**Config novas**: `max_tool_calls` 12 · `backups_keep` 20 ·
`mcp_autorestart` true · `tool_selector` true · `memory_top_k` 8.

Testes: suíte formal em **tests/run_all.py** — 33 casos cobrindo módulos v3.0
(backups, auditoria, métricas, notificações, memória, seletor, orçamento,
paralelismo, cache), scheduler (histórico, retry, watcher, webhook,
ociosidade), supervisor MCP, 8 endpoints novos, CLI e REGRESSÕES das v2.x
(JSON solto, anti-loop, modo leve do Claude Code com CLIs falsas,
keep_alive, denylist). Rode com: `./.venv/bin/python tests/run_all.py`
(cada caso usa diretório temporário próprio — nada toca em ~/.hermes).

## v2.2.8 — Claude Code autodiagnóstico + fallback de CLI antiga

- Toda resposta do agente 🔌 Claude Code agora termina com um rodapé
  "*🔌 Claude Code · modo · versão da CLI*" (e emite nota na visão ao vivo)
  — o print seguinte mostra exatamente o que está valendo na máquina.
- Medido com a CLI real: modo leve = **3 ferramentas / 3,5k chars** contra
  **21 ferramentas / 58k chars** do modo padrão (~16× menor). O texto
  "workflow" que o modelo ecoava vinha literalmente do payload padrão.
- CLI antiga sem `--bare`: cai automaticamente para o modo completo com
  aviso "atualize com: claude update" — em vez de erro seco.
- Diretiva do modo leve reforçada: proibido escrever JSON Schema/XML ou
  exemplos de chamada; dados do sistema via Bash com saída real.

## v2.2.7 — guard anti-loop no agente

- Modelos pequenos às vezes repetiam a mesma fala E a mesma chamada de
  ferramenta em loop, queimando o limite de tokens (saída cortada no meio).
  Agora: chamada idêntica à do passo anterior **não é re-executada** — o
  modelo recebe um aviso direto para responder ao usuário; se repetir de
  novo, o agente encerra e entrega o resultado já obtido.
- Botão "⚡ modo rápido" agora usa **768 tokens** (512 cortava respostas
  com ferramentas no meio).

## v2.2.6 — Claude Code em modo leve (fim do "fora de si")

- Via Ollama, a CLI `claude` agora roda com **`--bare` + diretiva curta em
  português + ferramentas essenciais (Bash/Read/Write/Edit/Glob/Grep) +
  limite de 4 turnos**. Medido com a CLI real: o prompt de sistema enviado ao
  modelo cai de **5.780 para ~500 caracteres (11× menor)** — era isso que
  fazia modelos 7B–8B delirarem com "templates de workflow".
- Validação: E2E completo contra a CLI real (v2.1.301) com API Anthropic
  simulada — eventos step/token/done e resposta final extraídos corretamente.
- Recomendação mantida: `qwen2.5-coder:7b` no campo "modelo do Claude Code".

## v2.2.5 — fim do "JSON solto" (modelos pequenos)

- **Modelo escreveu a chamada de ferramenta como texto e inventou os dados?**
  Nunca mais: o agente agora intercepta JSON de chamada SEM cercas de código
  (caso típico de modelos 3B), valida o nome contra as ferramentas reais e
  EXECUTA a ferramenta de verdade — a resposta sai com os dados reais da
  máquina, não os alucinados pelo modelo.
- Prompt reforçado: "NUNCA simule ou invente a saída de uma ferramenta".
- Agente 🔌 Claude Code agora reporta o passo e as estatísticas contam tokens
  por bloco (estimativa honesta em vez de "1 token").

## v2.2.4 — prompt enxuto + indicador de modo real

- **Painel mostra o modo**: "✔ modo real (Ollama)" ou "⚠ MODO DEMO (IA
  simulada)" ao lado da versão — impossível ficar em dúvida.
- **Prompt ~35% menor** (menos tempo de processamento por mensagem, o tal
  "prefill" que domina em CPU): catálogo de skills compacto (descrições de 1
  linha), descrições das ferramentas web/lembrar encurtadas e teto da memória
  no prompt 4000→2000 caracteres.
- Reminder: demo NÃO vem no zip — o modo demo só liga com HERMES_MOCK=1 ou
  --mock, e o server imprime o banner gigante quando isso acontece.

## v2.2.3 — diagnóstico de velocidade na GUI

- O badge do chat agora mostra **tok/s** (tokens por segundo) de cada resposta
  — abaixo de ~5 tok/s o modelo está pesado para a máquina.
- Botão **"⚡ aplicar modo rápido"** em ⚙ Ajustes: num_predict 512 + num_ctx
  4096 + keep_alive 1h em um clique.
- docs.md: troubleshooting "respostas >100s" com o passo a passo de diagnóstico
  (`ollama ps` durante a resposta, tok/s, GPU, swap).

## v2.2.2 — Claude Code: fallback de modelo local

- No agente 🔌 Claude Code via Ollama, deixar o modelo vazio agora usa **o
  mesmo modelo do agente Hermes** em vez do padrão da nuvem (`claude-opus-*`,
  que não existe no Ollama e gerava "There's an issue with the selected
  model"). Dica de campo e troubleshooting atualizados.

## v2.2.1 — respostas mais rápidas (keep_alive + num_predict)

- **keep_alive** (padrão `30m`): todo pedido ao Ollama agora pede para manter
  o modelo carregado — acabou o "primeiro token demorado" depois de uma
  pausa. Ajustável em ⚙ Ajustes (`1h`, `-1` = sempre).
- **num_predict** (padrão `0` = sem limite): limite opcional de tokens por
  resposta (512–768 = respostas mais rápidas e diretas), também em Ajustes.
- docs.md ganhou a seção **"⚡ Deixando as respostas mais rápidas"** com as 6
  alavancas (modelo 3B no dia a dia, num_ctx, GPU, flash attention etc.).

## v2.2.0 — ditado por voz (🎤 Whisper local)

- **Botão 🎤 no chat**: grave sua voz pelo microfone e o **Whisper local**
  (faster-whisper, CPU, int8 — sem PyTorch e sem API paga) transcreve; o texto
  vai para a mensagem e (padrão) é **enviado sozinho** — o agente interpreta
  e executa o que você ditou.
- Opcional e fácil de ativar: `pip install faster-whisper "av<19"` (o PyAV 19
  quebra a API do faster-whisper); o modelo (`base`,
  ≈140 MB) baixa só no primeiro uso e fica em cache.
- Novos endpoints `GET /api/stt/status` e `POST /api/stt` (multipart `audio`).
- Ajustes novos: modelo de voz (tiny→large-v3), idioma do ditado (padrão `pt`)
  e "enviar automaticamente após ditar".

## v2.1.0 — acesso à web (🌐 pesquisa e leitura de páginas)

- Novas ferramentas nativas do agente: **`web_search`** (busca no DuckDuckGo,
  sem chave de API — títulos, endereços e resumos) e **`web_fetch`** (abre
  qualquer página http(s) e devolve o texto limpo, até 2 MB). O modelo é
  instruído a citar as fontes.
- Funciona no **chat**, nas **tarefas agendadas** (ex.: "pesquise as notícias
  de tecnologia e resuma" às 08:00) e manualmente na nova seção **🌐 Web** da
  aba 🛠 Ferramentas.
- Interruptor de segurança: **⚙ Ajustes → "🌐 acesso à web"**
  (`web_access`, padrão ligado) — desligado, as ferramentas somem do agente,
  da GUI e da API.
- Prompt de sistema atualizado (seção de capacidades condicional) com diretiva
  forte: pesquisar SEMPRE que a resposta depender de informação atual, nunca
  inventar dados e citar as fontes.
- Nova skill **pesquisa-web**: fluxo de pesquisa (busca → escolher fontes →
  ler → sintetizar com fontes), memorizar descobertas úteis (`lembrar`) e
  rotina de **pesquisa agendada/monitoramento** com relatórios diários em
  `relatorios/YYYY-MM-DD-<tema>.md` destacando "o que mudou".

## v2.0.2 — catálogo com curadoria "leves ≤7B" (máquinas com ~10 GB de RAM)

- Curadoria da aba Ollama ganhou um bloco de modelos leves verificados na
  biblioteca oficial, com tamanho de download em cada descrição:
  `llama3.2:3b/1b`, `deepseek-r1:7b/1.5b`, `qwen2.5-coder:7b/1.5b`,
  `phi3:3.8b`, `phi4-mini:3.8b` e `granite4.2:3b` — download com 1 clique.
- Correções de nomes (tags verificadas na ollama.com): `phi3:4b` não existe
  (é `phi3:3.8b`) e `qwen3-coder` não tem versão 7B (menor: 30b — pesada
  p/ 10 GB; alternativa ≤7B: `qwen2.5-coder:7b`).

## v2.0.1 — Claude Code integrado ao Ollama por padrão

- O Claude Code (2º agente) agora é lançado **apontado para o mesmo Ollama**
  do Hermes: as variáveis `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` /
  `ANTHROPIC_API_KEY=""` são aplicadas automaticamente — não precisa exportar
  nada no terminal (antes eram obrigatórias).
- Novas configurações: `claude_use_ollama` (padrão ligado) e `claude_model`
  (modelo do Claude Code, ex.: `qwen3-coder`) — na aba ⚙ Ajustes e no
  `config.yaml`.
- Dica de instalação atualizada (`claude.ai/install.sh` + `ollama launch
  claude`) e `docs.md` revisado para o fluxo via Ollama.

## v2.0.0 — ferramentas manuais, Claude Code, catálogo de LMMs e conversas completas

- **🛠 Aba Ferramentas**: as funções padrão do agente direto na GUI — terminal
  rápido (mesma segurança/denylist do agente), navegador de arquivos do
  workspace (listar/ler/gravar), diagnóstico do sistema e o catálogo de todas
  as funções (nativas + conectores MCP).
- **🔌 Claude Code como segundo agente**: seletor no chat — fale com o
  **Hermes (Ollama)** ou com o **Claude Code** (CLI `claude` da sua máquina,
  com as funções padrão dele: bash, arquivos, busca…). Respostas ficam no
  histórico com etiqueta "🔌 Claude Code". As tarefas agendadas também podem
  escolher o agente.
- **📚 Catálogo de modelos (LMMs)**: busca na biblioteca oficial (ollama.com)
  + curadoria popular em português, com descrição, capacidades e tamanhos —
  baixe com 1 clique. Download agora é **cancelável** (⏹ cancelar).
- **💬 Conversas completas**: botão **＋ nova** (a anterior continua salva),
  busca em **todas** as conversas (🔍 dentro de 🕘 conversas) e abrir/continuar
  qualquer conversa pelo resultado da busca.

## v1.5.0 — execução ao vivo + memória persistente

- **👁 Execução ao vivo**: acompanhe uma tarefa agendada trabalhando em tempo
  real — cada passo, comando executado e a resposta sendo gerada, num console
  que abre sozinho ao clicar em "▶ agora" (ou no botão "👁 ao vivo" enquanto
  roda). Buffer da última execução fica disponível para reabrir.
- **🧠/📔 Memória persistente**: o agente agora lembra de você entre conversas
  e reinícios. Fatos e preferências ficam em `data/memory.json`, são injetados
  no prompt de TODAS as conversas e tarefas agendadas, e o agente grava/apaga
  sozinho com as novas ferramentas `lembrar` e `esquecer`.
- **GUI**: nova aba "📔 Memória" (adicionar, editar ✏, apagar 🗑) e modal de
  execução ao vivo com cronômetro e contagem de tokens.
- **API**: `GET/POST /api/memory`, `POST /api/memory/update|delete`,
  `GET /api/schedules/live?id=`.

## v1.4.0 — tarefas agendadas (⏰)

- **Agendador embutido no `hermes server`** (verifica a cada 15s): tarefas
  disparadas em momentos específicos, sem ninguém no teclado.
- **Agendamento em português**: "diário 07:30", "todo dia às 8", "seg,qua
  14:00", "amanhã 09:00", "uma vez 2026-10-05 08:00", "a cada 30m".
- **Execução desassistida**: sem confirmação interativa (nada bloqueia a
  tarefa agendada); a denylist de segurança segue ativa (rm -rf /, mkfs,
  shutdown… continuam bloqueados).
- **GUI**: nova seção "⏰ Tarefas agendadas" na aba Tarefas — criar, ▶ rodar
  agora, ⏸ pausar/ativar, 🗑 remover, próxima execução e histórico (nº de
  execuções, última com duração). Resultados completos aparecem na fila.
- **CLI**: `hermes schedule list|add|del|run`.
- Auto-liga o Ollama na execução quando "ligar automaticamente" está ativo.
- Nova skill **resumo-inbox**: relatórios de e-mail (Gmail MCP oficial do
  Google) e Google Classroom (via e-mails de notificação ou API).

## v1.3.1 — tempo de geração da resposta

- **⏱ badge de tempo** sob cada resposta: `⏱ 4.2s · 87 tokens · 2 passo(s)`
  (medido no servidor; fallback com cronômetro do navegador).
- **Cronômetro ao vivo** no "A trabalhar… (7s)" enquanto a IA gera.
- O tempo fica **gravado na conversa** — conversas reabertas do histórico
  mostram o tempo de cada resposta.

## v1.3.0 — memória de conversas (histórico + zerar + restauração)

- **Conversas persistidas em sessões** (`conversations/sessions/`): toda troca
  é gravada no servidor — a mensagem do usuário é salva ANTES da geração,
  então nada se perde nem se a conexão cair.
- **Restauração automática**: recarregar a GUI (F5) traz de volta a última
  conversa aberta, exatamente como estava. Trocar de aba nunca interrompeu
  nada; agora recarregar tampouco.
- **🗑 zerar**: inicia uma conversa nova na hora — a anterior continua salva.
- **🕘 conversas**: histórico completo com título, data e nº de mensagens;
  abrir restaura o contexto (o agente "lembra" da conversa) e dá para apagar
  conversas individuais.
- IDs de sessão validados (sem path traversal) e gravação atômica.

## v1.2.0 — espera robusta + "A trabalhar…"

### ⏳ Loading na GUI
- Indicador animado **"A trabalhar…"** assim que a mensagem é enviada, com
  contexto ao vivo: *(passo N)*, *(executando ferramenta)* — some no primeiro
  token da IA.
- Novo botão **⏹ parar** durante a geração (cancela no servidor; o texto
  parcial já recebido é preservado).

### 🔗 Espera robusta da resposta (o lado "promise" do fluxo)
- Geração roda em thread com **evento de cancelamento** propagado até o
  streaming do Ollama — abortar a página/parar não deixa thread órfã.
- **Keepalive a cada 5s** (`ping`) enquanto a IA pensa (ex.: modelo carregando
  na memória): a conexão não cai por inatividade e o front nunca fica preso.
- **Retry automático** (2x com backoff) para falhas transitórias de conexão.
- Queda no meio do stream vira erro claro ("a conexão caiu — texto pode estar
  incompleto"), sem travar o chat.
- Watchdog: se a thread morre, o stream termina ordenadamente em vez de pendurar.
- Conversa (mesmo parcial) sempre registrada em `conversations/`.

## v1.1.1 — blindagem PyYAML

- **Detecta PyYAML quebrado** (pacote incompleto, típico de venv em disco NTFS):
  o `hermes doctor` e o auto-diagnóstico do `hermes server` mostram o problema
  e o comando exato de correção (`pip install --force-reinstall PyYAML`).
- `/api/status` e o carregamento de skills **não travam mais** com yaml quebrado
  (frontmatter inválido vira skill sem metadados, em vez de erro 500).
- Salvar configuração com yaml quebrado retorna mensagem clara (não mais 500).

## v1.1.0 — "Visão completa" (a versão da demo online)

### 🧠 Nova aba Ollama na GUI (o "app desktop" do Linux)
- Processo do servidor: **PID, tempo ligado, memória RSS**, quem gerencia
  (systemd / Hermes / externo) e **modelos carregados em memória/VRAM** (`/api/ps`).
- Botões ▶ Ligar / ■ Desligar / ⟳ Reiniciar / ⚙ **iniciar com o sistema** (systemd).
- **Gerenciador de modelos**: listar (tamanho/data), definir em uso, **baixar com
  barra de progresso** e remover do disco — tudo pela GUI.
- **Conexão**: editar o endereço da API pela GUI + opção **"ligar o Ollama
  automaticamente"** (o agente sobe o servidor sozinho quando precisar).
- **🔍 testar conexão**: diagnóstico passo a passo (instalação → serviço/API →
  modelos → modelo configurado → **geração de teste real com latência**).

### 🩺 Diagnóstico
- Novo comando **`hermes doctor`** — mesma validação no terminal.
- **Auto-diagnóstico ao iniciar `hermes server`**: falhas aparecem na tela com o
  comando de correção, antes mesmo de abrir a GUI.

### 🔌 Conectores MCP (Model Context Protocol)
- Cliente MCP completo: transportes **stdio** e **Streamable HTTP**.
- Ferramentas dos servidores aparecem para o modelo como `mcp_<servidor>_<ferramenta>`.
- **Conector Figma** (3 modos): API REST (`figma-developer-mcp`), Dev Mode
  (`http://127.0.0.1:3845/mcp`) e servidor demo incluído (`mcp-servers/`).
- Cartão **Servidores MCP** no Painel: ativar/reiniciar e ferramentas por servidor.

### ✦ Skills (formato aberto SKILL.md)
- Loader com *progressive disclosure* (catálogo no prompt, conteúdo sob demanda).
- Aba **Skills** na GUI: listar, ver SKILL.md, habilitar/desabilitar e
  **instalar direto do GitHub** (ex.: `anthropics/skills` → `skills/pdf`).
- Skills incluídas: `figma-design`, `ui-design-system`, `app-prototyping`.

### 🛡 Validações e correções
- Nome de modelo **validado ao salvar** (formato `nome:tag`); espaços e valores
  vazios são descartados automaticamente.
- Erro `invalid model name` agora responde com **instruções + modelos instalados**.
- Endereço da API (`ollama_url`) validado ao salvar.
- Servidores MCP com token placeholder não travam mais o chat.
- CORS corrigido na API (GUI em iframes/previews).

## v1.0.0 — versão inicial
- Agente Linux com Ollama (modelo Hermes), ferramentas (shell, arquivos, diagnóstico),
- daemon com fila de tarefas, CLI completa, GUI web com ligar/desligar, log ao vivo
  (SSE), chat em streaming e ajustes.
