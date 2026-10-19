# ◈ Hermes Agent

**Agente Linux via terminal com Ollama (modelo Hermes) + GUI web para controle e
gerenciamento de ligado/desligado.**

O Hermes é um agente local que conversa, diagnostica e opera sua máquina Linux
executando comandos shell, lendo/gravando arquivos e inspecionando o sistema —
com o cérebro rodando no **Ollama** com o modelo **Hermes** (Nous Research),
100% local, sem nuvem.

A **GUI web** permite ligar/desligar o agente e o servidor Ollama com um clique,
acompanhar o log ao vivo, conversar com o agente, enfileirar tarefas e ajustar
a configuração.

```
                        ┌─────────────────────────────┐
   navegador ──────────►│  GUI web (Flask)  :8080     │
   (qualrem aparelho)   │  ▸ liga/desliga agentes     │
                        │  ▸ log ao vivo · chat       │
                        │  ▸ fila de tarefas · ajustes│
                        └──────────┬──────────────────┘
                                   │ gerencia (spawn/signals)
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
   ┌────────────────────┐ ┌──────────────────┐ ┌─────────────────┐
   │ agent daemon       │ │ CLI terminal     │ │ Ollama          │
   │ ▸ fila de tarefas  │ │ hermes chat/run  │ │ ollama serve    │
   │ ▸ heartbeat+log    │ │ hermes agent …   │ │ modelo: hermes3 │
   └─────────┬──────────┘ └────────┬─────────┘ └────────▲────────┘
             │      ferramentas (bash, arquivos, diagnóstico)
             └──────────────► Linux ◄────────────────────┘
```

---

## ⚡ Início rápido

```bash
cd hermes-agent
chmod +x install.sh
./install.sh                       # instala Ollama + modelo hermes3:8b + CLI

hermes status                      # conferir tudo
hermes server                      # abrir a GUI em http://localhost:8080
```

Acesso de outros aparelhos na rede (**sempre com senha!**):

```bash
hermes server --host 0.0.0.0 --port 8080 --token minha-senha-segura
```

Para instalar como serviço que sobe junto do sistema:

```bash
./install.sh --with-systemd        # hermes-server + hermes-agent no systemd
```

### Requisitos

| Item | Valor |
|---|---|
| SO | Linux (testado em Debian/Ubuntu; usa systemd quando disponível) |
| Python | 3.9+ |
| RAM | 8 GB (`hermes3:3b`) · 12 GB+ (`hermes3:8b`) · 64 GB+ (`hermes3:70b`) |
| Disco | ~5 GB (modelo 8b) + 1 GB (Hermes) |

### Instalação manual (sem install.sh)

```bash
# 1. Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull hermes3:8b

# 2. Hermes Agent
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# 3. Use
hermes server
```

---

## 🖥 CLI (terminal)

| Comando | O que faz |
|---|---|
| `hermes chat` | chat interativo com o agente no terminal |
| `hermes run "tarefa"` | executa uma tarefa única (ex.: `hermes run "mostre uso de disco"`) |
| `hermes server` | sobe a GUI web (`--host --port --token`) |
| `hermes daemon` | roda o daemon do agente em primeiro plano |
| `hermes status` | status do agente + Ollama |
| `hermes agent start\|stop\|restart\|status` | **liga/desliga** o agente |
| `hermes ollama start\|stop\|status` | **liga/desliga** o servidor Ollama |
| `hermes ollama pull [modelo]` | baixa um modelo |
| `hermes models` | lista modelos locais |
| `hermes tasks` | fila de tarefas e resultados |
| `hermes config show\|set\|edit` | configuração |

Flags globais: `--data-dir DIR` (diretório de dados, padrão `~/.hermes`) e
`--mock` (modo demonstração com Ollama simulado).

## 🌐 GUI web

Abra `http://localhost:8080` (ou `host:porta` que você escolheu).

- **▤ Painel** — cartões do **Agente** e do **Ollama** com estado em tempo real,
  botões ▶ Ligar / ■ Desligar / ⟳ Reiniciar, e **log ao vivo** (SSE).
- **◈ Chat** — converse com o agente; as chamadas de ferramenta aparecem na
  hora (🔧 comando, argumentos, saída) antes da resposta final.
- **☑ Tarefas** — enfileira tarefas para o daemon executar em sequência
  (funciona até com o chat fechado; histórico com resultados).
- **⚙ Ajustes** — troca de modelo, prompt de sistema, limites, sandbox e token
  de acesso, salvos em `~/.hermes/config.yaml`.

## 🔌 API REST (usada pela GUI)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/status` | status consolidado (agente, Ollama, config) |
| POST | `/api/agent/start·stop·restart` | liga/desliga/reinicia o agente |
| POST | `/api/ollama/start·stop` | liga/desliga o Ollama |
| GET | `/api/logs?lines=300` | últimas linhas do log |
| GET | `/api/logs/stream` | log ao vivo (SSE) |
| POST | `/api/chat` | conversa (stream NDJSON de eventos) |
| GET/POST | `/api/tasks` (+`/clear`) | fila de tarefas |
| GET/POST | `/api/settings` | configuração |

Autenticação (quando houver token): header `X-Hermes-Token: <token>` ou
`?token=<token>`.

Exemplo:

```bash
curl -s localhost:8080/api/agent/start -X POST | jq
curl -N localhost:8080/api/logs/stream          # log ao vivo no terminal
```

## ⏰ Tarefas agendadas

Deixe pedidos para executarem sozinhos em horários específicos — o
agendador roda **dentro do `hermes server`** (mantenha a GUI aberta):

```bash
hermes schedule add "resuma meus e-mails e as atividades do classroom" "diário 07:30"
hermes schedule add "relatório de uso de disco" "seg,sex 18:00"
hermes schedule add "limpeza de backups antigos" "domingo 03:00"
hermes schedule list
```

Ou pela GUI → aba **Tarefas → ⏰ Tarefas agendadas**. Formatos aceitos:
`diário 07:30` · `todo dia às 8` · `seg,qua 14:00` · `amanhã 09:00` ·
`uma vez 2026-10-05 08:00` · `a cada 30m`.

As tarefas agendadas rodam **sem confirmação interativa** (nada as barra),
mas a denylist de segurança permanece: comandos destrutivos continuam
bloqueados. Resultados ficam no histórico da aba Tarefas.

**E-mail/Classroom**: adicione o conector Gmail (MCP oficial do Google) no
`config.yaml` e a skill `resumo-inbox` guia o agente no relatório diário:

```yaml
mcp_servers:
  - name: gmail
    url: https://gmailmcp.googleapis.com/mcp/v1   # requer OAuth (Google Cloud)
```

## 🛠 Ferramentas do agente direto na GUI

A aba **Ferramentas** dá acesso manual às funções padrão dos agentes:
terminal rápido (com a mesma denylist de segurança), arquivos do workspace
(listar/ler/gravar), diagnóstico da máquina e o catálogo de funções
(nativas + MCP). Use sem passar pelo chat.

## 🔌 Dois agentes: Hermes e Claude Code

No chat, o seletor no topo escolhe quem responde:

- **◈ Hermes (Ollama)** — o agente padrão deste projeto;
- **🔌 Claude Code** — a CLI `claude` da sua máquina, com as funções padrão
  do Claude (bash, leitura/edição de arquivos, busca…), **integrada ao
  Ollama automaticamente**: o Hermes lança o `claude` apontando para o mesmo
  servidor Ollama (variáveis `ANTHROPIC_*` aplicadas sozinhas — não é
  preciso exportar nada). Ajustável em ⚙ Ajustes (`claude_use_ollama`,
  `claude_model`).

  ```bash
  curl -fsSL https://claude.ai/install.sh | bash   # instala a CLI (uma vez)
  ollama launch claude --model llama3.2:3b         # teste via Ollama (use um modelo instalado!)
  # ⚠ sem --model ele tenta "claude-opus-…", que NÃO existe no Ollama
  ```

As tarefas agendadas também têm seletor de agente (Hermes ou Claude Code).

## 🎤 Ditar pelo microfone (Whisper local)

Botão **🎤** no chat: fale, pare a gravação e o **Whisper local** transcreve —
o texto é enviado ao agente, que interpreta e executa (dite "mostre informações
do sistema"). Requer uma vez:

```bash
./.venv/bin/pip install faster-whisper "av<19"   # modelo 'base' baixa no 1º uso
```

100% local, sem API. Modelo e idioma ajustáveis em ⚙ Ajustes; microfone exige
`http://127.0.0.1:8080` ou HTTPS.

## 🌐 Acesso à web

O **próprio agente** pesquisa na internet e lê páginas quando precisa — no
chat e nas tarefas agendadas (a skill `pesquisa-web` o guia em pesquisas,
monitoramentos e relatórios diários; uso manual opcional na aba
**Ferramentas → 🌐 Web**):

- `web_search`: busca no DuckDuckGo (sem chave de API) com títulos, endereços
  e resumos;
- `web_fetch`: abre qualquer endereço http(s) e devolve o texto limpo.

O modelo é instruído a **citar as fontes**. Para desligar (agente offline):
⚙ Ajustes → "🌐 acesso à web".

## 📚 Baixar modelos (LMMs) pela GUI

Na aba **Ollama → Modelos**, busque na biblioteca oficial (ollama.com) ou na
curadoria popular ("qwen", "visão", "código"…) e baixe com um clique; o
download mostra progresso e pode ser **cancelado**. Para tags específicas
(ex.: `qwen2.5:7b`), use o campo manual.

## 💬 Gerenciar conversas

- **＋ nova** — começa uma conversa limpa (a anterior continua salva);
- **🕘 conversas → 🔍** — busca dentro de TODAS as conversas salvas e abre a
  conversa que contém o texto;
- **abrir** — retoma qualquer conversa anterior exatamente de onde parou.

## 👁 Acompanhando uma tarefa ao vivo

Ao disparar uma tarefa agendada ("▶ agora" na aba Tarefas), a GUI abre um
console que mostra a execução em tempo real: passos, comandos rodados com
sucesso/erro, tokens sendo gerados e a resposta final. O mesmo botão "👁 ao
vivo" aparece enquanto a tarefa roda — útil para conferir o agente trabalhando
no horário agendado.

## 📔 Memória do agente

O Hermes lembra de você entre conversas, reinícios e tarefas agendadas.
Na prática:

- No chat, conte algo ("lembre que meu curso é X") e o agente salva com a
  ferramenta `lembrar` — ou esquece com `esquecer`;
- Na aba **📔 Memória** você vê, adiciona, edita e apaga fatos diretamente;
- Tudo o que está lá é usado em **qualquer** conversa e nas tarefas agendadas
  (ex.: o resumo diário de e-mail já sai do jeito que você prefere).

Os fatos ficam em `data/memory.json` — é só backupar esse arquivo junto com o
resto do `data/`.

## 🧠 Gerenciando o Ollama pela GUI (o "app desktop" do Linux)

A aba **Ollama** dá a visibilidade de processo que no Windows fica na bandeja:

- **Servidor**: estado, versão, **PID, tempo ligado, memória RSS**, quem gerencia
  (systemd/Hermes/externo), modelos carregados em memória/VRAM e botões
  ▶ Ligar / ■ Desligar / ⟳ Reiniciar / ⚙ **iniciar com o sistema** (systemd).
- **Conexão**: edite o endereço da API (`ollama_url`), ative o **arranjo
  automático** (o agente sobe o Ollama sozinho quando precisar) e rode o
  **🔍 testar conexão** — validação passo a passo: instalação → serviço/API →
  modelos instalados → modelo configurado → **geração de teste real com
  latência medida**. Use isso sempre antes de começar a trabalhar.
- **Modelos**: lista com tamanho/data, definir o modelo em uso, **baixar com
  barra de progresso** (`ollama pull` via GUI) e remover do disco.

> É a mesma coisa que trocar o terminal pela GUI: chat, tarefas, ligar/desligar,
> Ollama, modelos, skills, MCP e ajustes — tudo pela interface web. A CLI
> continua disponível para quem preferir.

## 🔌 Conectores MCP

O Hermes é um **cliente MCP** (Model Context Protocol): servidores externos
(Figma, GitHub, bancos, automação) aparecem para o agente como ferramentas
extras `mcp_<servidor>_<ferramenta>`. Configure em `config.yaml`:

```yaml
mcp_servers:
  # Figma via API REST (Framelink) — token em figma.com → Settings → Security
  - name: figma
    command: npx
    args: ["-y", "figma-developer-mcp", "--figma-api-key=SEU-TOKEN", "--stdio"]

  # Figma Dev Mode (app desktop: Preferences → Enable local MCP Server)
  - name: figma-devmode
    url: http://127.0.0.1:3845/mcp

  # Demonstração incluída no projeto (sem token)
  - name: figma-demo
    command: python3
    args: ["mcp-servers/figma_demo_server.py"]
```

Transportes: **stdio** (`command`/`args`) e **Streamable HTTP** (`url`).
Na GUI: Painel → *Servidores MCP* (ativar/reiniciar, ferramentas por servidor).
Qualquer servidor MCP da comunidade funciona — veja
[awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers).

## ✦ Skills (SKILL.md)

Skills são pacotes de instruções que o agente carrega sob demanda: o catálogo
(nome + descrição) entra no prompt de sistema e o conteúdo é lido com
`read_file` só quando a tarefa combina (*progressive disclosure*, formato
aberto [agentskills.io](https://agentskills.io)).

**Incluídas** (pasta `skills/`): `figma-design` (operar o Figma via MCP),
`ui-design-system` (paleta, tipografia, grid 8pt, acessibilidade) e
`app-prototyping` (mapa de telas, fluxos, componentes).

**Instalar do GitHub** — GUI → aba *Skills* (ex.: `anthropics/skills`,
subpasta `skills/pdf`) ou via API:

```bash
curl -X POST localhost:8080/api/skills/install \
  -H 'Content-Type: application/json' -d '{"repo":"anthropics/skills","subpath":"skills/docx"}'
```

**Criar suas próprias**: pasta com `SKILL.md` (frontmatter `name` +
`description` + instruções em Markdown) em `~/.hermes/skills/` — o próprio
agente pode criar skills com a ferramenta `write_file`.

## 🛡 Segurança

O agente executa comandos na máquina — trate-o como um shell com assistência:

- **Sempre** use `--token` se a GUI escutar em `0.0.0.0` (a GUI avisa quando
  estiver aberta sem senha).
- Comandos destrutivos (`rm -rf /`, `mkfs`, `dd` para disco, `shutdown`,
  `curl … | sh`, fork bomb…) são **bloqueados por denylist** em qualquer modo.
- `sandbox: true` restringe leitura/escrita de arquivos ao workspace
  (`~/.hermes/workspace`).
- No terminal, comandos arriscados pedem confirmação
  (`confirm_dangerous: true`).
- Todo comando tem timeout (`cmd_timeout`) e saída truncada.
- Prefira manter a GUI em `127.0.0.1` e acessar via SSH/túnel quando possível.

## 📁 Onde ficam os dados (`~/.hermes`)

```
~/.hermes/
├── config.yaml          configuração (editável pela GUI/CLI)
├── heartbeat.json       estado do agente (pid, status) — usado pelo ligar/desligar
├── workspace/           sandbox de arquivos do agente
├── logs/agent.log       log unificado do agente
├── tasks/               fila de tarefas (spool) + tasks/done/ resultados
└── conversations/       histórico dos chats (JSONL por dia)
```

## 🧪 Modo demonstração (sem Ollama)

Sem Ollama instalado (ou com `--mock`), o Hermes entra em **modo demonstração**:
um Ollama simulado responde localmente, o loop de ferramentas é real e a GUI
funciona por completo — útil para avaliar antes de baixar modelos. As respostas
deixam claro que são simuladas.

## 🧩 Modelos

Qualquer tag do Ollama funciona; o padrão é o Hermes:

```bash
ollama pull hermes3:3b     # leve (~2 GB, 8 GB RAM)
ollama pull hermes3:8b     # padrão (~4,7 GB, 12 GB RAM) — recomendado
ollama pull hermes3:70b    # servidor (~40 GB)
hermes config set model hermes3:3b
```

## ❓ Problemas comuns

| Sintoma | Solução |
|---|---|
| “não consegui falar com o Ollama” | `hermes ollama status` → `hermes ollama start` |
| “modelo não encontrado” | `hermes ollama pull` (baixa o modelo da config) |
| GUI não abre de outro aparelho | liberar a porta no firewall e usar `--host 0.0.0.0` |
| Respostas lentas | use `hermes3:3b` ou reduza `num_ctx` |
| Agente “sem heartbeat” | processo travado → `hermes agent restart` |

---

Feito com ◈ · [Ollama](https://ollama.com) · [Hermes 3 — Nous Research](https://ollama.com/library/hermes3) · Flask

## 🗺 Versões e branches de fase

O projeto evolui em fases — cada uma tem uma branch com o código do marco:

| Branch | Fase |
|---|---|
| `v1.x` | 🖥 O agente de terminal (v1.1.0 → v1.5.0) |
| `v2.x` | 🌐 GUI web + Claude Code (v2.0.0 → v2.2.8) |
| `v3.0.x` | 🏗 A plataforma: auditoria, backups, skills (v3.0.x) |
| `v3.1.x` | 📧 E-mail (OAuth 2FA) + agenda somente leitura (v3.1.x) |
| `main` | 📱 GUI responsiva + PWA (v3.2.x →) |

Detalhe versão a versão: [`docs/HISTORICO-DE-VERSOES.md`](docs/HISTORICO-DE-VERSOES.md) · tags de todas as releases na aba **Tags**.
