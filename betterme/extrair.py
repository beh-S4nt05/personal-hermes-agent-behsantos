"""Extrai JSON da resposta de um modelo — implementação ÚNICA.

Modelos pequenos cercam o JSON de prosa (ou respondem JSON cru).
Varredura de chaves balanceadas com consciência de strings/escapes:
o primeiro objeto JSON válido do texto. v6.4.0 (DRY): antes havia
duas cópias — orchestrator._extract_json (esta, boa) e
specialists._extrair_json (regex gulosa, frágil) — agora aliases
desta função.
"""
from __future__ import annotations

import json


def json_de(texto: str) -> dict | None:
    """Primeiro objeto JSON balanceado do texto (modelos pequenos cercam
    o JSON de prosa) — None se não achar nada válido."""
    t = texto or ""
    i = t.find("{")
    while i != -1:
        prof, ini, em_str, esc = 0, i, False, False
        for j in range(i, len(t)):
            c = t[j]
            if em_str:
                if esc:                      # caractere escapado (\" \\ ...)
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    em_str = False
                continue
            if c == '"':
                em_str = True
            elif c == "{":
                prof += 1
            elif c == "}":
                prof -= 1
                if prof == 0:
                    try:
                        obj = json.loads(t[ini:j + 1])
                        return obj if isinstance(obj, dict) else None
                    except ValueError:
                        break
        i = t.find("{", i + 1)
    return None
