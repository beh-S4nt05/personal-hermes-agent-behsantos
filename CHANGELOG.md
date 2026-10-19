# Changelog

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
