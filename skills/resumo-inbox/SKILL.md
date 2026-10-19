---
name: resumo-inbox
description: Resumir e-mails do Gmail e atividades do Google Classroom em relatórios periódicos. Use quando a tarefa envolver "resumo dos e-mails", "o que os professores passaram", "atividades do classroom", "resumo da caixa de entrada" ou relatórios agendados dessas fontes.
---

# Resumo de e-mail (Gmail) e Google Classroom

## Pré-requisito: conector Gmail (MCP)

O resumo de e-mails usa as ferramentas MCP do Gmail (nomes começam com
`mcp_gmail`). Se elas não aparecerem, o conector não está configurado —
avise o operador para adicionar no config.yaml o servidor MCP oficial do
Google (Gmail, `https://gmailmcp.googleapis.com/mcp/v1`) e reiniciar.
Sem o conector, NÃO invente o conteúdo dos e-mails: diga claramente que
precisa do conector configurado.

## Fluxo do resumo de e-mail

1. Busque as mensagens recentes (últimas 24h ou desde o último resumo):
   ferramenta de busca do Gmail com consulta `newer_than:1d`
   (ou `in:inbox newer_than:1d`).
2. Agrupe por remetente/assunto e priorize: pessoal direto > financeiro >
   trabalho/escola > newsletters/promoções.
3. Produza o relatório neste formato:

```
📬 RESUMO DO E-MAIL — <data>
──────────────────────────────
🔴 Precisam de resposta (N)
  • [remetente] assunto — 1 linha do que pede
🟡 Importantes (N)
  • …
🔵 Informativos (N)
  • [remetente] assunto (agrupados)
🏫 Escola/Classroom (N)
  • [professor/turma] atividade ou aviso
💡 Sugeridos para arquivar: N newsletters/promoções
```

## Google Classroom

Não há conector MCP oficial do Classroom. Caminhos possíveis, em ordem:

1. **E-mails do Classroom** (mais simples): as notificações do Classroom
   chegam por e-mail (remetente contém `classroom.google.com`). No resumo
   do Gmail, filtre e agrupe essas mensagens num bloco "🏫 Escola".
2. **API do Classroom**: se o operador tiver credenciais OAuth
   (`classroom.googleapis.com`, escopos `classroom.courses.readonly` e
   `classroom.student-submissions.me.readonly`), use `run_command` com
   `curl` + token para listar cursos e atividades pendentes. Sem
   credenciais, peça ao operador para configurar — não invente dados.

## Regras

- Nunca invente e-mails, notas ou atividades — relate apenas o que as
  ferramentas retornaram.
- Em tarefas agendadas, mantenha o relatório objetivo (menos de 40 linhas).
- Termine com "próximos passos" só se houver ações claramente necessárias.
