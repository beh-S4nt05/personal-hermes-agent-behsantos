# 📘 Hermes Agent — Documentação completa

**Versão 2.0.0** · agente Linux local com Ollama + GUI web · Claude Code integrado

Este documento explica o funcionamento completo do projeto: arquitetura, GUI,
agentes, chat, conversas, tarefas agendadas, memória, ferramentas, API REST,
CLI, configuração, segurança e solução de problemas.

---

## Índice

1. [O que é o Hermes Agent](#1-o-que-é-o-hermes-agent)
2. [Instalação e primeiros passos](#2-instalação-e-primeiros-passos)
3. [Arquitetura e fluxo de dados](#3-arquitetura-e-fluxo-de-dados)
4. [A GUI (abas)](#4-a-gui-abas)
5. [Os dois agentes: Hermes e Claude Code](#5-os-dois-agentes-hermes-e-claude-code)
6. [Chat: como uma mensagem flui](#6-chat-como-uma-mensagem-flui)
7. [Conversas: persistência, nova e busca](#7-conversas-persistência-nova-e-busca)
8. [Tarefas: fila e agendadas (⏰)](#8-tarefas-fila-e-agendadas-)
9. [Memória persistente (📔)](#9-memória-persistente-)
10. [Ferramentas do agente e segurança](#10-ferramentas-do-agente-e-segurança)
11. [Ollama: gerenciamento e download de modelos](#11-ollama-gerenciamento-e-download-de-modelos)
12. [API REST (referência completa)](#12-api-rest-referência-completa)
13. [CLI (referência)](#13-cli-referência)
14. [Configuração (config.yaml)](#14-configuração-configyaml)
15. [Estrutura de dados (data/)](#15-estrutura-de-dados-data)
16. [Skills e conectores MCP](#16-skills-e-conectores-mcp)
17. [Modo demonstração vs modo real](#17-modo-demonstração-vs-modo-real)
18. [Solução de problemas](#18-solução-de-problemas)
19. [Histórico de versões](#19-histórico-de-versões)

---

## 1. O que é o Hermes Agent

Um **agente de operação Linux que roda 100% na sua máquina**, controlável por
terminal (CLI/TUI) e por uma **GUI web local**. Ele conversa com modelos do
**Ollama** (ou com o **Claude Code**) e pode executar comandos, manipular
arquivos, diagnosticar o sistema, usar conectores MCP (ex.: Figma, Gmail),
guardar memória sobre você e rodar **tarefas agendadas sem ninguém no teclado**.

Principais capacidades:

| Capacidade | Onde |
|---|---|
| Conversar e executar ferramentas (loop agente) | Chat / CLI / TUI |
| 🌐 Pesquisar na web e ler páginas | chat, tarefas e aba 🛠 Ferramentas |
| Dois agentes: Hermes (Ollama) e Claude Code | Seletor no chat |
| Tarefas agendadas em português ("diário 07:30") | Aba Tarefas / CLI |
| Execução ao vivo (ver o agente trabalhando) | Modal 👁 na GUI |
| Memória persistente entre conversas | Aba Memória / tool `lembrar` |
| Ferramentas manuais (terminal, arquivos…) | Aba Ferramentas |
| Gerenciar Ollama e baixar modelos | Aba Ollama |
| Conversas salvas, buscáveis e restauráveis | Painel 🕘 no chat |
| Skills instaláveis do GitHub | Aba Skills |

## 2. Instalação e primeiros passos

Requisitos: Linux, Python 3.10+, Ollama instalado (e um modelo baixado).

```bash
unzip hermes-agent-v2.0.0.zip        # (ou a versão atual)
cd hermes-agent
python3 -m venv .venv
./.venv/bin/pip install -e .         # instala o comando `hermes`
ollama pull hermes3:8b               # modelo padrão
./.venv/bin/hermes server            # sobe a GUI
```

A GUI abre em **http://127.0.0.1:8080** (localhost apenas, por padrão).

Opcional — **ditado por voz** (Whisper local):

```bash
./.venv/bin/pip install faster-whisper "av<19"   # ~200 MB; modelo 'base' baixa no 1º uso
```

Opcional — Claude Code como 2º agente: instale a CLI `claude`
(`curl -fsSL https://claude.ai/install.sh | bash`) e confirme com
`ollama launch claude --model hermes3:8b`. O Hermes faz a integração com o
Ollama automaticamente (seção 5).

Instalação permanente (inicia com o sistema): use `install.sh` e as units em
`systemd/` (`hermes-server.service` para a GUI, `hermes-agent.service` para o
daemon de tarefas).

## 3. Arquitetura e fluxo de dados

```
┌────────────────────────────── sua máquina ──────────────────────────────┐
│                                                                         │
│  navegador ── GUI (index.html)                                          │
│      │  fetch/SSE (NDJSON)                                              │
│      ▼                                                                  │
│  Flask (hermes/server/app.py)  ── Scheduler (thread, poll 15s)          │
│      │                        ── ACTIVE_PULLS (downloads canceláveis)   │
│      ▼                                                                  │
│  Agent (hermes/agent.py)  ──ou──  claude_agent.py (CLI `claude`)        │
│      │                                  │                               │
│      ├── tools.py      (run_command, arquivos, sys_info, lembrar…)      │
│      ├── skills.py     (catálogo SKILL.md → prompt)                     │
│      ├── mcp_client.py (conectores: Figma, Gmail…)                      │
│      ├── memory.py     (fatos → prompt)                                 │
│      ▼                                                                  │
│  ollama_client.py ──HTTP──▶ Ollama (127.0.0.1:11434) ──▶ modelo local   │
│                                                                         │
│  dados persistentes em data/ (conversas, agendamentos, memória, tasks)  │
└─────────────────────────────────────────────────────────────────────────┘
```

Módulos (`hermes/`):

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Configuração (defaults ← `data/config.yaml` ← CLI/env) |
| `ollama_client.py` | Cliente HTTP do Ollama + cliente simulado (mock) |
| `manager.py` | Ligar/desligar Ollama e daemon; diagnóstico; boot com sistema |
| `agent.py` | Loop agente: modelo → ferramentas → resposta final |
| `claude_agent.py` | Claude Code como 2º agente (CLI `claude`, stream JSON) |
| `tools.py` | Ferramentas nativas + denylist de segurança + sandbox |
| `skills.py` | Carrega skills (SKILL.md) do projeto e de `data/skills` |
| `mcp_client.py` | Conectores MCP (stdio ou HTTP, ex.: Gmail oficial) |
| `memory.py` | Memória persistente (`data/memory.json`) |
| `conversations.py` | Sessões de chat salvas + busca |
| `scheduler.py` | Tarefas agendadas + buffer de execução ao vivo |
| `daemon.py` | Fila de tarefas em segundo plano |
| `server/app.py` | API REST + GUI (Flask) |
| `cli.py` / `tui.py` | Comando `hermes` e TUI de terminal |

## 4. A GUI (abas)

| Aba | O que faz |
|---|---|
| ▤ **Painel** | Visão geral: agente, Ollama, host, atalhos |
| ◈ **Chat** | Conversa com seletor de agente, ＋ nova conversa, 🕘 histórico com 🔍 busca, cronômetro "A trabalhar…", badge ⏱ tempo · tokens · passos, **🎤 ditado por voz** |
| ☑ **Tarefas** | Fila do agente + resultados; **⏰ Tarefas agendadas** (criar, ▶ agora, 👁 ao vivo, ⏸ pausar, 🗑 apagar) |
| 🧠 **Ollama** | Ligar/desligar/reiniciar, conexão, auto-start, **modelos: buscar catálogo, baixar com progresso, cancelar, apagar** |
| 🛠 **Ferramentas** | Terminal rápido, arquivos do workspace (listar/ler/gravar), info do sistema, **🌐 web (busca DuckDuckGo + leitura de páginas)** e catálogo de funções |
| ✦ **Skills** | Instalar do GitHub, ver conteúdo, ativar/desativar |
| 📔 **Memória** | Fatos guardados: adicionar, editar, apagar |
| ⚙ **Ajustes** | Modelo, prompt extra, limites, sandbox, token de acesso… |

A GUI pode ser protegida por **token de acesso** (Ajustes → `auth_token`);
sem token, só aceite em localhost.

## 5. Os dois agentes: Hermes e Claude Code

### ◈ Hermes (padrão)

Loop agente próprio sobre o Ollama: o modelo recebe o prompt de sistema
(identidade + ferramentas + skills + memória) e pode chamar ferramentas
nativas (`run_command`, arquivos, `lembrar`…) e MCP, até produzir a resposta.
Limite de `max_steps` ciclos por mensagem.

### 🔌 Claude Code (2º agente, v2.0.0)

O chat e as tarefas agendadas podem escolher o agente **Claude Code**: a GUI
executa a CLI `claude` já instalada na sua máquina, dentro do workspace do
Hermes, com as funções padrão do Claude (bash, leitura/edição de arquivos,
busca…). A saída em `stream-json` é traduzida para os mesmos eventos do chat —
você vê passos e ferramentas na hora, e a resposta fica gravada na conversa
com a etiqueta "🔌 Claude Code".

**Instalação** (uma vez, fora do Hermes):

```bash
curl -fsSL https://claude.ai/install.sh | bash    # ou: npm install -g @anthropic-ai/claude-code
ollama launch claude --model hermes3:8b           # teste rodando via Ollama
```

**Integração automática com o Ollama** — como o Claude Code roda sobre o
Ollama, o Hermes lança a CLI `claude` apontada para o **mesmo servidor
Ollama** do agente Hermes: as variáveis (`ANTHROPIC_BASE_URL`,
`ANTHROPIC_AUTH_TOKEN=ollama`, `ANTHROPIC_API_KEY=""`) são aplicadas
automaticamente em cada execução — **não é preciso exportar nada** no
terminal onde o `hermes server` roda.

Ajustes opcionais (aba ⚙ Ajustes ou `config.yaml`):

| Chave | Padrão | Efeito |
|---|---|---|
| `claude_use_ollama` | `true` | Claude Code fala com o Ollama local (automático) |
| `claude_model` | vazio | modelo do Claude Code (ex.: `qwen3-coder`, `hermes3:8b`); vazio = padrão dele |

Use `claude_use_ollama: false` se o seu Claude Code falar com a API real da
Anthropic (login/assinatura) — nesse caso as variáveis não são aplicadas.
Sem a CLI instalada, o agente responde com instruções de instalação.

## 6. Chat: como uma mensagem flui

1. A GUI envia `POST /api/chat` com `{message, history, session_id, agent}`;
2. O servidor valida/cria a **sessão** e grava a mensagem do usuário **antes**
   de gerar (nunca se perde, mesmo se a geração cair);
3. Um worker roda o agente escolhido e publica eventos na fila; a resposta
   vai para o navegador em **NDJSON** (stream linha a linha);
4. Eventos possíveis:

| Evento | Significado |
|---|---|
| `session` | id da sessão persistida |
| `step` | ciclo nº N do loop agente |
| `token` | pedaço de texto gerado (efeito máquina de escrever) |
| `tool_start` / `tool_end` | ferramenta iniciou/terminou (com saída) |
| `stats` | ⏱ duração · nº de tokens · nº de passos |
| `done` / `error` / `cancelled` | fim da geração |
| `ping` | keepalive enquanto o modelo carrega/pensa |

5. Ao terminar, a resposta é gravada na sessão com `dur` e, se for o caso,
   `agent: "claude"`;
6. ⏹ **parar** (botão) cancela a geração — o texto parcial já gerado é mantido.

### 🎤 Ditado por voz (Whisper local)

No chat, o botão **🎤** grava sua voz pelo microfone e o **Whisper local**
(faster-whisper, na CPU) transcreve — o texto vai para o campo de mensagem e
(o padrão) é **enviado sozinho ao agente**, que interpreta e executa como
qualquer mensagem: dite *"liste os arquivos do workspace"* e veja acontecer.

- Requer uma vez: `./.venv/bin/pip install faster-whisper` (~200 MB); o modelo
  (`base`, ≈140 MB) é baixado no primeiro ditado e fica em cache — depois é
  100% local, sem API;
- ⚙ Ajustes: **modelo de voz** (tiny/base/small/medium/large-v3 — maior =
  mais preciso e mais pesado), **idioma** (padrão `pt`) e **enviar
  automaticamente após ditar** (desligue para revisar antes de enviar);
- O microfone exige contexto seguro: funciona em `http://127.0.0.1:8080` ou
  HTTPS; se abrir a GUI por IP na rede (http://192.168.x.x), o navegador
  bloqueia a gravação.

## 7. Conversas: persistência, nova e busca

- Cada conversa é um JSON em `data/conversations/sessions/<id>.json` com todas
  as mensagens; `current.json` aponta a conversa ativa (F5 restaura tudo);
- **＋ nova** — começa uma conversa limpa; a anterior continua salva;
- **🕘 conversas** — lista as salvas (título = primeira mensagem, até 200) com
  *abrir* e *🗑 apagar*;
- **🔍 busca** (v2.0.0) — procura um texto dentro de **todas** as conversas
  (mínimo 2 caracteres), mostra um trecho de onde encontrou e abre a conversa
  com um clique. Busca em perguntas e respostas;
- O título e a contagem de mensagens aparecem na lista; respostas mostram
  ⏱ tempo de geração e etiqueta do agente que respondeu.

## 8. Tarefas: fila e agendadas (⏰)

### Fila do agente (daemon)

Mensagens enfileiradas ("verifique uso de disco…") rodam em sequência no
daemon; resultados aparecem na aba Tarefas (entrada `data/tasks/done/`).
Comando equivalente: `hermes tasks`.

### Tarefas agendadas (v1.4.0+)

O agendador **vive dentro do processo `hermes server`** (thread que verifica a
cada 15 s) — o PC precisa estar ligado com o server aberto no horário.

**Formatos aceitos em português** (campo "quando" ou CLI):

| Exemplo | Tipo | Comportamento |
|---|---|---|
| `diário 07:30` · `todo dia às 8` · `às 8h30 todo dia` | daily | todo dia no horário |
| `seg,qua 14:00` · `sexta às 17h` · `domingo 03:00` | weekly | só nos dias escolhidos |
| `amanhã 09:00` · `hoje 23:59` · `uma vez 2026-10-05 08:00` | once | roda 1× e **desativa sozinha** |
| `a cada 30m` · `a cada 2h` · `a cada 90 minutos` | interval | repete pelo intervalo |

**Regras de disparo** (`is_due`):

- daily/weekly: dispara quando o horário do dia chegou (e passou), no dia
  certo (weekly), se ainda não rodou hoje e se a tarefa não foi criada depois
  do horário no mesmo dia (nesse caso começa no dia seguinte);
- once: dispara no horário com **tolerância de 10 min**; se atrasou mais
  (ex.: PC desligado), é marcada **"perdida"** e desativada — nada roda
  desatualizado;
- interval: dispara quando o intervalo completou desde a última execução (ou
  criação); slots perdidos são pulados.

**Execução desassistida**: tarefas agendadas rodam **sem confirmação
interativa** — nada as barra; apenas a denylist de segurança continua (seção 10).

**Por tarefa**: ▶ rodar agora (força, mesmo pausada), ⏸ pausar/ativar, 🗑
apagar, contagem de execuções, última execução com duração, próxima execução,
e escolha do **agente** (Hermes ou Claude Code).

**👁 Ao vivo**: cada execução alimenta um buffer (passos, ferramentas com
saída, contagem de tokens, resposta final). O modal abre sozinho no "▶ agora"
ou pelo botão "👁 ao vivo" enquanto roda; a última execução fica disponível
para reabrir. O resultado completo também vai para o histórico da aba Tarefas
com o prefixo `⏰ [agendada]`.

CLI: `hermes schedule list | add "tarefa" "diário 08:30" | del <id> | run <id>`.

## 9. Memória persistente (📔)

- Fatos sobre você ficam em `data/memory.json` (id `m########`, data, texto);
- **Entram no prompt de sistema de TODAS as conversas e tarefas agendadas**
  (até 300 fatos / 4000 caracteres), com o id entre colchetes;
- O agente grava/apaga sozinho com as ferramentas **`lembrar`** ("grave que
  meu curso é X") e **`esquecer`** (pelo id);
- Você gerencia tudo na aba **📔 Memória**: adicionar, ✏ editar, 🗑 apagar;
- Exemplo de uso: diga no chat *"lembre que prefiro resumos curtos"* — a
  partir daí o resumo diário de e-mail das 08:00 já sai do seu jeito.

## 10. Ferramentas do agente e segurança

### Ferramentas nativas (tools.py)

| Ferramenta | Função |
|---|---|
| `run_command` | executa comando bash (timeout, saída truncada em 6 KB) |
| `read_file` / `write_file` / `list_dir` | arquivos no workspace (leitura até 512 KB / 8 KB mostrados) |
| `sys_info` | diagnóstico: SO, kernel, CPU, memória, disco, uptime, carga |
| `lembrar` / `esquecer` | grava/apaga fatos da memória persistente |
| `web_search` | pesquisa na internet (DuckDuckGo, sem chave de API) e devolve título + endereço + resumo dos resultados |
| `web_fetch` | baixa uma página http(s) e devolve o texto limpo (sem HTML; até 2 MB) |

Na **aba 🛠 Ferramentas** você usa essas funções manualmente: terminal rápido
(mesma segurança do agente), navegador de arquivos com editor, info do
sistema, **🌐 web (busca + abrir páginas)** e o catálogo completo (nativas +
MCP).

**Acesso à web** — feito **pelo próprio agente**: ele decide pesquisar quando
a resposta depende de informação atual, lê as páginas e cita as fontes. As
ferramentas `web_search` e `web_fetch` (DuckDuckGo, sem chave de API) valem
no chat, nas tarefas agendadas e no Claude Code via `run_command`. Só http/https, conteúdo textual até 2 MB, com timeout —
downloads binários seguem via `run_command` (curl/wget). Desative em
⚙ Ajustes ("🌐 acesso à web") ou `web_access: false` no config: as ferramentas
somem do agente e da GUI.

### Camadas de segurança

1. **Denylist permanente** — comandos destrutivos são SEMPRE bloqueados, em
   qualquer modo, mesmo com confirmação desativada:
   `rm -rf /` e variantes, `mkfs`, `dd` para disco, fork bomb,
   `shutdown/reboot/halt/poweroff`, escrita direta em `/dev/sd*`,
   `chmod -R 777 /`, `curl|sh` (pipe para shell), `mv /`, `insmod/rmmod -a`;
2. **Sandbox de arquivos** (padrão ligado) — leitura/escrita restrita ao
   workspace e às pastas de skills; desative em Ajustes para liberar caminhos
   absolutos;
3. **Timeout** — cada comando tem teto (`cmd_timeout`, máx. 600 s);
4. **Confirmação** — no terminal, comandos arriscados pedem confirmação
   (`confirm_dangerous`). Nas **tarefas agendadas não há confirmação**
   (execução desassistida) — a denylist e o sandbox seguem valendo;
5. **Token da GUI** — defina `auth_token` para exigir senha na interface;
6. **Bind local** — o server escuta em `127.0.0.1` por padrão.

### Conectores MCP e skills

- **MCP** (`mcp_servers` no config): processos locais (stdio) ou servidores
  HTTP — ex.: **Gmail MCP oficial do Google**
  (`https://gmailmcp.googleapis.com/mcp/v1`, OAuth, escopo `gmail.readonly`;
  bloco pronto e comentado no `config.example.yaml`);
- **Skills**: pastas com `SKILL.md` que viram instruções no prompt. Vêm no
  projeto (`figma-design`, `ui-design-system`, `app-prototyping`,
  `resumo-inbox`) ou instale do GitHub na aba Skills (qualquer repo com
  SKILL.md, ex.: `anthropics/skills`).

## 11. Ollama: gerenciamento e download de modelos

A aba 🧠 Ollama mostra estado (versão, PID, uptime, memória), botões
ligar/desligar/reiniciar, "iniciar com o sistema" (systemd), endereço da API,
teste de conexão e **"ligar automaticamente"** (o agente sobe o Ollama sozinho
quando precisar).

**Modelos (LMMs) — v2.0.0 completa:**

- **🔍 Buscar no catálogo** — junta a biblioteca oficial (ollama.com, com
  descrição, capacidades como *tools/vision* e tamanhos disponíveis) e uma
  curadoria popular comentada em português; a busca ignora acentos
  ("codigo" acha "código");
- **⬇ Baixar com 1 clique** no resultado (ou pelo nome exato `modelo:tag`);
  barra de progresso em tempo real (NDJSON);
- **⏹ Cancelar** o download em andamento;
- **🗑 Apagar** modelos instalados; lista mostra o que já está na máquina.

CLI: `hermes models` (listar), `hermes ollama start|stop|status|test|pull <modelo>`, `hermes doctor` (diagnóstico).

### ⚡ Deixando as respostas mais rápidas (sem trocar de modelo)

1. **keep_alive** (⚙ Ajustes → "manter modelo carregado", padrão `30m`): sem
   isso o Ollama descarrega o modelo ~5 min após o uso e a próxima mensagem
   paga o carregamento de novo (vários segundos). Use `1h` ou `-1` (sempre)
   se sobrar RAM — agora todo pedido do agente já envia esse valor.
2. **num_predict** (⚙ Ajustes, `0` = sem limite): `512`–`768` tokens deixam as
   respostas mais concisas e chegam bem antes.
3. **Modelo certo para cada tarefa**: um 3B (`llama3.2:3b`, `hermes3:3b`,
   `qwen2.5:3b` ≈ 2 GB) responde em cerca de metade do tempo de um 8B, com
   qualidade suficiente para o dia a dia; deixe o 8B para tarefas difíceis.
   Evite modelos "pensantes" (`deepseek-r1`) quando velocidade importa — a
   cadeia de raciocínio multiplica o tempo de geração.
4. **num_ctx menor**: `4096` em vez de `8192` acelera o pré-processamento do
   prompt (se os prompts do agente couberem).
5. **GPU**: com GPU NVIDIA o Ollama usa automaticamente — confira com
   `ollama ps` durante uma geração (coluna *PROCESSOR*: `100% GPU`). Um 3B
   inteiro na VRAM responde quase instantaneamente; `nvidia-smi` mostra a
   VRAM disponível.
6. **Aceleração extra do serviço** (opcional):

   ```bash
   sudo systemctl edit ollama
   #    [Service]
   #    Environment="OLLAMA_FLASH_ATTENTION=1"
   #    Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
   sudo systemctl restart ollama
   ```

## 12. API REST (referência completa)

Autenticação: se `auth_token` estiver definido, envie header
`Authorization: Bearer <token>`. Respostas em JSON; streams em NDJSON.

| Método e rota | Descrição |
|---|---|
| `GET /` | página da GUI |
| `GET /api/status` | status consolidado (agente, ollama, host, versão) |
| `POST /api/chat` | conversa (NDJSON) — body `{message, history, session_id, agent}` |
| **Conversas** | |
| `GET /api/conversations` | lista sessões + corrente |
| `GET /api/conversations/<id>` | sessão completa |
| `GET /api/conversations/search?q=` | busca em todas as conversas |
| `POST /api/conversations/current` | aponta a conversa ativa |
| `POST /api/conversations/delete` | apaga sessão |
| **Memória** | |
| `GET /api/memory` · `POST /api/memory` | lista · adiciona fato `{text}` |
| `POST /api/memory/update` · `POST /api/memory/delete` | edita `{id,text}` · apaga `{id}` |
| **Tarefas agendadas** | |
| `GET /api/schedules` · `POST /api/schedules` | lista · cria `{input, when, agent}` |
| `POST /api/schedules/toggle` | `{id, enabled}` pausa/ativa |
| `POST /api/schedules/delete` · `POST /api/schedules/run` | apaga · roda agora `{id}` |
| `GET /api/schedules/live?id=` | buffer da execução ao vivo |
| **Fila do agente** | |
| `GET /api/tasks` · `POST /api/tasks` · `POST /api/tasks/clear` | lista/resultado · enfileira · limpa histórico |
| `POST /api/agent/<action>` | `start`/`stop`/`restart` do daemon |
| **Ferramentas manuais** | |
| `GET /api/tools` | catálogo (nativas + MCP) |
| `POST /api/tools/run` | terminal rápido `{command}` (denylist ativa) |
| `POST /api/tools/list_dir` / `read_file` / `write_file` / `sys_info` | arquivos e diagnóstico |
| `POST /api/tools/web_search` / `web_fetch` | 🌐 `{query}` busca · `{url}` abre página |
| `GET /api/stt/status` · `POST /api/stt` | 🎤 status da voz · transcreve áudio (multipart `audio`) |
| **Ollama** | |
| `GET /api/ollama/diagnose` · `POST /api/ollama/test` | diagnóstico · teste de conexão |
| `GET /api/ollama/models` | modelos instalados |
| `GET /api/ollama/library?q=` | catálogo de modelos (curadoria + ollama.com) |
| `POST /api/ollama/pull` | baixa modelo (NDJSON com progresso) |
| `POST /api/ollama/pull/cancel` | cancela download `{model}` |
| `POST /api/ollama/delete` | apaga modelo `{model}` |
| `POST /api/ollama/restart` · `POST /api/ollama/boot` | reinicia · inicia com o sistema |
| `POST /api/ollama/<action>` | `start`/`stop` |
| **Skills / MCP / config / logs** | |
| `GET /api/skills` · `POST /api/skills/install` · `POST /api/skills/toggle` | lista · instala do GitHub · ativa/desativa |
| `GET /api/skills/content` | conteúdo de uma skill |
| `GET /api/mcp` · `POST /api/mcp/start` · `POST /api/mcp/restart` | conectores |
| `GET /api/settings` · `POST /api/settings` | lê/salva configurações |
| `GET /api/logs` · `GET /api/logs/stream` · `POST /api/logs/clear` | log do agente (SSE ao vivo) |

## 13. CLI (referência)

```bash
hermes server [--host 0.0.0.0] [--port 8080]   # GUI + agendador (modo de uso)
hermes chat                                     # TUI de terminal
hermes run "verifique uso de disco"             # uma tarefa direto
hermes agent start|stop|restart                 # daemon de tarefas
hermes tasks                                    # fila + resultados
hermes schedule list                            # tarefas agendadas
hermes schedule add "resumo dos e-mails" "diário 07:30"
hermes schedule del <id> · hermes schedule run <id>
hermes ollama start|stop|status|test|pull      # servidor Ollama e modelos
hermes models                                   # modelos instalados
hermes config set model hermes3:8b              # ajustes persistentes
hermes status · hermes doctor                   # visão geral · diagnóstico
```

## 14. Configuração (config.yaml)

Prioridade: **defaults ← `data/config.yaml` ← flags/env**. Variáveis de
ambiente: `HERMES_DATA_DIR` (pasta de dados) e `HERMES_MOCK=1` (demo).

| Chave | Padrão | Descrição |
|---|---|---|
| `ollama_url` | `http://127.0.0.1:11434` | endereço do Ollama |
| `model` | `hermes3:8b` | modelo padrão (formato `nome:tag`) |
| `num_ctx` / `temperature` | 8192 / 0.4 | contexto e criatividade |
| `auto_start_ollama` | false | sobe o Ollama sozinho quando precisar |
| `claude_use_ollama` | true | 🔌 Claude Code integrado ao Ollama (variáveis automáticas) |
| `claude_model` | vazio | modelo do Claude Code (ex.: `qwen3-coder`) |
| `web_access` | true | 🌐 ferramentas de web do agente e da GUI |
| `stt_model` / `stt_language` | base / pt | 🎤 modelo do Whisper e idioma do ditado |
| `stt_autosend` | true | envia a mensagem ao agente após ditar |
| `host` / `port` | 127.0.0.1 / 8080 | onde a GUI escuta |
| `auth_token` | vazio | senha da GUI (use se abrir para a rede) |
| `max_steps` | 8 | ciclos modelo→ferramenta por tarefa |
| `keep_alive` | 30m | mantém o modelo na RAM entre mensagens (anti cold-start) |
| `num_predict` | 0 | máx. tokens por resposta (0 = sem limite; 512–768 = mais rápido) |
| `cmd_timeout` | 60 | teto (s) por comando shell |
| `sandbox` | true | arquivos restritos ao workspace |
| `confirm_dangerous` | true | confirmação no terminal p/ comandos arriscados |
| `system_prompt_extra` | vazio | instruções extras no prompt |
| `mcp_servers` | [] | conectores `{name, command|url, …}` |
| `mcp_timeout` | 120 | timeout MCP (s) |
| `skills_disabled` | [] | skills desligadas pela GUI |

Exemplo de conector Gmail (oficial do Google):

```yaml
mcp_servers:
  - name: gmail
    url: https://gmailmcp.googleapis.com/mcp/v1   # requer OAuth (Google Cloud)
```

## 15. Estrutura de dados (data/)

```
data/                          (padrão: ~/.hermes — na demo: hermes-agent/data)
├── config.yaml                configuração persistida
├── memory.json                📔 fatos da memória do agente
├── conversations/
│   ├── current.json           ponteiro da conversa ativa
│   └── sessions/*.json        cada conversa (mensagens, dur, agent)
├── schedules/*.json           ⏰ tarefas agendadas (spec, execuções, status)
├── tasks/
│   ├── queue/                 fila do daemon
│   └── done/*.json            resultados (agendadas entram como "⏰ [agendada]")
├── logs/agent.log             log do agente
├── heartbeat.json             batimento do daemon
├── workspace/                 📂 área de trabalho do agente (sandbox)
└── skills/                    skills instaladas pela GUI
```

Backup: copie a pasta `data/` inteira — nela está tudo (conversas, memória,
agendamentos, configuração).

## 16. Skills e conectores MCP

- **Skill** = pasta com `SKILL.md` (instruções que entram no prompt quando
  relevantes). Instale pela aba Skills (owner/repo do GitHub + subpasta
  opcional) ou crie a sua em `data/skills/minha-skill/SKILL.md`;
- Skills inclusas: `pesquisa-web` (pesquisar, aprender e monitorar com
  relatórios diários), `figma-design`, `ui-design-system`, `app-prototyping`
  (design com MCP do Figma) e `resumo-inbox` (relatório diário de e-mails +
  atividades do Google Classroom — Gmail via MCP oficial; Classroom via
  e-mails de notificação ou API com OAuth);
- **MCP** = protocolo de ferramentas externas. Configure em `mcp_servers`
  (processo local via `command`/`args` ou servidor via `url`). As ferramentas
  MCP aparecem para o agente como qualquer outra ferramenta.

## 17. Modo demonstração vs modo real

- **Modo real** (uso): `hermes server` com Ollama verdadeiro;
- **Modo demo** (`HERMES_MOCK=1` ou `--mock`, usado por `demo.sh`): IA
  simulada para testar a interface sem Ollama — o server imprime o banner
  gigante "MODO DEMONSTRAÇÃO — IA SIMULADA". Ferramentas, tarefas, memória,
  conversas e downloads simulados funcionam de verdade; o Claude Code
  responde com um texto explicando o modo.

## 18. Solução de problemas

| Sintoma | Causa/procedimento |
|---|---|
| "O servidor Ollama está desligado" | Ligue na aba Ollama ou `hermes ollama start`; ou ative "ligar automaticamente" |
| `invalid model name` | Modelo sem `:tag` — use `hermes3:8b` (Ajustes → modelo) |
| Modelo não encontrado | `ollama pull <modelo>` ou aba Ollama → Models |
| Resposta lenta na 1ª msg | modelo carregando na memória (normal; aguarde o `ping`) |
| Claude Code "não encontrado" | instale com `curl -fsSL https://claude.ai/install.sh \| bash` (ou npm) e reinicie o `hermes server` |
| Claude Code vazio/erro | já aponta para o Ollama por padrão; confira o `claude_model` (use um modelo instalado) ou, se usa a API real, desative `claude_use_ollama` |
| PyYAML com erro no pip (Windows/NTFS) | `pip install --force-reinstall --no-cache-dir PyYAML` |
| Tarefa agendada não disparou | server estava fechado no horário? once perdeu a janela de 10 min ("perdida"); as demais disparam no próximo ciclo |
| Erro de YAML no config | confira indentação (2 espaços) e aspas |
| GUI pedindo token | é o `auth_token`; defina/altere em Ajustes |
| Sandbox bloqueou um caminho | desative `sandbox` em Ajustes (por sua conta e risco) |
| Busca na web sem resultados | DuckDuckGo limita rajadas — espere uns segundos e tente de novo; confira se "🌐 acesso à web" está ativo em Ajustes |
| 🎤 não grava | o microfone só funciona em `http://127.0.0.1:8080` ou HTTPS (abrindo por IP na rede, o navegador bloqueia); confira a permissão do microfone no navegador |
| 🎤 "transcrição não instalada" | `./.venv/bin/pip install faster-whisper "av<19"` e recarregue a página |
| 1º ditado demora | é o download do modelo (base ≈140 MB, uma vez só) — os seguintes são rápidos |

## 19. Histórico de versões

| Versão | Destaques |
|---|---|
| **2.0.0** | 🛠 aba Ferramentas · 🔌 Claude Code como 2º agente (chat + agendadas) · 📚 catálogo de LMMs com busca + download cancelável · 💬 conversas completas (＋ nova, 🔍 busca) |
| 1.5.0 | 👁 execução ao vivo das tarefas · 📔 memória persistente (tools `lembrar`/`esquecer`) |
| 1.4.0 | ⏰ tarefas agendadas em PT-BR, execução desassistida, CLI `schedule`, skill resumo-inbox |
| 1.3.x | abas não perdem processo; 🗑 zerar + 🕘 conversas anteriores com backup; restauração no F5; cronômetro + badge ⏱ tokens · passos |
| 1.2.0 | promise/retry/cancel, loading "A trabalhar…", ⏹ parar |
| 1.1.x | MCP Figma + skills de design; diagnóstico Ollama na GUI; Claude Code via Ollama; correções |
| 1.0.0 | agente Linux com Ollama + GUI web, fila de tarefas, TUI/CLI |

Detalhes por versão em `CHANGELOG.md`.

---

*Hermes Agent — roda 100% local: seus dados, conversas e memória ficam na
sua máquina.*
