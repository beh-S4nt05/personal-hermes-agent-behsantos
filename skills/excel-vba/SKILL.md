---
name: excel-vba
description: Excel, planilha e VBA — macro, macros, userform, formulário, módulo, sub, tratamento de erro no VBA, proteção de planilha e compatibilidade de versão.
---

# Excel e VBA (código que não quebra na máquina do outro)

## Regras
1. **Option Explicit** sempre; variáveis declaradas.
2. **Tratamento de erro**: `On Error GoTo ErrHandler` nas Subs principais;
  nada de `On Error Resume Next` solto.
3. **Nunca use Select/Activate** — referencie objetos (`ws.Range(...)`).
4. **Performance**: desligue `ScreenUpdating/Calculation` no início e
   RESTAURE no fim (mesmo com erro — Finally via handler).
5. **Compatibilidade**: nada de recurso só do 365 sem avisar; evite
   referências frágeis a bibliotecas.
6. **Proteção**: senha de VBA e de planilha combinadas com o usuário, nunca
   hardcode de senha no módulo.

## Entregando
Código completo + onde colar (módulo/form) + como testar em 30 segundos.
