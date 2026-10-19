---
name: ui-design-system
description: Sistema de design para interfaces — paleta de cores, escala tipográfica, espaçamento em grid 8pt, raios, elevação, estados e checklist de acessibilidade. Use ao criar ou avaliar qualquer interface, componente ou protótipo.
---

# Sistema de Design (UI)

Referência para criar interfaces consistentes. Aplique estas regras em qualquer
design (Figma, HTML/CSS, relatórios) mesmo sem outras instruções.

## Paleta (60-30-10)

- **60% neutra**: fundo, superfícies, texto.
- **30% suporte**: cards, bordas, fundos secundários.
- **10% destaque**: UMA cor primária para ações e destaques.

| Papel | Exemplo | Uso |
|---|---|---|
| primária | `#7C5CFF` | botões, links, foco |
| fundo | `#0B0E14` / `#FFFFFF` | página |
| superfície | `#121826` / `#F5F7FB` | cards, painéis |
| texto | `#D7E0EE` / `#1A2233` | conteúdo |
| texto-suave | `#8FA0B8` / `#5B6B82` | legendas, metadados |
| sucesso | `#2BD576` | confirmações |
| atenção | `#FFB454` | avisos |
| erro | `#FF5470` | destructive, validação |

Nunca use cores puras (`#FF0000`, `#0000FF`) — ajuste saturação/contraste.

## Tipografia

Escala limitada (máx. 5 níveis): 32/24/20/16/13 px. Peso 700 títulos, 400 corpo,
600 ênfase. Altura de linha: 1.2 (títulos) e 1.5 (corpo). Máx. ~70 caracteres
por linha.

## Espaçamento e layout

Grid de **8pt**: use múltiplos (8, 16, 24, 32, 48). Padding de card ≥ 16px.
Raios: botão 10px, card 14px, input 9px — coerentes em todo o app.
Elevação: no máx. 2 níveis de sombra; superfícies escuras usam borda + sombra sutil.

## Estados (todo componente interativo precisa dos 5)

1. padrão · 2. hover · 3. foco (anel visível de 2px na cor primária) ·
4. ativo/selecionado · 5. desabilitado (opacidade ~45%)

## Componentes base para qualquer app

`header`, `tab-bar` ou `rodape`, `botao-primario`, `botao-secundario`,
`input-texto`, `input-busca`, `card`, `lista-itens`, `avatar`, `badge`,
`modal`, `toast`, `estado-vazio`, `skeleton-loading`.

## Checklist de acessibilidade (revise antes de entregar)

- [ ] Contraste ≥ 4.5:1 (texto) e ≥ 3:1 (elementos de interface)
- [ ] Alvos de toque ≥ 44×44px
- [ ] Não usa só cor para transmitir informação (ícone + texto)
- [ ] Foco visível navegando por Tab
- [ ] Textos alternativos para imagens
- [ ] Botões com rótulo descritivo (não só "aqui", "clique")

## Design tokens em JSON (para exportar/integrar)

```json
{
  "color": {"primary": "#7C5CFF", "bg": "#0B0E14", "surface": "#121826",
            "text": "#D7E0EE", "muted": "#8FA0B8", "success": "#2BD576",
            "warning": "#FFB454", "danger": "#FF5470"},
  "font": {"family": "Inter", "scale": {"h1": 32, "h2": 24, "h3": 20, "body": 16, "caption": 13}},
  "space": [8, 16, 24, 32, 48],
  "radius": {"button": 10, "card": 14, "input": 9}
}
```
