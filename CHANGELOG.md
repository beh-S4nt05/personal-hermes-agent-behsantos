# Changelog

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
