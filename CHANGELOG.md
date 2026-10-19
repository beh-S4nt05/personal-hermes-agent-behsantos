# Changelog

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
