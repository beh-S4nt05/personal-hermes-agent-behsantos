---
name: powerbi-dax
description: Power BI, powerbi, DAX, medida, medidas, modelo dimensional, tabela de calendário, star schema, dashboard de BI, time intelligence e indicadores no Power BI.
---

# Power BI e DAX (padrões que funcionam)

## Modelo
- Star schema: fatos (números) e dimensões (contexto) separadas; relate
  pelo ID, nunca por nome.
- Tabela de calendário dedicada (DateKey) e `Mark as date table`.

## DAX essencial
- Medida, não coluna calculada, para tudo que agrega.
- Time intelligence exige calendário: `TOTALYTD(...)`.
- Nomes de medida claros e com unidade ("Vendas Líquidas R$").
- Evite filter piramidal — prefira `CALCULATE` com contexto explícito.

## Entregando
- Toda medida vem com: nome, fórmula completa e em UMA linha o que ela
  calcula.
- Se a pergunta for de modelagem, desenhe as tabelas e relacionamentos
  (texto) antes do DAX.
