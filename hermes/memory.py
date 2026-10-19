"""Memória persistente do agente: fatos sobre o usuário que sobrevivem entre
conversas e reinícios.

- Arquivo: <data_dir>/memory.json  (escrita atômica)
- O conteúdo é injetado no prompt de sistema de TODAS as conversas e tarefas
  agendadas, e o agente pode gravar/apagar fatos com as ferramentas
  `lembrar` / `esquecer` (tools.py).
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

_LOCK = threading.Lock()
FACT_ID_RE = re.compile(r"^m[a-f0-9]{6,12}$")
MAX_FACTS = 300          # teto de fatos armazenados
MAX_PROMPT_CHARS = 4000  # teto injetado no prompt


class MemoryStore:
    def __init__(self, cfg):
        self.cfg = cfg
        self.path: Path = cfg.data_dir / "memory.json"

    # ------------------------------------------------------------- base
    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("facts"), list):
                return data
        except (OSError, ValueError):
            pass
        return {"facts": []}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)

    def list_all(self) -> list[dict]:
        """Fatos ordenados do mais recente para o mais antigo."""
        with _LOCK:
            facts = [f for f in self._read()["facts"] if isinstance(f, dict)]
        # por ts (época) e, em empate, o inserido depois vem primeiro
        indexed = list(enumerate(facts))
        indexed.sort(key=lambda t: (t[1].get("ts", 0), t[0]), reverse=True)
        return [f for _, f in indexed]

    # ------------------------------------------------------------ ações
    def add(self, text: str) -> dict:
        text = str(text or "").strip()
        if not text:
            raise ValueError("fato vazio")
        with _LOCK:
            data = self._read()
            fact = {
                "id": "m" + uuid.uuid4().hex[:8],
                "text": text[:1000],
                "created": time.strftime("%Y-%m-%d %H:%M"),
                "ts": int(time.time()),
            }
            data["facts"].append(fact)
            data["facts"] = data["facts"][-MAX_FACTS:]
            self._write(data)
        return fact

    def update(self, fid: str, text: str) -> dict | None:
        text = str(text or "").strip()
        with _LOCK:
            data = self._read()
            for f in data["facts"]:
                if f.get("id") == fid:
                    if text:
                        f["text"] = text[:1000]
                        f["edited"] = time.strftime("%Y-%m-%d %H:%M")
                    self._write(data)
                    return f
        return None

    def delete(self, fid: str) -> bool:
        with _LOCK:
            data = self._read()
            antes = len(data["facts"])
            data["facts"] = [f for f in data["facts"] if f.get("id") != fid]
            if len(data["facts"]) == antes:
                return False
            self._write(data)
        return True

    # ----------------------------------------------------------- prompt
    def prompt_section(self) -> str:
        """Seção pronta para o prompt de sistema ('' se não houver fatos)."""
        facts = self.list_all()
        if not facts:
            return ""
        lines = [
            "\n\nMemória persistente sobre o usuário (fatos guardados entre "
            "conversas;\nuse-as para personalizar respostas; mantenha atualizada "
            "com a ferramenta `lembrar`\ne remova o que ficou obsoleto com "
            "`esquecer`, usando o id entre colchetes):"
        ]
        total = 0
        for f in facts:
            line = f"  [{f.get('id')}] {f.get('text', '')}"
            if total + len(line) > MAX_PROMPT_CHARS:
                lines.append("  … (memória truncada)")
                break
            lines.append(line)
            total += len(line)
        return "\n".join(lines)
