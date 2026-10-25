# ⚙ n8n passo a passo — do zero à automação com o Betterme

> Guia para quem nunca usou o n8n. Tudo **local**: nada sai da sua
> máquina, nenhuma conta em nuvem, uso pessoal/interno grátis
> (Sustainable Use License). Versão: 6.3.1.

O n8n é um editor visual de automações ("arrasta-e-solta nós e liga
fios"). O Betterme o instala **dentro do seu data-dir** e conversa com
ele nos dois sentidos:

```
┌──────────────────┐   "dispare o fluxo X"    ┌──────────────────┐
│  Betterme (chat) │ ───────────────────────▶ │  n8n (workflow)  │
│      :8080       │   POST /webhook/<path>   │      :5678       │
│                  │ ◀─────────────────────── │                  │
└──────────────────┘   POST /api/hooks/<id>   └──────────────────┘
        ▲                   (dispara o agente)          │
        └──────────────── o n8n manda, o cérebro faz ───┘
```

---

## 0. O que você precisa

- Betterme instalado (`install.py`) e o **Node.js na máquina** com
  versão **entre 20.19 e 24.x** — `node -v` para conferir
  (`betterme fluxos status` já mostra isso).
- Uns 300 MB de disco para o n8n.
- Nada mais: sem cartão, sem conta em serviço nenhum.

## 1. Instalar o n8n local

```bash
betterme fluxos setup      # instala dentro do data-dir do Betterme
```

Quem preferir carregar tudo de uma vez (playwright, Ollama, modelo,
n8n e doctor final):

```bash
python install.py --full           # tudo
python install.py --full --skip-n8n   # tudo, menos o n8n
```

## 2. Subir o n8n e criar a conta local

```bash
betterme fluxos start       # sobe o serviço em http://127.0.0.1:5678
betterme fluxos abrir       # abre o editor no navegador (opcional)
```

No **primeiro acesso** o n8n pede um e-mail e uma senha para criar o
*dono* do servidor — é uma conta **local**, guardada no seu data-dir;
pode usar qualquer e-mail, nada é enviado para fora.

## 3. Primeiro workflow (com template pronto)

No editor do n8n (aba **⚙ Fluxos** do Betterme, ou
`http://127.0.0.1:5678`):

1. Copie o **Template A** (JSON abaixo).
2. No editor: menu **⋯** (canto superior) → **Import from clipboard**
   → cole → confirme.
3. Aparecem 2 nós: um **Webhook** (porta de entrada) e um
   **Respond to Webhook** (resposta). Clique em cada um para explorar.
4. Ative o workflow com o botão **Active** (toggle, canto superior
   direito). **Só workflows ativos respondem no Production URL.**

```json
{
  "name": "Betterme eco (teste)",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "betterme-eco",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "eco-entrada",
      "name": "Recebe do Betterme",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 0],
      "webhookId": "betterme-eco"
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "{\"ok\": true, \"msg\": \"o n8n recebeu!\", \"dica\": \"edite este nó para devolver o que quiser\"}",
        "options": {}
      },
      "id": "eco-resposta",
      "name": "Responde ao Betterme",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1,
      "position": [220, 0]
    }
  ],
  "connections": {
    "Recebe do Betterme": {
      "main": [
        [
          {
            "node": "Responde ao Betterme",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1"
  }
}
```

## 4. Disparar do chat do Betterme

No chat do Betterme (GUI, aba 💬), peça:

> dispare o fluxo betterme-eco

O cérebro usa a ferramenta `fluxos_chamar`, que faz
`POST http://127.0.0.1:5678/webhook/betterme-eco` e **espera a
resposta** (até 60 s). O que o nó *Respond to Webhook* devolver
aparece na conversa. Para workflows mais longos, acrescente mais nós
entre a entrada e a resposta — o chat espera.

## 5. Listar workflows pela API

Para o terminal enxergar os workflows do n8n:

1. No editor: **Settings → n8n API → Create an API key** → copie.
2. No terminal:

```bash
betterme fluxos apikey SUA-CHAVE   # salva em secrets/n8n.key (chmod 600)
betterme fluxos listar             # nome, nº de nós, ativo/inativo, id
```

## 6. Sentido inverso: o n8n dispara o Betterme

Aqui o fluxo manda e o **cérebro** obedece:

1. No Betterme (GUI → aba **Tarefas**), crie uma tarefa com gatilho
   **webhook** e o que você quer que o agente faça (ex.: *"resuma os
   e-mails de hoje"*). A criação responde com a URL de disparo:
   `POST http://127.0.0.1:8080/api/hooks/<id-da-tarefa>`.
2. No n8n, importe o **Template B** abaixo e **troque a URL do nó
   HTTP** pelo `.../api/hooks/<id>` da sua tarefa.

```json
{
  "name": "Dispara tarefa do Betterme",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "gatilho-n8n",
        "responseMode": "lastNode",
        "options": {}
      },
      "id": "gat-entrada",
      "name": "Quando algo acontecer",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 0],
      "webhookId": "gatilho-n8n"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://127.0.0.1:8080/api/hooks/TROQUE-PELO-ID-DA-TAREFA",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\"mensagem\": \"disparado pelo n8n\"}",
        "options": {}
      },
      "id": "gat-http",
      "name": "Chama o Betterme",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [220, 0]
    }
  ],
  "connections": {
    "Quando algo acontecer": {
      "main": [
        [
          {
            "node": "Chama o Betterme",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1"
  }
}
```

> **Autenticação ativa?** Se o GUI do Betterme pedir token no acesso,
> acrescente `?token=SEU-TOKEN` na URL do nó HTTP.
> **Por horário?** Troque o primeiro nó por um **Schedule Trigger**
> (ex.: todos os dias 08:00) — o resto continua igual.

## 7. Problemas comuns

| Sintoma | Causa provável | Correção |
|---|---|---|
| `webhook respondeu 404` | workflow **inativo** ou path errado | ative o toggle **Active**; confira o Production URL |
| `n8n não respondeu` | serviço parado | `betterme fluxos start` |
| `sem API key` no `listar` | chave não salva | `betterme fluxos apikey <chave>` |
| `resposta inesperada da API` | chave inválida/revogada | gere outra em Settings → n8n API |
| setup falha no Node | versão fora de 20.19–24.x | atualize o Node.js (`node -v`) |
| hook responde 409 | GUI do Betterme fechado (agendador) | deixe `betterme server` rodando |
| hook responde 404 | id errado ou tarefa não é webhook | recrie a tarefa com gatilho webhook |
| porta 5678 ocupada | outro n8n na máquina | pare o outro ou mude a porta |

## 8. Onde fica tudo (e como remover)

- n8n, workflows e conta: dentro do **data-dir** do Betterme
  (`betterme fluxos status` mostra o caminho exato).
- API key: `secrets/n8n.key` no data-dir, permissão 600.
- Remoção completa: `betterme fluxos remover` (apaga o n8n e tudo que
  ele criou — o Betterme continua intacto).

**Privacidade**: o n8n roda na sua máquina, os workflows ficam no seu
disco e a integração usa apenas `127.0.0.1`. Se um workflow seu
consultar serviços externos (e-mail, APIs públicas), isso é decisão
sua, nó a nó — o Betterme continua não enviando memória nem dados
pessoais a provedor nenhum (D2).
