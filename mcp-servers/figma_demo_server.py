#!/usr/bin/env python3
"""Servidor MCP de demonstração do Figma (transporte stdio, sem dependências).

Expõe ferramentas no formato Model Context Protocol para criar/modificar
designs de aplicações — perfeito para demonstrar e testar o conector MCP do
Betterme Agent sem precisar de conta Figma nem chave de API.

Também serve como exemplo/commentário de referência de como escrever um
servidor MCP em Python puro: JSON-RPC 2.0 por linhas no stdin/stdout.

Os designs criados são salvos como JSON em $HERMES_WORKDIR/figma-designs
(padrão: ./figma-designs).
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

SERVER_NAME = "figma-demo"
SERVER_VERSION = "1.0.0"
BASE = Path(os.environ.get("HERMES_WORKDIR", ".")) / "figma-designs"

DESIGN_TOKENS = {
    "cores": {
        "primaria": "#7C5CFF",
        "primaria-escura": "#5B3FD4",
        "fundo": "#0B0E14",
        "superficie": "#121826",
        "texto": "#D7E0EE",
        "texto-suave": "#8FA0B8",
        "sucesso": "#2BD576",
        "atencao": "#FFB454",
        "erro": "#FF5470",
    },
    "tipografia": {
        "familia": "Inter",
        "escala": {
            "h1": "32px/700",
            "h2": "24px/600",
            "corpo": "16px/400",
            "legenda": "13px/400",
            "mono": "ui-monospace 13px",
        },
    },
    "espacamento": "grid de 8pt (8, 16, 24, 32, 48)",
    "raios": {"botao": "10px", "card": "14px", "input": "9px"},
    "elevacao": ["0 1px 3px rgba(0,0,0,.3)", "0 8px 30px rgba(0,0,0,.45)"],
    "acessibilidade": {
        "contraste_texto": "AA — razão >= 4.5:1",
        "alvo_toque": ">= 44px",
    },
}

TOOLS = [
    {
        "name": "figma_list_files",
        "description": "Lista os arquivos de design (projetos) disponíveis no Figma.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "figma_get_file",
        "description": "Retorna a estrutura completa de um arquivo de design (telas e componentes).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "Chave do arquivo (ex.: figma-abc123)"}
            },
            "required": ["file_key"],
        },
    },
    {
        "name": "figma_create_design",
        "description": (
            "Cria um novo design/aplicação no Figma com telas e componentes. "
            "Use para prototipar apps: informe nome, descrição e a lista de telas."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome do design (ex.: App de Tarefas)"},
                "description": {"type": "string", "description": "Descrição/objetivo do aplicativo"},
                "screens": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Telas iniciais (ex.: [\"login\", \"home\", \"detalhe\"])",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "figma_add_screen",
        "description": "Adiciona uma nova tela a um design existente, com componentes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {"type": "string"},
                "name": {"type": "string", "description": "Nome da tela (kebab-case, ex.: configuracoes)"},
                "components": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Componentes da tela (ex.: [\"header\", \"card\", \"botao-primario\"])",
                },
            },
            "required": ["file_key", "name"],
        },
    },
    {
        "name": "figma_get_design_tokens",
        "description": "Retorna os design tokens do sistema (cores, tipografia, espaçamento, raios, acessibilidade).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ------------------------------------------------------------------ helpers

def _load(file_key: str) -> dict:
    path = BASE / f"{file_key}.json"
    if not path.exists():
        raise ValueError(f"arquivo não encontrado: {file_key} (veja figma_list_files)")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(design: dict) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    path = BASE / f"{design['key']}.json"
    path.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_components(screen_name: str) -> list[str]:
    return ["header", "conteudo", "rodape"]


def _call_tool(name: str, args: dict) -> str:
    if name == "figma_list_files":
        BASE.mkdir(parents=True, exist_ok=True)
        files = []
        for f in sorted(BASE.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                files.append(
                    {
                        "key": d.get("key"),
                        "name": d.get("name"),
                        "screens": len(d.get("screens", [])),
                        "updated_at": d.get("updated_at"),
                    }
                )
            except Exception:
                continue
        return json.dumps(
            {"arquivos": files, "dica": "use figma_get_file com a chave 'key'"},
            ensure_ascii=False,
            indent=2,
        )

    if name == "figma_get_file":
        d = _load(str(args.get("file_key", "")))
        return json.dumps(d, ensure_ascii=False, indent=2)

    if name == "figma_create_design":
        design = {
            "key": "figma-" + uuid.uuid4().hex[:8],
            "name": str(args.get("name", "Sem nome")),
            "description": str(args.get("description", "")),
            "tokens_aplicados": True,
            "auto_layout": True,
            "grid": "8pt",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "screens": [],
        }
        for s in args.get("screens") or []:
            sname = str(s)
            design["screens"].append(
                {
                    "id": "screen-" + uuid.uuid4().hex[:6],
                    "name": sname,
                    "components": _default_components(sname),
                    "auto_layout": "vertical",
                    "padding": 24,
                }
            )
        _save(design)
        return json.dumps(
            {
                "ok": True,
                "message": f"Design '{design['name']}' criado com {len(design['screens'])} tela(s).",
                "file_key": design["key"],
                "link": f"figma://file/{design['key']}",
                "estrutura": design,
                "proximo_passo": "refine com figma_add_screen ou confira com figma_get_file",
            },
            ensure_ascii=False,
            indent=2,
        )

    if name == "figma_add_screen":
        d = _load(str(args.get("file_key", "")))
        screen = {
            "id": "screen-" + uuid.uuid4().hex[:6],
            "name": str(args.get("name", "nova-tela")),
            "components": [str(c) for c in args.get("components") or []]
            or _default_components(str(args.get("name", ""))),
            "auto_layout": "vertical",
            "padding": 24,
        }
        d["screens"].append(screen)
        d["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(d)
        return json.dumps(
            {"ok": True, "message": f"Tela '{screen['name']}' adicionada a {d['name']}.", "tela": screen},
            ensure_ascii=False,
            indent=2,
        )

    if name == "figma_get_design_tokens":
        return json.dumps(DESIGN_TOKENS, ensure_ascii=False, indent=2)

    raise ValueError(f"ferramenta desconhecida: {name}")


def handle(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        text = _call_tool(str(params.get("name", "")), params.get("arguments") or {})
        return {"content": [{"type": "text", "text": text}], "isError": False}
    if method == "ping":
        return {}
    raise ValueError(f"método não suportado: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg:  # notificações não exigem resposta
            continue
        try:
            result = handle(str(msg.get("method", "")), msg.get("params") or {})
            resp = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        except Exception as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32000, "message": f"{exc.__class__.__name__}: {exc}"},
            }
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
