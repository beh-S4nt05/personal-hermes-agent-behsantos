---
name: doc-pdf
description: Ler e extrair conteúdo de PDF — pdf, páginas, texto do pdf, tabelas do pdf, documento digitalizado, scanner, ocr, tesseract e conversão de documento para texto.
---

# PDF e OCR (via comandos locais)

## Pipeline
1. **Texto nativo?** `pdftotext -layout arquivo.pdf -` (rápido e fiel).
2. **Tabela?** `python` com pandas+pdfplumber, ou `pdftotext -layout` e
   parse — cole o resultado bruto antes de interpretar.
3. **Digitalizado (sem texto)?** OCR: `tesseract entrada.png saida -l por`
   (extraia a página com `pdftoppm -png -r 200 arquivo.pdf pagina`).
4. **Sem as ferramentas instaladas?** Diga o que falta e COMO instalar
   (`apt install poppler-utils tesseract-ocr-por`), e pergunte se o
   operador quer instalar (é criação de pacote — pode exigir aprovação).

## Regras
- Cole trechos REAIS do extraído; nunca resuma PDF que não leu.
- Páginas: sempre diga de onde veio o trecho (página N).
