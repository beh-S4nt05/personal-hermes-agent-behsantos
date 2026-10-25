---
name: briefing-diario
description: Resumo único da manhã com tudo que importa — agenda de hoje, contagem de e-mails não lidos, notícias principais, tarefas agendadas do Betterme e estado da máquina (disco, bateria, atualizações). Use quando o pedido envolver briefing, resumo da manhã, como está o dia, o que tenho hoje, panorama ou start do dia.
---

# Briefing diário

Uma passada, um resumo curto. O operador lê 8 linhas e sabe o dia.

## O que juntar (na ordem)

1. **Data e dia da semana** (`date "+%A, %d/%m/%Y"`).
2. **Agenda de hoje** — ferramentas agenda_* (SOMENTE LEITURA):
   compromissos com horário e local, em ordem.
3. **E-mails não lidos** — ferramentas email_*: só o NÚMERO e os 3
   remetentes mais recentes (não abrir tudo).
4. **Tarefas ⏰ do Betterme** — o que está agendado para hoje.
5. **Estado da máquina** — disco (`df -h /`), bateria
   (`cat /sys/class/power_supply/BAT*/capacity` se existir),
   atualizações pendentes se rápido de ver.
6. **3 manchetes** (só se houver acesso à web) — skill pesquisa-web,
   uma linha cada.

## Formato da resposta

```
☀️ quarta, 22/10/2026
🗓 09:00 Reunião X (sala 3) · 14:00 Visitante (recepção)
📧 12 não lidos (últimos: João, Maria, Banco)
⏰ Betterme: backup diário 18:00
💻 disco 61% (sobra 180 GB) · bateria 84%
🌐 1. … 2. … 3. …
```

## Autonomia

Pode ser AGENDADA (⏰ "todo dia 8:00, briefing") — roda sozinha e o
resumo chega pronto. Sem perguntas, sem confirmar, direto ao ponto.
