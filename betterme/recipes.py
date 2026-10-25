"""Receitas prontas: automações úteis que o operador ativa com 1 clique."""
from __future__ import annotations

RECIPES = [
    {
        "id": "noticias-diarias",
        "icon": "📰",
        "title": "Resumo diário de notícias",
        "desc": "Pesquisa notícias do dia, resume e salva relatório no workspace.",
        "input": ("Faça um resumo das principais notícias de hoje (Brasil e mundo) "
                  "usando web_search, escreva o relatório em relatorio-noticias-YYYY-MM-DD.md "
                  "no workspace e guarde os 3 fatos mais importantes na memória."),
        "when": "diário 08:30",
        "agent": "betterme",
    },
    {
        "id": "saude-sistema",
        "icon": "🩺",
        "title": "Saúde do sistema (semanal)",
        "desc": "Disco, memória, top processos e atualizações pendentes num relatório.",
        "input": ("Rode um diagnóstico completo da máquina (df -h, free -h, uptime, "
                  "top processos por CPU/memória) e salve um relatório em "
                  "relatorio-sistema-YYYY-MM-DD.md com alertas de disco/memória."),
        "when": "seg 09:00",
        "agent": "betterme",
    },
    {
        "id": "limpeza-backups",
        "icon": "🧹",
        "title": "Limpeza de backups antigos",
        "desc": "Apaga backups com mais de 30 dias e relata o espaço liberado.",
        "input": ("Liste os backups (ferramenta backups, action=list) e apague os "
                  "com data anterior a 30 dias usando run_command; depois relate "
                  "quantos arquivos e quanto espaço foi liberado."),
        "when": "dom 06:00",
        "agent": "betterme",
    },
    {
        "id": "backup-workspace",
        "icon": "💾",
        "title": "Backup semanal do workspace",
        "desc": "Empacota o workspace em .tar.gz com a data no nome.",
        "input": ("Crie um arquivo tar.gz do workspace inteiro em "
                  "backup-workspace-YYYY-MM-DD.tar.gz dentro do workspace e confirme "
                  "o tamanho final (du -h)."),
        "when": "sex 18:00",
        "agent": "betterme",
    },
    {
        "id": "vigia-disco",
        "icon": "👁",
        "title": "Vigia de disco (a cada 6h)",
        "desc": "Alerta se qualquer volume passar de 90% de uso.",
        "input": ("Verifique o uso de disco (df -h). Se alguma partição estiver "
                  "acima de 90%, escreva um alerta claro; caso contrário responda "
                  "que está tudo em ordem."),
        "when": "a cada 6h",
        "agent": "betterme",
    },
    {
        "id": "memoria-revision",
        "icon": "📔",
        "title": "Revisão da memória (semanal)",
        "desc": "O agente organiza e limpa os fatos guardados na memória.",
        "input": ("Liste os fatos da memória, remova os desatualizados/irrelevantes "
                  "com esquecer e escreva um resumo do que ficou."),
        "when": "sab 10:00",
        "agent": "betterme",
    },
    {
        "id": "n8n-fluxo-diario",
        "icon": "⛓",
        "title": "Disparar fluxo do n8n",
        "desc": "Lista os workflows do n8n local, dispara o indicado e "
                "relata a resposta (integração ⛓ Betterme ↔ n8n).",
        "input": ("Use a ferramenta fluxos_listar para ver os workflows do "
                  "n8n local, escolha o mais relevante (prefira o que eu "
                  "indicar na época) e dispare com fluxos_chamar usando o "
                  "path do webhook; relate a resposta recebida."),
        "when": "diário 09:00",
        "agent": "betterme",
    },
]
