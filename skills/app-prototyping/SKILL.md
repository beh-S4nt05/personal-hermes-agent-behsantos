---
name: app-prototyping
description: Estruturar protótipos de aplicações — mapa de telas, fluxos de usuário, wireframes e componentes por tela. Use quando o pedido envolver criar um app, protótipo, MVP ou definir telas e navegação, antes de partir para o visual.
---

# Prototipagem de aplicações

 Método para transformar uma ideia em um protótipo completo. Aplique ANTES do
visual (o visual vem da skill ui-design-system e a execução no Figma vem da
skill figma-design).

## Passo 1 — Entender (pergunte se faltar)

- Quem usa e para quê? (persona + objetivo principal)
- Plataforma: mobile, desktop, web responsiva?
- Ação mais importante do app? (uma só!)

## Passo 2 — Mapa de telas

Liste as telas mínimas para o fluxo principal (MVP — resista a adicionar mais):

```
app/
├── onboarding        (opcional, máx. 3 passos)
├── login
├── home              (estado vazio + estado com dados)
├── detalhe-item
├── criar-editar-item
└── configuracoes
```

Regra: se uma tela não serve ao fluxo principal nem a um caso de erro, corte.

## Passo 3 — Fluxos

Documente cada fluxo como sequência tela → ação → resultado:

```
login → [entrar] → home
login → [esqueci a senha] → recuperar-senha → [enviar] → login (toast)
home → [item] → detalhe-item → [editar] → criar-editar-item → [salvar] → detalhe-item
```

Sempre inclua: fluxo feliz, fluxo de erro e estado vazio (primeiro uso).

## Passo 4 — Componentes por tela

Para cada tela, liste os componentes (kebab-case) e o que fazem:

```
home:
  - header (título + avatar)
  - input-busca
  - lista-itens (card: título, subtítulo, badge de status)
  - botao-flutuante-criar
  - tab-bar (home, buscar, perfil)
```

## Passo 5 — Wireframe antes de hi-fi

Descreva o wireframe em texto (layout, hierarquia, ordem) e valide com o
usuário. Só depois aplique o design system.

## Passo 6 — Critérios de pronto

- [ ] Fluxo principal funciona de ponta a ponta
- [ ] Estados: vazio, carregando (skeleton), erro, sem-conexão
- [ ] Navegação: usuário nunca fica preso numa tela sem saída
- [ ] Ação principal visível sem rolagem (mobile)
- [ ] Nomes de telas/componentes em kebab-case consistentes

## Entrega

Apresente: mapa de telas, fluxos, componentes por tela e o próximo passo
sugerido (ex.: criar o design no Figma com a skill figma-design).
