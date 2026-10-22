---
name: arquitetura-mdc
description: "Material Design Components (MDC): design system com theming, componentes, elevação e acessibilidade para web e Android. Use quando a tarefa envolver mdc, material design, material components, theming, tema claro escuro, design system, componentes google ou ui padronizada."
---
# MDC — Material Design Components

## O que é
Design system do Google: vocabulário pronto de componentes + regras de
tema → UI consistente sem reinventar botão/todo dia.

## Pilares
1. **Theming por tokens** (não cor fixa): primary, on-primary, surface,
   background — troca de tema = troca de tokens (claro/escuro/high-contrast).
2. **Tipografia escala** (display…caption) e **elevação** (níveis 0-5).
3. **Componentes** prontos e acessíveis: Button, TextField, Card, Dialog,
   NavigationRail, Snackbar, Chip, FAB.

## Por ecossistema
- **Web**: `@material/web` (MWC, web components) ou MDC-React (RMWC).
- **Android**: `com.google.android.material` + Material 3 (`Theme.Material3`).
- **Compose**: `MaterialTheme` + componentes M3 nativos.

## Regras de sênior
- SEMPRE dark mode junto do claro (tokens, não if/else de cor).
- Estado de componente: enabled/disabled/error entra pelo token.
- Acessibilidade: contraste AA, `aria-label`, alvo de toque ≥ 48dp.
- Espaçamento em múltiplos de 4dp (grid de 8).

## Armadilhas
- Cor hardcoded (`#7C5CFF`) — quebra theming; use o token.
- Misturar versões M2/M3 no Android.
- Snackbar pra erro crítico (é efêmero) — use dialog/banner.

## Verificação
Tema escuro renderiza certo · contraste AA · mesmos componentes em toda a UI.
