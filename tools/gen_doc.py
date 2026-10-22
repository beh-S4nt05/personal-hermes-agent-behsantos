#!/usr/bin/env python3
"""Gera DOCUMENTACAO.md do Hermes Agent — uso, evolução e referência por
função, extraída DIRETO do código (AST) e do CHANGELOG. Rode na raiz:
    python3 tools/gen_doc.py
"""
import ast
import re
from datetime import date
from pathlib import Path

ROOT = Path("/home/user/hermes-agent")
OUT = ROOT / "DOCUMENTACAO.md"
HOJE = date.today().strftime("%d/%m/%Y")

VERSION = ""
m = re.search(r'VERSION = "([^"]+)"',
              (ROOT / "hermes" / "config.py").read_text(encoding="utf-8"))
if m:
    VERSION = m.group(1)

PAPEL_MODULO = {
    "orchestrator.py": ("🎯", "o coração do pipeline: planeja (lendo a conversa, "
        "a experiência e o goal), aplica skills, submete aos portões de "
        "aprovação, executa, revisa, registra cada task e aprende com as "
        "edições do operador"),
    "agent.py": ("💬", "o executor: conversa com o Ollama com streaming de "
        "tokens e uso das ferramentas"),
    "server/app.py": ("🌐", "a API REST + GUI web (Flask/waitress): todos os "
        "endpoints, streaming do chat, aprovações, painel e páginas"),
    "cli.py": ("⌨️", "todos os comandos `hermes` do terminal"),
    "config.py": ("⚙️", "Config: defaults, leitura/escrita do config.yaml, "
        "skills_dirs, chaves tipadas"),
    "update.py": ("⬇", "autoatualização: consulta tags no GitHub, baixa o zip "
        "e aplica preservando data/.venv/.git"),
    "skills.py": ("✦", "carregador de skills: frontmatter, gatilhos, "
        "ativação e instalação"),
    "skills_audit.py": ("🛡", "auditoria do catálogo: estrutura, tamanho, "
        "prompt injection, duplicatas"),
    "tools.py": ("🔧", "ferramentas do agente: shell, arquivos, web, "
        "lembrar… (com denylist de segurança)"),
    "memory.py": ("🧠", "memória de longo prazo (fatos guardados com "
        "`lembrar`)"),
    "conversations.py": ("🗂", "conversas: sessões, histórico, títulos"),
    "scheduler.py": ("⏰", "agendador de tarefas periódicas/pontuais"),
    "daemon.py": ("🔄", "daemon: fila de tarefas em segundo plano"),
    "manager.py": ("🖥", "liga/desliga Ollama e daemon, boot systemd, "
        "diagnóstico"),
    "ollama_client.py": ("📡", "cliente HTTP do Ollama (chat, tags, ps)"),
    "claude_agent.py": ("🔌", "agente Claude Code (2º cérebro, modo leve)"),
    "mcp_client.py": ("🔌", "cliente MCP: e-mail, agenda, Figma…"),
    "emailcfg.py": ("🔑", "OAuth do e-mail (XOAUTH2 + device code)"),
    "agendacfg.py": ("🔑", "OAuth da agenda Google"),
    "doctor.py": ("🩺", "diagnóstico passo a passo Ollama↔Python"),
    "activity.py": ("📝", "registro de atividade (o que aconteceu e quando)"),
    "audit.py": ("🧾", "auditoria de ações do agente"),
    "backups.py": ("💾", "backups automáticos dos dados"),
    "metrics.py": ("📊", "métricas de uso (jsonl)"),
    "notify.py": ("🔔", "notificações ao operador"),
    "recipes.py": ("📋", "receitas: fluxos prontos de uso"),
    "stt.py": ("🎤", "ditado por voz (Whisper local)"),
    "supervisor.py": ("👁", "supervisor: vigia e reinicia processos"),
}

JS_DESC = {
    "checkOnline": "v3.11.1 — detecta servidor offline e exibe o banner vermelho (casca em cache)",
    "api": "fetch com token X-Hermes-Token embutido",
    "esc": "escape de HTML (anti-injeção na renderização)",
    "store": "persistência leve no localStorage (preferências da GUI)",
    "toast": "aviso flutuante",
    "refresh": "atualiza status/painel",
    "agentAction": "▶ liga / ■ desliga / ⟳ reinicia o agente (daemon)",
    "ollamaAction": "liga/desliga o servidor Ollama",
    "startLog": "log ao vivo da atividade",
    "togglePause": "pausa/retoma o log ao vivo",
    "loadConversations": "lista conversas da lateral",
    "openConversation": "abre uma conversa salva",
    "resetChat": "＋ nova conversa",
    "deleteConversation": "apaga conversa",
    "sendChat": "envia mensagem e consume o streaming (SSE)",
    "stopChat": "■ interrompe a geração",
    "handleEvent": "despacha cada evento do stream (token, note, brain, approval_request, done…)",
    "renderApproval": "cartão de aprovação 🔒/📦 com botões ✅/✏️/⛔ (reusado no banner pós-restart)",
    "approveTask": "posta a decisão no /api/chat/approve",
    "renderBrain": "bloco 🔬 por baixo dos panos",
    "toggleBrain": "liga/desliga a visão 🔬",
    "loadTasks": "fila de tarefas do daemon",
    "addTask": "enfileira tarefa",
    "loadSchedules": "tarefas ⏰ agendadas",
    "schedAdd": "cria agendamento",
    "schedRun": "dispara agendamento agora",
    "loadPerf": "desempenho (tok/s) do painel",
    "loadOrchStats": "v3.10 — Saúde do pipeline (funil, tentativas, skills top)",
    "loadPending": "v3.11 — banner de pendências que sobreviveram a restart",
    "loadModels": "aba Ollama: modelos + papel de cada um",
    "assignRole": "atribuição de papel em 1 clique (chips da aba Ollama)",
    "loadSkills": "catálogo de skills",
    "loadAudit": "auditoria",
    "loadMemory": "memória de longo prazo",
    "loadSettings": "ajustes (toggles ao vivo)",
    "suggest": "sugestões de comandos",
    "toolBlock": "bloco de ferramenta executada (▸ shell, web…)",
    "scrollChat": "autoscroll do chat",
    "mdFmt": "renderização markdown leve das respostas",
    "copyCode": "copiar bloco de código",
}

DADOS = [
    ("config.yaml", "⚙️ configuração do operador (modelos por papel, toggles, host/port)"),
    ("conversations/", "🗂 conversas completas, por sessão"),
    ("orchestrator_tasks.jsonl", "🎯 REGISTRO de cada task do pipeline — status, tentativas, duração, veredito, edições do operador (v3.3+; campos de experiência v3.10). Fonte do painel de saúde e da memória de experiência"),
    ("session_goals.json", "🎯 goals de sessão (/goal) — sobrevivem a restart (v3.11)"),
    ("pending_approvals.json", "🔒/📦 aprovações pendentes — sobrevivem a restart (v3.11)"),
    ("ollama_models_cache.json", "🧠 últimos modelos vistos — aba Ollama funciona com servidor desligado (v3.9)"),
    ("memory.json", "🧠 memória de longo prazo (fatos via `lembrar`)"),
    ("metrics.jsonl", "📊 métricas de uso"),
    ("notifications.json", "🔔 notificações"),
    ("heartbeat.json", "💓 batimento do daemon"),
    ("ollama.pid", "📍 PID do Ollama gerenciado"),
    ("schedules/", "⏰ tarefas agendadas"),
    ("tasks/", "🔄 fila e resultados do daemon"),
    ("audit/", "🧾 auditoria de ações"),
    ("logs/", "📜 logs (Log ao vivo da GUI)"),
    ("backups/", "💾 backups automáticos"),
    ("secrets/", "🔑 credenciais — chmod 600, NUNCA no repo nem no modelo"),
    ("skills/", "✦ skills do usuário (além das 18 embutidas)"),
    ("workspace/", "🧰 área de trabalho do agente"),
]


def _clean(s, n=120):
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        s = s[:n - 1] + "…"
    return s.replace("|", "\\|")


def _sig(node):
    args = []
    for a in node.args.args:
        args.append(a.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for a in node.args.kwonlyargs:
        args.append(a.arg + "=?")
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    for d in node.args.defaults:
        pass
    return "(" + ", ".join(args) + ")"


def parse_modulo(path):
    """Devolve (funções[(nome, args, doc)], classes[(nome, doc, metodos)])."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs, classes = [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.name, _sig(node),
                          _clean(ast.get_docstring(node))))
        elif isinstance(node, ast.ClassDef):
            metodos = [(m.name, _clean(ast.get_docstring(m), 70))
                       for m in node.body
                       if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and not (m.name.startswith("__")
                                and m.name != "__init__")]
            classes.append((node.name, _clean(ast.get_docstring(node), 100),
                            metodos))
    return funcs, classes


def parse_endpoints(path):
    """[(método, rota, fnome, doc)] dos decoradores @app.get/post/…."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    eps = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in ("get", "post", "put", "delete")
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "app" and dec.args):
                rota = dec.args[0].value if isinstance(
                    dec.args[0], ast.Constant) else "?"
                eps.append((dec.func.attr.upper(), rota, node.name,
                            _clean(ast.get_docstring(node))))
    return eps


def secao_modulo(nome, funcs, classes, icon, papel):
    linhas = [f"### {nome} — {icon} {papel}", ""]
    if classes:
        for cnome, cdoc, metodos in classes:
            linhas.append(f"**classe `{cnome}`** — {cdoc or '—'}")
            if metodos:
                linhas.append("")
                linhas.append("| Método | O que faz |")
                linhas.append("|---|---|")
                for mnome, mdoc in metodos:
                    linhas.append(f"| `{mnome}` | {mdoc or '—'} |")
            linhas.append("")
    if funcs:
        linhas.append("| Função | O que faz |")
        linhas.append("|---|---|")
        for fnome, fargs, fdoc in funcs:
            linhas.append(f"| `{fnome}{fargs}` | {fdoc or '—'} |")
    linhas.append("")
    return linhas


# ─────────────────────────────────────────────────────── montagem
partes = []
A = partes.append

A(f"""# 📘 Hermes Agent — Documentação viva: uso, evolução e funções

**Versão {VERSION}** · gerado em {HOJE} · este documento é extraído do
código-fonte (parser AST) e do CHANGELOG — funções, endpoints e versões
refletem exatamente o que está instalado. O histórico detalhado, versão a
versão, está no `CHANGELOG.md`; o manual completo de operação no `docs.md`.

---

## 1. O que é o Hermes Agent

Um **agente pessoal que roda na SUA máquina** (Linux, local-first):
conversa por chat, executa tarefas de verdade (shell, arquivos, web,
e-mail, agenda) usando modelos locais do **Ollama** (≤ 8B), com GUI web
de controle em `localhost:8080` — zero nuvem, zero dado saindo do
computador. O Claude Code entra como 2º agente opcional.

**Princípios que não negociam:**
- 🏠 **local-first**: tudo em `~/.hermes`; funciona offline;
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
hermes update                 # ⬇ atualiza em 1 comando (tags do GitHub)
hermes update --check         # só verifica se há versão nova
```
O `update` preserva `data/` (suas conversas, memória, config), `.venv`
e `.git`.

### 2.2 Ligar e desligar (ciclo de vida)
```bash
hermes server                 # ▶ liga a GUI — http://localhost:8080
# Ctrl+C desliga. Não existe serviço no boot por padrão.
```
- Instalação com `install.sh --with-systemd` cria os services
  (`hermes-server`, `hermes-agent`) — `sudo systemctl disable --now
  hermes-server hermes-agent` remove.
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
| **Skills** | catálogo (18 embutidas), ativar/desativar, criar com `criar-skill`, auditar com `hermes skills audit` (v3.11) |
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
""")

# ── CLI (tabela gerada) ──
src_cli = (ROOT / "hermes" / "cli.py").read_text(encoding="utf-8")
cmds = re.findall(r'add_parser\("([^"]+)",\s*help="([^"]+)"', src_cli)
A("### 2.5 CLI completa\n\n| Comando | O que faz |\n|---|---|\n")
for nome, help_ in cmds:
    A(f"| `hermes {nome}` | {help_} |")
A("\nSubcomandos: `hermes skills audit` (auditar o catálogo), "
  "`hermes config set/get`, `hermes server --host/--port/--token`.\n")

# ── 3. modificações ──
A(f"""
## 3. Modificações — o que foi feito (v1.0.0 → v{VERSION})

40 releases. Tabela extraída do CHANGELOG (a versão detalhada de cada
uma está lá):

| Versão | Marca |
|---|---|
""")
ch = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
for linha in ch.splitlines():
    m = re.match(r"## (v[\d.]+) — (.+)", linha)
    if m:
        A(f"| **{m.group(1)}** | {m.group(2)} |")
A("""
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
""")

# ── 5. arquitetura + dados ──
A("""
## 5. Arquitetura e arquivos de dados

```
navegador ─ GUI (index.html, vanilla JS)
   │  HTTP/SSE
   ▼
hermes server (Flask/waitress, porta 8080) ── CLI `hermes …`
   │                          │
   ▼                          ▼
🎯 orchestrator ────────── ⚡ agent.py ──🔧 tools (shell/web/arquivos)
   │ skills ✦                    │
   ▼                              ▼
🔍 revisão ──► entrega      Ollama (localhost:11434) · Claude Code
   │
   ▼  registro/aprendizado
~/.hermes/ (dados — tabela abaixo)
```

**Arquivos em `~/.hermes/` (data_dir):**

| Caminho | O que guarda |
|---|---|
""")
for nome, desc in DADOS:
    A(f"| `{nome}` | {desc} |")
A("")

# ── 6. referência por função ──
A("## 6. Referência de funções (gerada do código-fonte)\n")
total_fn = 0
ordem = sorted(PAPEL_MODULO.items(),
               key=lambda kv: ["orchestrator.py", "agent.py", "server/app.py",
                               "cli.py", "tools.py", "skills.py",
                               "skills_audit.py", "update.py", "config.py",
                               "memory.py", "conversations.py", "scheduler.py",
                               "daemon.py", "manager.py", "ollama_client.py",
                               "claude_agent.py", "mcp_client.py", "doctor.py",
                               "emailcfg.py", "agendacfg.py"].index(kv[0])
               if kv[0] in ["orchestrator.py", "agent.py", "server/app.py",
                            "cli.py", "tools.py", "skills.py",
                            "skills_audit.py", "update.py", "config.py",
                            "memory.py", "conversations.py", "scheduler.py",
                            "daemon.py", "manager.py", "ollama_client.py",
                            "claude_agent.py", "mcp_client.py", "doctor.py",
                            "emailcfg.py", "agendacfg.py"] else 99)
for nome, (icon, papel) in ordem:
    caminho = ROOT / "hermes" / "server" / "app.py" if nome == "server/app.py" \
        else ROOT / "hermes" / nome
    try:
        funcs, classes = parse_modulo(caminho)
    except Exception as exc:  # noqa: BLE001
        A(f"### {nome} — ⚠ erro ao analisar: {exc}\n")
        continue
    total_fn += len(funcs) + sum(len(c[2]) for c in classes)
    if nome == "server/app.py":
        eps = parse_endpoints(caminho)
        total_fn += len(eps)
        A(f"### hermes/server/app.py — {icon} {papel}\n")
        A(f"**{len(eps)} endpoints HTTP:**\n")
        A("| Método e rota | O que faz |")
        A("|---|---|")
        for met, rota, fnome, doc in eps:
            A(f"| `{met} {rota}` | {doc or fnome} |")
        A("")
        funcs = [f for f in funcs]  # helpers de módulo seguem abaixo
    partes.extend(secao_modulo(f"hermes/{nome}" if nome != "server/app.py"
                               else "app.py — helpers", funcs, classes,
                               icon, papel))

# GUI JS
A("""### GUI (index.html) — funções JavaScript principais

| Função | O que faz |
|---|---|
""")
js_src = (ROOT / "hermes" / "server" / "templates" / "index.html"
          ).read_text(encoding="utf-8")
js_nomes = re.findall(r"^(?:async )?function (\w+)\(", js_src, re.M)
for nome in js_nomes:
    if nome in JS_DESC:
        A(f"| `{nome}()` | {JS_DESC[nome]} |")
A(f"""
*…e mais {sum(1 for n in js_nomes if n not in JS_DESC)} funções de
renderização e utilidade (`mdFmt`, `bubble`, `toolBlock`, `fmtUp`…).*

## 7. Segurança

- **token** opcional (`hermes server --token` / `auth_token`) — header
  `X-Hermes-Token`; **anti-CSRF**: POST cross-origin sem token é 403;
- **denylist** de comandos perigosos no `tools.py` (shutdown, dd em
  disco, /dev/sd*, fork bomb…);
- **secrets/** com chmod 600 — credenciais NUNCA passam pelo modelo,
  config versionado, logs ou auditoria;
- e-mail e agenda **somente leitura** por padrão;
- `hermes skills audit` — anti-prompt-injection no catálogo;
- `git grep` anti-segredo antes de todo push; repo sem dados pessoais.

## 8. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "Address already in use" na 8080 | outro processo na porta | `sudo lsof -nP -iTCP:8080 -sTCP:LISTEN` → `kill <PID>` |
| GUI "abre" com servidor desligado | casca em cache do service worker | banner vermelho acusa (v3.11.1); F12 → Application → Unregister + Clear site data |
| aba Ollama vazia com servidor off | normal — cache expira | ligue o Ollama (aba Ollama ▶) e recarregue |
| "não recebo a resposta do agente" | era bug v3.4, corrigido v3.5 | se voltar, reporte (garantidor do done ativo) |
| update falha (sem internet) | GitHub inacessível | `hermes update --check`; ou unzip manual do zip da release |
| Ollama lento | modelo pesado p/ a máquina | aba Ollama → ver tok/s no Painel; troque por modelo menor |

---
*Documento gerado por `gen_doc.py` (parser AST + CHANGELOG). Para
regenerar após mudanças: `python3 tools/gen_doc.py`.*
""")

OUT.write_text("\n".join(partes), encoding="utf-8")
n_funcs = total_fn
print(f"✔ {OUT} · {len(chr(10).join(partes).splitlines())} linhas · "
      f"{n_funcs} funções/métodos/endpoints documentados")
