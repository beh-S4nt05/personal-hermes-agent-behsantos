---
name: pesquisa-web
description: Pesquisar na internet, aprender com os resultados e produzir relatórios com fontes. Use quando a tarefa envolver "pesquise", "procure na internet", "notícias de hoje", "o que há de novo", "compare preços/produtos", "monitoramento" ou qualquer pergunta que precise de informação atual.
---

# Pesquisa e aprendizado na web

Você tem as ferramentas `web_search` (busca DuckDuckGo) e `web_fetch` (abre a
página e devolve o texto limpo). Esta skill define COMO pesquisar bem e
transformar o resultado em aprendizado útil.

## Princípios

1. **Nunca invente**: se a pergunta depende de informação atual (data, preço,
   notícia, versão, evento) e você não tem certeza, PESQUISE antes de
   responder.
2. **Cite as fontes**: toda afirmação que veio da web leva o endereço — em
   linha ou numa lista "Fontes:" no fim da resposta.
3. **Diga quando não achou**: se a busca não retornar nada útil, informe
   honestamente — não preencha lacunas com suposição.

## Fluxo de pesquisa

1. Formule a busca sendo específico ("ollama modelos leves 7b" em vez de
   "ia"); em temas técnicos, testar também em inglês costuma ajudar.
2. `web_search` → analise títulos e resumos; escolha as 2–3 fontes mais
   relevantes (prefira documentação oficial e sites conhecidos).
3. `web_fetch` nas fontes escolhidas para ler o conteúdo completo.
4. Sintetize: resposta direta primeiro, detalhes depois, fontes no fim.

## Aprendizado (memorizar descobertas)

- Fatos que o usuário mandar lembrar, ou que forem claramente úteis no futuro
  (preferências, contexto do curso/professores, dados da máquina) → guarde
  com `lembrar` (um fato por chamada, frase curta).
- Não despeje pesquisa na memória: guarde CONCLUSÕES úteis, não links.

## Pesquisa agendada / monitoramento (tarefas ⏰)

Quando a tarefa for periódica ("todas as manhãs, notícias de tecnologia"):

1. Pesquise e escreva um relatório em `relatorios/YYYY-MM-DD-<tema>.md`
   (com `write_file`): data, tema, bullets das descobertas e fontes.
2. Se já existir relatório anterior do mesmo tema (procure com `list_dir` /
   `read_file`), comece destacando "o que mudou desde a última pesquisa".
3. A resposta final da tarefa deve ser o resumo dos pontos principais.

Modelo mínimo de relatório:

    # <tema> — YYYY-MM-DD
    - **Tópico 1**: resumo de 1–2 linhas (fonte: https://…)
    - **Tópico 2**: …
    ## O que mudou desde a última pesquisa
    - …
