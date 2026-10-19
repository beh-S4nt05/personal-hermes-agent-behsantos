---
name: figma-design
description: Criar e modificar designs de aplicações no Figma usando o conector MCP (figma_create_design, figma_add_screen, figma_get_file, figma_list_files, figma_get_design_tokens). Use sempre que o pedido envolver Figma, UI, telas, protótipos, mockups ou design de apps.
---

# Design no Figma via conector MCP

Você tem ferramentas MCP conectadas ao Figma (nomes começam com `mcp_figma`).
Use-as para criar e modificar designs de aplicações.

## Fluxo recomendado (sempre nesta ordem)

1. **Leia os design tokens** com `figma_get_design_tokens` — cores, tipografia,
   espaçamento e regras de acessibilidade. Nunca invente cores fora dos tokens.
2. **Planeje antes de criar**: liste as telas necessárias com nome (kebab-case) e
   o propósito de cada uma. Apresente o plano ao usuário se o pedido for vago.
3. **Crie o design** com `figma_create_design`:
   - `name`: nome legível (ex.: "App de Tarefas")
   - `description`: objetivo do app em 1–2 frases
   - `screens`: lista de telas iniciais (ex.: ["login", "home", "detalhe-tarefa"])
4. **Refine** adicionando telas ou componentes com `figma_add_screen`
   (argumentos: `file_key`, `name` da tela, `components`).
5. **Confirme** o resultado com `figma_get_file` e reporte ao usuário:
   chave do arquivo, telas criadas e componentes de cada uma.

## Convenções de design (obrigatórias)

- Auto-layout vertical em todas as telas; padding de 24px; grid de 8pt.
- Nomes de telas em kebab-case: `home`, `detalhe-produto`, `configuracoes`.
- Componentes descritos em kebab-case: `header`, `card-produto`,
  `botao-primario`, `input-busca`, `lista-itens`, `rodape`, `tab-bar`.
- Toda tela mobile deve ter: `header` + área de conteúdo + `rodape` ou `tab-bar`.
- Acessibilidade: contraste AA (≥ 4.5:1 para texto), alvos de toque ≥ 44px.
- Paleta: use SOMENTE os tokens retornados por `figma_get_design_tokens`.

## Exemplos de chamadas

Criar um app:

```json
{"name": "App de Tarefas", "description": "Lista de tarefas com prioridades e notificações",
 "screens": ["login", "lista-tarefas", "detalhe-tarefa", "configuracoes"]}
```

Adicionar tela a um design existente (file_key retornado no passo 3):

```json
{"file_key": "figma-a1b2c3d4", "name": "relatorios",
 "components": ["header", "filtro-periodo", "grafico-semanal", "card-resumo"]}
```

## Erros comuns

- `arquivo não encontrado` → confira a chave com `figma_list_files`.
- Pedido vago ("faz um app aí") → proponha 3 ideias com telas antes de criar.
