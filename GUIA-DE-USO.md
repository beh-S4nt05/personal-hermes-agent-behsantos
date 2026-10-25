# 📖 Guia de Uso — o que fazer SOMENTE com o Betterme (v3.15.1)

> Catálogo prático para o operador: capacidades reais (testadas, 120/120),
> prompts de exemplo para copiar e colar, e limites honestos.
> Complementa o `MAPA_APLICACAO.md` (por dentro) — este é o lado de QUEM USA.

---

## 🚀 Modo missão — autonomia total (v3.16.0)

Passe UMA tarefa com o prefixo **`missão:`** e o Betterme faz o resto:

```
missão: construa meu app de gastos em /media/Arquivos/projetos/gastos,
  com testes e git
```

Ele divide em 2-5 subtasks sequenciais, executa cada uma como task
completa (com revisor e aprovações), **valida cada etapa** e, se algo
reprovar, **reescreve a própria task** com o problema apontado e tenta de
novo — até o objetivo inicial sair validado, com relatório final
(subtask por subtask, tentativas e veredito). Sem pasta no pedido? Ele
pergunta o caminho uma vez e retoma a missão inteira com ele.

---

## A fórmula do prompt que funciona

```
[VERBO DE CONCLUSÃO] + [OBJETO] + [LOCAL (caminho)] + [CRITÉRIO DE ACEITE]
```

- **Verbo de conclusão**: crie, analise, corrija, organize, monitore — não
  "me ajude com...".
- **Local**: caminho absoluto da pasta (o agente pergunta se faltar).
- **Critério**: "com a saída real colada", "com testes verdes", "commite no git".
- O que NÃO precisa: por favor, contexto demais, medo de pedir demais.
  Se for criação, o plano aparece para você aprovar/editar antes de rodar.

**Complementos que multiplicam:**
- `/goal <objetivo>` no início da sessão — tudo que vier depois é guiado por ele;
- "lembre que…" — fatos permanentes (equipamentos, preferências, stacks);
- "consulte a biblioteca sobre X antes" — força o RAG antes de escrever.

---

## 1. 💻 Desenvolvimento de software completo

O arco inteiro sem sair do chat: pasta do projeto (pedida ou no pedido),
código em **Python, JavaScript/Node, TypeScript, Kotlin, Java**, arquiteturas
**MVVM, MVI, MDC, SaaS**, execução verificada, testes, git e CI/CD.

| Pedido exemplo | O que acontece |
|---|---|
| "quero iniciar um projeto: uma API REST de tarefas em Python" | pergunta o caminho → cria a pasta → skill codigo-python injetada → código + testes + commit |
| "crie uma calculadora node com POO em ~/projetos/calc, teste e commite" | skill codigo-javascript → arquivo + `node --test` + saída real + git |
| "monte o app Android em Kotlin com MVI em /media/…/app" | skills codigo-kotlin + arquitetura-mvi → estrutura Compose + reducer puro |
| "adicione autenticação JWT multitenant no projeto ~/projetos/saas" | skill arquitetura-saas → tenant_id, planos, refresh token |
| "configure o CI com GitHub Actions no projeto X" | skill cicd-github-actions → `.github/workflows/ci.yml` com cache e matrix |
| "leia o projeto em ~/projetos/app, explique a arquitetura e aponte riscos" | análise com git status + ambiente |
| "corrija o bug X do projeto Y: [erro colado]" | debug-sistematico + autocorreção → reproduz, corrige, re-testa, commit |

**Por que funciona**: o revisor cobra a seção `## Verificação` da skill que
casou (ex.: "testes verdes, saída real colada") — prometer não basta.

## 2. 📚 Estudar e produzir com seus livros (RAG local)

Coloque livros/docs em `~/.betterme/biblioteca/` (.md/.txt/.pdf), rode
`betterme rag` e:

- "consulte a biblioteca sobre [assunto] e explique como o livro ensina"
- "implemente o padrão X do livro [nome] no projeto Y"
- "compare o que diz o livro sobre A com a prática no projeto B"

O que entra no contexto é **trecho verbatim com a fonte** — se não estiver
no livro, ele diz que não está (não inventa citação).

## 3. 📊 Análise de dados e relatórios

- "analise o arquivo `~/relatorios/vendas.csv` e calcule os indicadores"
- "leia essa planilha e diga o que significam os números" (interpretação, não saída crua)
- "gere um relatório executivo em Markdown sobre [tema] com os dados de [arquivo]"
- Skills: analise-dados, powerbi-dax (medidas DAX/modelagem),
  producao-industrial (indicadores/OEE), excel-vba (gera macros para você
  aplicar no Excel)
- "leia este PDF e resuma" (doc-pdf)

## 4. ⏰ Autonomia de longo prazo (agendador)

- "toda manhã às 07:30 me traga o briefing: e-mails de hoje, agenda e uso da máquina" (skill briefing-diario)
- "monitore a pasta ~/entradas e processe todo arquivo novo que aparecer" (gatilho watch)
- "semanal, domingos 20:00: relatório de uso do disco com tendência"
- Tarefas falham → retry automático; "só quando ocioso" disponível;
  visão ao vivo na GUI; webhook para disparar de fora (`/api/hooks/<id>`)

## 5. 📧 E-mail e agenda (MCP, configurado uma vez)

- "resuma meu inbox de hoje e o que preciso responder" (resumo-inbox)
- "leia o e-mail do Fulano e me diga o que ele pede"
- "envie e-mail para fulano@x.com com [assunto/conteúdo]" (SMTP configurado)
- "o que tenho na agenda hoje/esta semana?" (Google Calendar, somente leitura)

## 6. 🖥️ Diagnóstico e gestão da própria máquina

- "faça uma busca geral no sistema e entenda meu uso do dispositivo" (1 chamada, 14 seções: CPU modelo/núcleos/threads/velocidade, velocidade da RAM, modelo do computador, uso atual, disco, memória, tops, GPU… — interpretado com dados REAIS)
- "o que está consumindo minha memória? devo me preocupar?"
- "onde foi meu espaço em disco? mostre os maiores diretórios"
- "meu notebook está lento — diagnostique e me diga o que fazer"
- Skill atalhos-shell: receitas de uma linha para o dia a dia

## 7. 🗂️ Organização e arquivos

- "organize minha pasta Downloads por tipo de arquivo" (organizador-arquivos, com backup antes)
- "renomeie essas fotos por data" · "junte esses PDFs e indexe na biblioteca"
- Toda edição gera backup automático — "restaura a versão anterior de X"

## 8. 🔎 Pesquisa na web com fonte

- "pesquise [assunto atual] e produza um relatório em arquivo com as fontes" (pesquisa-web + rag-citado)
- "leia esta URL e resuma" (web_fetch)
- "compare preços/especificações de X e me dê uma recomendação"

## 9. ✦ Skills da comunidade (o catálogo cresce sozinho)

- Baixe qualquer repo de skills (zip/pasta) para `~/Downloads` → vira nativa
  em minutos (autoscan), casa com seus pedidos e **delega** o padrão de entrega
- `betterme skills import <pasta/zip/URL>` para importar na hora
- "crie uma skill para [seu processo]" → o agente RASCUNHA e você aprova/edita

## 10. 🎛️ Operar a própria suíte

- `/goal`, `/tasks`, `/skills`, `/memoria`, `/tools`, `/ajuda` no chat
- Voz→texto no chat (STT) · conversas persistentes + export .md
- Aba Ollama: instalar/remover modelos, auto-atribuição
- `betterme doctor` (ambiente) · `betterme selftest` (qualidade com LLM real,
  incl. cenário de projeto) · `betterme update` (novas versões)

---

## Receitas completas (juntando tudo)

**Receita 1 — produto do zero à entrega:**
```
/goal construir e publicar meu app de controle de gastos
quero iniciar um projeto: app web TypeScript em /media/Arquivos/projetos/gastos
   (agente pergunta o caminho se você não der)
consulte a biblioteca sobre arquitetura MVC antes de estruturar
agora implemente as telas com o design system MDC
escreva os testes e deixe tudo verde
configure o CI com GitHub Actions e commite cada etapa
```

**Receita 2 — rotina matinal automática:**
```
lembre que meu e-mail principal é o da empresa e prefiro resumos curtos
toda manhã 07:30: briefing com inbox, agenda e um resumo de uso da máquina
```

**Receita 3 — estudar com seus livros e materializar:**
```
(ponha os PDFs em ~/.betterme/biblioteca e rode: betterme rag)
consulte a biblioteca sobre o capítulo de coroutines
explique como o livro ensina e me dê um exemplo
agora crie um projeto Kotlin de exercício em ~/projetos/kotlin-lab
   aplicando exatamente o padrão do livro, com testes
```

**Receita 4 — operador de sistemas pessoais:**
```
monitore ~/faturas e, quando chegar PDF novo, leia, extraia os dados
   e atualize a planilha ~/financas/controle.csv
semanal domingo 20:00: relatório de gastos com tendência do mês
```

---

## O que NÃO dá (limites honestos de hoje)

| Limite | Por quê / contorno |
|---|---|
| Tarefas gigantes em um só pedido | modelo 8B a 0,5–2,4 tok/s — divida em etapas (cada uma verificada); a compactação segura o contexto, o tempo é o limite |
| Compilar APK iOS/Android de verdade | requer SDK instalado na máquina; o Betterme gera o código Kotlin/Compose pronto |
| Controlar mouse/janelas do desktop | não há automação de GUI do sistema (só arquivos/comandos/web) |
| Navegar em sites com JavaScript pesado | web_fetch lê texto; SPAs podem vir rasas |
| Push/PR para GitHub sozinho | git push fica com você (por design — credencial); commits locais ele faz todos |
| Excel/VBA executando | o Linux não roda Excel — ele gera a macro/código para você aplicar |
| Voz dele (TTS) | ele ESCUTA (STT), ainda não fala |

---

## Regra de ouro

> O Betterme entrega **evidência**, não promessa: saída real colada, arquivo
> que existe, teste que passou, commit com hash. Se um pedido voltar sem
> evidência, reprove e peça de novo — o revisor da próxima tentativa cobra
> junto com você.

---

## v4.0.0 — Agentes: autonomia, especialistas e aprendizado

### 🎚 Níveis de autonomia (`betterme autonomia` ou `/autonomia` no chat)

| Nível | Comportamento |
|---|---|
| **cauteloso** | confirma criação, entrega E cada comando na TUI |
| **padrao** *(default)* | leitura livre; escrita aprovada (como sempre foi) |
| **autonomo** | encadeia sem parar nos gates soft; varredura pré-entrega |

Hard gates SEMPRE ativos: comandos perigosos, secrets/, escopo/sandbox e
a regra D2 (código/memória nunca vão a provedores gratuitos).

### 🧪 Especialistas

O cérebro invoca `especialista(nome, caso)` quando quer segunda opinião:
**revisor, debugger, pesquisador, seguranca**. Cada um roda com a skill
certa num contexto limpo e devolve veredito com **evidência checada em
disco** — sem evidência real, o veredito é descartado. Rodam no pool
gratuito (groq→gemini→mistral→…) com fallback local; cada especialista
passa por um **exame de competência** antes de ativar.

### 📚 Aprendizado (sempre com sua aprovação)

Missão complexa aprovada → rascunho de skill; missão reprovada → lição.
Veja e decida: `betterme aprendidos` → `aprovar <id>` / `rejeitar <id>`.
Transforme documento em skill: `betterme skills aprender <arquivo|URL|texto>`.
Decisões antigas: `betterme conversas buscar "termo"`.

### 👔 Gerente de código (Claude) — opt-in

`betterme gerente on --yes` (leia o aviso: o código da task vai à nuvem
Anthropic; memória e segredos nunca saem). O Betterme continua sendo o
cérebro que decide quando delegar. `betterme gerente off` volta ao 100% local.

### 🛡 Rotina pré-push

`betterme varredura` antes de publicar código (exit 1 = crítico bloqueia).
Nomes de terceiros: um por linha em `~/.betterme/varredura-nomes.txt`.

### 🧱 Sandbox de kernel

Se `bwrap` estiver instalado (`sudo apt install bubblewrap`), os comandos
do agente rodam isolados no kernel automaticamente; sem ele, a denylist
de aplicação segue valendo. `betterme doctor` mostra o estado.
