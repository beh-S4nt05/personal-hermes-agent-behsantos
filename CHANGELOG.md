# Changelog

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
