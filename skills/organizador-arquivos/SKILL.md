---
name: organizador-arquivos
description: Organizar pastas bagunçadas como downloads e área de trabalho — separar arquivos por tipo (documentos, planilhas, imagens, instaladores, compactados), achar duplicados por hash, renomear em lote e limpar a bagunça com segurança. Use quando o pedido envolver organizar pastas, separar arquivos, ordenar downloads, desktop, limpar bagunça ou remover duplicados.
---

# Organizador de arquivos

Bagunça se resolve com método: LISTAR → propor → mover → relatar.
Nunca mova às cegas.

## Fluxo

1. **Levantar** o que existe (por extensão):
   `find PASTA -maxdepth 1 -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn`
2. **Propor** o destino (se cria pastas/move = tarefa de CRIAÇÃO:
   plano passa pelo portão do operador):
   - documentos (pdf, docx, txt, md) · planilhas (xlsx, csv) ·
     imagens (png, jpg, webp) · instaladores (deb, AppImage, run) ·
     compactados (zip, tgz, rar)
3. **Executar** por tipo: `mkdir -p` + `mv PASTA/*.pdf PASTA/documentos/`
4. **Duplicados**: mesmo tamanho antes (`find -size`), depois confirme
   com `md5sum`; apagar SÓ com confirmação explícita do operador.

## Zonas intocáveis (JAMAIS mover/apagar)

- `~/.hermes/` (dados do agente) e `~/.hermes/secrets/`
- `~/.ssh/`, `~/.config/`, `~/.gnupg/`
- qualquer pasta de sistema (`/etc`, `/usr`, `/var`, `/boot`)

## Relatório final (sempre)

- N arquivos movidos por pasta · M duplicados encontrados
  (X confirmados e apagados) · espaço liberado (`du` antes/depois)
