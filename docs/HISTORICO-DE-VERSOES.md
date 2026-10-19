# 🗺 Histórico de Versões e Fases do Projeto

O Hermes Agent evoluiu em **5 fases**. Cada fase tem uma **branch** no
repositório apontando para o seu marco final, e cada versão liberada tem
uma **tag** — o código de cada release está congelado exatamente como foi
entregue (um commit por versão, árvore verbatim dos zips de release).

> **Nota técnica:** os commits das fases 1–4 foram *reconstruídos* a partir
> dos arquivos de release oficiais do projeto. As datas dos commits antigos
> refletem o momento da reconstrução; a ordem e o conteúdo são os originais.

| Branch | Fase | Versões | Marco |
|---|---|---|---|
| [`v1.x`](../tree/v1.x) | 🖥 **1 — O agente de terminal** | v1.1.0 → v1.5.0 | núcleo: chat, comandos, memória, agendamento |
| [`v2.x`](../tree/v2.x) | 🌐 **2 — GUI web + 2º agente** | v2.0.0 → v2.2.8 | painel web, Claude Code, web, voz |
| [`v3.0.x`](../tree/v3.0.x) | 🏗 **3 — A plataforma** | v3.0.0 → v3.0.2 | auditoria, backups, skills, scheduler, doctor |
| [`v3.1.x`](../tree/v3.1.x) | 📧 **4 — Conectividade** | v3.1.0 → v3.1.3 | e-mail (OAuth 2FA), agenda, log ao vivo |
| `main` | 📱 **5 — Mobile** | v3.2.0 → | GUI responsiva + PWA instalável |

---

## Fase 1 — 🖥 O agente de terminal (`v1.x`)

O começo: um agente Linux que conversa pelo terminal com o **Ollama**
(modelo local), executa comandos reais (com denylist de segurança) e lê/
grava arquivos. Fundações que seguem até hoje: config YAML, log, chat CLI.

- **v1.1.0 — “Visão completa”**: comando de visão geral do sistema (a versão da demo online)
- **v1.1.1**: blindagem contra PyYAML ausente/corrompido
- **v1.2.0**: espera robusta de resposta + indicador **“A trabalhar…”**
- **v1.3.0**: memória de conversas (histórico, zerar, restaurar)
- **v1.3.1**: tempo de geração exibido na resposta
- **v1.4.0**: ⏰ tarefas agendadas (o agente executa sozinho no horário)
- **v1.5.0**: 👁 execução ao vivo (acompanhar comandos em tempo real) + memória persistente

## Fase 2 — 🌐 GUI web e o segundo agente (`v2.x`)

O agente ganha **painel web**: ligar/desligar agente e Ollama com um clique,
log ao vivo, chat pelo navegador, ferramentas manuais e catálogo de modelos.
Chega o **Claude Code** como segundo agente, rodando sobre o MESMO Ollama —
e começa a batalha contra os delírios de modelos pequenos.

- **v2.0.0**: ferramentas manuais na GUI, Claude Code, catálogo de LMMs, conversas completas
- **v2.0.1**: Claude Code integrado ao Ollama por padrão (sem exports manuais)
- **v2.0.2**: catálogo com curadoria “leves ≤7B” (~10 GB de RAM)
- **v2.1.0**: 🌐 acesso à web (pesquisa + leitura de páginas)
- **v2.2.0**: 🎤 ditado por voz (Whisper local)
- **v2.2.1**: respostas mais rápidas (keep_alive + num_predict)
- **v2.2.2**: fallback de modelo local no Claude Code
- **v2.2.3**: diagnóstico de velocidade na GUI
- **v2.2.4**: prompt enxuto + indicador de modo real
- **v2.2.5**: fim do “JSON solto” (modelos pequenos ecoando schemas)
- **v2.2.6**: Claude Code em **modo leve** (payload enxuto — fim do “fora de si”)
- **v2.2.7**: guard anti-loop no agente
- **v2.2.8**: Claude Code autodiagnóstico + fallback de CLI antiga

## Fase 3 — 🏗 A plataforma (`v3.0.x`)

A “grande atualização” — três eixos: **confiança** (backups antes de
operações, auditoria de tudo, token anti-CSRF), **poder** (ferramentas do
agente direto na GUI, skills, seletor de modelo, orçamento de esforço,
paralelismo, cache) e **inteligência** (scheduler robusto, supervisor,
doctor, notificações, tema claro, markdown rico nas respostas).

- **v3.0.0**: a grande atualização (confiança · poder · inteligência)
- **v3.0.1**: revisão crítica (segurança + correções)
- **v3.0.2**: **guard de execução** — fim do “escreve o comando e não roda”

## Fase 4 — 📧 Conectividade: e-mail e agenda (`v3.1.x`)

O agente sai da máquina: lê e envia e-mails (MCP), com **arquitetura
anti-vazamento** como requisito nº 1 — credenciais em cofre 600 fora do
workspace, nunca passam pelo modelo. Depois: 2FA/OAuth, log de atividades
completo e a agenda Google em modo somente leitura.

- **v3.1.0**: 📧 MCP de e-mail (IMAP/SMTP, credenciais à prova de vazamento)
- **v3.1.1**: 📡 log ao vivo registra TODA a atividade (correção de bug real)
- **v3.1.2**: e-mail com **2FA/OAuth** (XOAUTH2 + device code — Microsoft/Google)
- **v3.1.3**: e-mail **somente leitura por padrão** + 🗓 agenda Google
  (calendar.readonly) + 🌀 guard anti-loop do Claude Code

## Fase 5 — 📱 Mobile (`main`, v3.2.x)

- **v3.2.0**: GUI **responsiva** (barra inferior no celular, teclado
  respeitado, alvos de toque) + **PWA instalável** (“Adicionar à tela
  inicial” abre como app; service worker que nunca cacheia a API)

---

## Linha do tempo completa

| Versão | O que trouxe | Fase |
|---|---|---|
| v1.0.0 | versão inicial | 1 |
| v1.1.0 | "Visão completa" (a versão da demo online) | 1 |
| v1.1.1 | blindagem PyYAML | 1 |
| v1.2.0 | espera robusta + "A trabalhar…" | 1 |
| v1.3.0 | memória de conversas (histórico + zerar + restauração) | 1 |
| v1.3.1 | tempo de geração da resposta | 1 |
| v1.4.0 | tarefas agendadas (⏰) | 1 |
| v1.5.0 | execução ao vivo + memória persistente | 1 |
| v2.0.0 | ferramentas manuais, Claude Code, catálogo de LMMs e conversas completas | 2 |
| v2.0.1 | Claude Code integrado ao Ollama por padrão | 2 |
| v2.0.2 | catálogo com curadoria "leves ≤7B" (máquinas com ~10 GB de RAM) | 2 |
| v2.1.0 | acesso à web (🌐 pesquisa e leitura de páginas) | 2 |
| v2.2.0 | ditado por voz (🎤 Whisper local) | 2 |
| v2.2.1 | respostas mais rápidas (keep_alive + num_predict) | 2 |
| v2.2.2 | Claude Code: fallback de modelo local | 2 |
| v2.2.3 | diagnóstico de velocidade na GUI | 2 |
| v2.2.4 | prompt enxuto + indicador de modo real | 2 |
| v2.2.5 | fim do "JSON solto" (modelos pequenos) | 2 |
| v2.2.6 | Claude Code em modo leve (fim do "fora de si") | 2 |
| v2.2.7 | guard anti-loop no agente | 2 |
| v2.2.8 | Claude Code autodiagnóstico + fallback de CLI antiga | 2 |
| v3.0.0 | a grande atualização (confiança · poder · inteligência) | 3 |
| v3.0.1 | revisão crítica (segurança + correções) | 3 |
| v3.0.2 | guard de execução (fim do "escreve o comando e não roda") | 3 |
| v3.1.0 | 📧 MCP de e-mail (leitura + envio, credenciais à prova de vazamento) | 4 |
| v3.1.1 | 📡 Log ao vivo mostra TODA a atividade (bug real) | 4 |
| v3.1.2 | 📧 e-mail com 2FA/OAuth (XOAUTH2 + device code) | 4 |
| v3.1.3 | 🔎 E-mail somente leitura por padrão · 🗓 Agenda Google · 🌀 guard anti-loop | 4 |
| v3.2.0 | 📱 GUI responsiva (celular/tablet) + instalável como app (PWA) | 5 |
| — | *próxima: v3.3.x — acesso externo seguro (HTTPS/túnel) e mais* | 5 |
