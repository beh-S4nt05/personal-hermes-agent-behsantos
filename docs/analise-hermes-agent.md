# 🔬 Estudo técnico do Hermes Agent — v2.2.8

**Data:** out/2026 · **Método:** raio-X do código-fonte (19 módulos, ~7.150 linhas medidas), análise por área e propostas priorizadas.
**Status:** ⚠️ **PROPOSTA — nada aqui foi implementado.** Cada item descreve *o quê, por quê e como*; só entra no código após sua confirmação.

---

## 1. A aplicação hoje (mapa)

### 1.1 Números medidos

| Métrica | Valor |
|---|---|
| Linhas (Python + HTML) | **7.152** |
| Maior arquivo | `templates/index.html` — **1.667** linhas (SPA vanilla) |
| Endpoints HTTP | **~50** rotas (`app.py`, 1.046 linhas) |
| Ferramentas nativas | **9** (run_command, read/write_file, list_dir, sys_info, web_search, web_fetch, lembrar, esquecer) |
| Páginas da GUI | **8** (painel, chat, skills, memória, ajustes, ferramentas, ollama, tarefas) |
| Agentes | **2** (◈ Hermes local · 🔌 Claude Code com modo leve) |
| Transportes MCP | **2** (stdio + Streamable HTTP) |
| Skills instaladas | 5 (pesquisa-web, resumo-inbox, app-prototyping, figma ×2) |

### 1.2 Arquitetura

```
┌─────────────────────────── GUI (SPA vanilla, 8 páginas) ───────────────────────────┐
│  chat (SSE) · visão ao vivo · tarefas/agendador · skills · memória · ajustes · logs │
└──────────────┬───────────────────────────────────────────────┬─────────────────────┘
               │ ~50 rotas /api                                 │ SSE (token a token)
┌──────────────▼───────────────────────────────────────────────▼─────────────────────┐
│  server/app.py (Flask threaded)                                                     │
│   ├─ agent.py ── loop de ferramentas ──┐                                            │
│   │    ├─ tools.py (9 nativas + denylist)          ├─ claude_agent.py (CLI,        │
│   │    ├─ skills.py (catálogo p/ o prompt)         │   modo leve --bare, fallback) │
│   │    └─ memory.py (cap 2.000 chars)              │                              │
│   │    └─ mcp_client.py ── stdio / http ──> mcp-servers/                           │
│   ├─ ollama_client.py (chat_stream, keep_alive, num_predict)                       │
│   ├─ scheduler.py (intervalo + horário fixo, tick 15s) ── daemon.py                │
│   ├─ conversations.py (JSON por sessão) · stt.py (Whisper local)                   │
│   └─ manager.py (serviço Ollama: boot/restart/diagnose)                            │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 O que já está sólido (e não precisa mexer)

- **Local-first de verdade**: nada de nuvem/API paga; Ollama + Whisper locais; modo real é o modo de uso.
- **Streaming ponta a ponta**: SSE do Ollama até a GUI, com keepalive e cancelamento.
- **Resiliência a modelos pequenos**: fallback de JSON solto (v2.2.5), guard anti-loop (v2.2.7), modo leve do Claude Code (v2.2.6–2.2.8) — validados com CLI/API reais.
- **Segurança básica sensata**: host `127.0.0.1` por padrão, token de acesso opcional, denylist de comandos, `resolve_path` confinado ao workdir, limite de 512 KB em gravações.
- **Operabilidade**: ~50 endpoints cobrindo pull/cancel de modelos, diagnóstico do Ollama, logs em stream, mock mode para demo.
- **Agendador sem barreiras** (requisito seu): tarefas rodam sem confirmação interativa.

---

## 2. Análise por área

Legenda de esforço: 🟢 S (horas) · 🟡 M (1–2 sessões) · 🔴 L (estrutural).

---

### ⚡ 2.1 PERFORMANCE

**Como está:** streaming com `keep_alive` 30m + `num_predict`; prompt de sistema ~728 tokens (skills/ferramentas/memória enxutos); badge tok/s; memória com teto de 2.000 chars; Flask `threaded=True`; ferramentas executadas **em sequência**; `system_prompt()` **reconstruído a cada request**; conversas em JSON.

**Lacunas:** trabalho redundante por request; histórico truncado em vez de resumido; sem métricas históricas; servidor de desenvolvimento em produção.

| # | Melhoria | Como eu faria | Esforço |
|---|---|---|---|
| P1 | **Cache do prompt de sistema** | `agent.py` monta o prompt 1× e guarda hash; invalida só quando config/skills/memória mudarem. Bônus: prefixo estável = Ollama reaproveita KV-cache interno → primeira resposta mais rápida | 🟢 |
| P2 | **Ferramentas em paralelo** | Hoje `for call in calls` é sequencial. Com 2+ chamadas no mesmo passo: `ThreadPoolExecutor(max_workers=3)`, preservando a ordem dos resultados no histórico. Ex. típico: `web_search` + `sys_info` juntas | 🟡 |
| P2 | **Servidor de produção** | `waitress` (puro Python, instalação leve) no modo real, no lugar do `app.run` do Flask. SSE e tarefas simultâneas mais estáveis | 🟢 |
| P2 | **Painel de métricas** | `/api/metrics` persistindo tok/s, tempo até 1º token e `ollama ps` (CPU vs GPU) por resposta; mini-gráfico na página painel. "Está lento" vira dado, não achismo | 🟡 |
| P3 | **Sumarização de conversa** | Em vez de truncar histórico antigo, sumarizar em background (num_predict baixo, pós-resposta) e guardar "resumo até aqui" na sessão | 🟡 |
| P3 | **Memória vetorial** | `sqlite-vec` + `nomic-embed-text` (~274 MB, via Ollama) — lembrar de tudo sem pagar tokens no prompt | 🔴 |

---

### 🎨 2.2 DESIGN

**Como está:** SPA vanilla em **arquivo único de 1.667 linhas**; 8 páginas; tema escuro; toasts; badges com tempo/tokens/passos; respostas renderizadas como **texto puro**.

**Lacunas:** respostas sem Markdown tornam código/listas difíceis de ler; manutenção do arquivo único; sem atalhos de teclado; sem wizard de primeira execução (origem de metade dos "não funciona").

| # | Melhoria | Como eu faria | Esforço |
|---|---|---|---|
| D1 | **Renderizar Markdown nas respostas** | Parser MD mínimo **próprio** (sem CDN — preview sem rede): títulos, listas, negrito, blocos de código com **botão copiar**. Maior ganho de polimento percebido | 🟡 |
| D2 | **Dividir o index.html** | `static/app.css` + `static/app.js` servidos pelo Flask; HTML só com estrutura. Manutenção deixa de ser caça em 1,6k linhas | 🟡 |
| D3 | **Linha do tempo na visão ao vivo** | Passos colapsáveis com **duração por passo**, medidor tok/s ao vivo, avatares ◈/🔌 por agente | 🟡 |
| D4 | **Atalhos + acessibilidade** | Ctrl+Enter envia · Esc para · `/` foca o campo · aria-labels · contraste revisado | 🟢 |
| D5 | **Wizard "hermes doctor"** | Checklist na primeira execução (e comando CLI): Ollama on? modelo instalado? Whisper ok? CLI claude nova? — cada item com botão corrigir. Reduz drasticamente tickets de suporte | 🟡 |
| D6 | **Tema claro/escuro + responsivo** | CSS variables (um só lugar) + layout mobile — usar o agente pelo celular na rede local (com token) | 🟡 |
| D7 | **Exportar conversa** | Botão ⬇ baixa a sessão como `.md` (ou `.json`) | 🟢 |

---

### 🎛 2.3 CONTROLE

**Como está:** denylist de comandos; token opcional (host localhost por padrão); workdir confinado; cancel via `terminate()`; timeouts (Claude 15 min); anti-loop; `--max-turns 4`.

**Lacunas:** `write_file` **sobrescreve sem backup** (irreversível); sem auditoria persistente de ações do agente; sem teto de chamadas por resposta; cancelamento mata no meio da ferramenta.

| # | Melhoria | Como eu faria | Esforço |
|---|---|---|---|
| C1 | **Auditoria (trilha de ações)** | JSONL append-only em `data/audit/`: timestamp, agente, ferramenta, args, status, saída truncada. Página com filtro por agente/ferramenta/dia. Hoje os logs mostram o servidor, não o histórico de *ações* | 🟡 |
| C2 | **Backups automáticos antes de gravar** | `write_file` copia o arquivo atual para `data/backups/<data>/<hora>-<nome>` (rotativo, máx. 20/arquivo) + botão **"reverter"** na GUI. O agente pode escrever, você pode desfazer | 🟢 |
| C3 | **Orçamento por resposta** | Teto de 12 chamadas de ferramenta por resposta e de tokens por tarefa agendada — prende cadeias infinitas mesmo quando as chamadas não são idênticas (buraco que o anti-loop v2.2.7 não cobre) | 🟢 |
| C4 | **Cancelamento gracioso** | Em vez de `terminate()` imediato: flag faz a ferramenta corrente terminar, pula as próximas e devolve o parcial — sem arquivo pela metade | 🟡 |
| C5 | **Modo "planejar antes"** | Toggle por conversa: o agente lista o que faria e aguarda ✓ (tarefas agendadas continuam **sem barreira**, como você exigiu) | 🟡 |
| C6 | **Token automático fora do localhost** | Se `host ≠ 127.0.0.1` e token vazio: gerar token, mostrar 1× e exigir. Headers CSP + rate limit simples nos endpoints de escrita | 🟢 |

---

### 🤖 2.4 AUTOMAÇÃO

**Como está:** scheduler com intervalo ("a cada 30m") e horário fixo ("todos os dias às 8h"); tick de 15s; execução sem barreiras; visão ao vivo; `last_run` e status ok/erro por tarefa.

**Lacunas:** **sem retry** (tarefa falhou, esperou até a próxima); **sem histórico de execuções** (só o "ao vivo"); sem notificação de falha; sem gatilhos que não sejam tempo; timezone implícito.

| # | Melhoria | Como eu faria | Esforço |
|---|---|---|---|
| A1 | **Histórico de execuções** | Guardar as últimas 20 execuções por tarefa (ts, duração, status, primeiros 500 chars da saída) + página de histórico com "rodar de novo" | 🟢 |
| A2 | **Retry com backoff** | Campo opcional "se falhar, tentar 2× a cada 5 min". Falha de rede/modelo carregando deixa de virar tarefa perdida | 🟢 |
| A3 | **Gatilhos por evento** | (a) **watcher**: "quando aparecer PDF em ~/Downloads → faça X" (polling com hash de diretório, sem dependência externa); (b) **webhook**: `POST /api/hooks/<id>` dispara tarefa — abre integração com Gmail, n8n, IFTTT | 🟡 |
| A4 | **Notificações de falha** | Toast persistente na GUI + webhook opcional por tarefa (e-mail via MCP quando houver servidor configurado) | 🟡 |
| A5 | **Dependências + timezone** | "rodar B após A terminar ok" e TZ explícito (America/Manaus) no agendador | 🟢 |
| A6 | **Galeria de receitas** | 5–6 tarefas prontas, 1 clique p/ ativar: resumo diário de notícias, relatório semanal do sistema, limpeza de backups antigos | 🟡 |
| A7 | **Execução em idle** | Sondar inatividade (load + input) e adiar tarefas pesadas para quando a máquina estiver livre | 🔴 |

---

### 🔌 2.5 SERVERS MCP

**Como está:** transportes **stdio + Streamable HTTP**; ciclo de vida (start/stop/alive/restart); `list_tools`/`call_tool` com timeout fixo de 60s; ferramentas MCP entram no prompt do agente via `handles()`; 1 servidor de exemplo (figma) e rotas na GUI para ativar/reiniciar.

**Lacunas:** configurar servidor = **editar YAML à mão**; processo morto **não renasce** (o agente só erra na hora da chamada); timeout fixo; sem permissões por ferramenta MCP; catálogo = 1 exemplo.

| # | Melhoria | Como eu faria | Esforço |
|---|---|---|---|
| M1 | **Painel MCP de verdade na GUI** | Listar servidores do YAML com status (online/offline/nº de ferramentas), ligar/desligar, **testar ferramenta** e **adicionar servidor por formulário** — sem tocar em arquivo | 🟡 |
| M2 | **Supervisor com auto-restart** | Loop de saúde a cada 60s: servidor morto → restart com backoff; log rotativo por servidor. MCP deixa de "sumir" silenciosamente | 🟢 |
| M3 | **Permissões por ferramenta MCP** | Allow/deny como nas nativas (hoje o modelo pode chamar qualquer ferramenta MCP que esteja no ar) | 🟢 |
| M4 | **Timeout e limites por servidor** | Configurável no YAML (padrão 60s) + teto de tamanho de resposta truncando com aviso | 🟢 |
| M5 | **Catálogo curado 1-clique** | Receitas para servidores locais úteis: filesystem (escopado), fetch, sqlite, memory/knowledge-graph, playwright (navegação real para pesquisa) — cada um com aviso de custo de RAM | 🟡 |
| M6 | **Seleção dinâmica de ferramentas** | Com muitos servidores, injetar no prompt só as N ferramentas mais parecidas com a pergunta (similaridade de descrição) — poupa tokens e **reduz delírio do modelo pequeno** (mesma lição do modo leve do Claude Code) | 🔴 |

---

## 3. O que eu NÃO mudaria (filosofia do projeto)

1. **Local-first**: nada de nuvem, chave de API paga ou telemetria.
2. **Alvo = modelos ≤8B**: toda otimização considera essa realidade (payload enxuto sempre).
3. **Zero build-step**: vanilla JS, sem npm/webpack — a GUI funciona offline para sempre.
4. **Tarefas agendadas sem barreiras** (sua exigência) — os controles novos são opcionais e per-conversa.
5. **Mock mode** para demonstração, com banner explícito — modo real continua sendo o modo de uso.

---

## 4. Roadmap sugerido (3 ondas)

| Onda | Conteúdo | Resultado esperado |
|---|---|---|
| **1 — Confiança** 🥇 | C2 backups · C1 auditoria · C3 orçamento · A1 histórico · A2 retry · D1 Markdown+copiar · M2 supervisor MCP · P1 cache de prompt | Nada irreversível, nada silencioso, tudo visível |
| **2 — Poder** 🥈 | P2 paralelismo+waitress+métricas · A3 gatilhos (watcher+webhook) · A4 notificações · D3 timeline · D5 wizard doctor · M1 painel MCP · D7 exportar | Automação além do relógio; diagnóstico automático |
| **3 — Inteligência** 🥉 | P3 memória vetorial · M6 seleção dinâmica MCP · A6 receitas · A7 idle · D6 mobile/temas | O agente lembra de tudo e gasta menos pra pensar |

**Regra de ouro que segui em tudo:** cada melhoria respeita as 5 restrições da seção 3 — nenhuma exige nuvem, modelo maior ou build-step.

---

*Documento de estudo — gerado a partir do código v2.2.8. Nenhum item implementado sem confirmação.*
