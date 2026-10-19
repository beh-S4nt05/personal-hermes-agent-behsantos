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
MAX_PROMPT_CHARS = 2000  # teto injetado no prompt (menos prefill = mais rápido)


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
    @staticmethod
    def _score(query: str, text: str) -> int:
        """Similaridade barata pergunta↔fato (overlap de palavras)."""
        import unicodedata

        def words(s: str) -> set[str]:
            s = unicodedata.normalize("NFKD", s.lower())
            s = "".join(c for c in s if c.isascii())
            return {w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2}

        q = words(query or "")
        if not q:
            return 0
        t = words(text or "")
        return len(q & t)

    def relevant(self, query: str, k: int = 8) -> list[dict]:
        """Top-k fatos por relevância à pergunta (mais os 2 mais recentes)."""
        facts = self.list_all()
        if not facts:
            return []
        scored = sorted(facts, key=lambda f: self._score(query, f.get("text", "")),
                        reverse=True)
        top = scored[:max(1, k)]
        # os 2 mais recentes sempre entram (contexto vivo)
        for f in facts[:2]:
            if f not in top:
                top.append(f)
        return top

    def prompt_section(self, query: str | None = None) -> str:
        """Seção pronta para o prompt de sistema ('' se não houver fatos).

        v3.0: com muitos fatos, injeta os mais RELEVANTES à pergunta em vez
        de truncar — o agente lembra do que importa sem pagar tokens à toa.
        """
        facts = self.list_all()
        if not facts:
            return ""
        lines = [
            "\n\nMemória persistente sobre o usuário (fatos guardados entre "
            "conversas;\nuse-as para personalizar respostas; mantenha atualizada "
            "com a ferramenta `lembrar`\ne remova o que ficou obsoleto com "
            "`esquecer`, usando o id entre colchetes):"
        ]
        total_chars = sum(len(f.get("text", "")) for f in facts)
        selected = facts
        note = ""
        if (query and total_chars > MAX_PROMPT_CHARS
                and int(getattr(self.cfg, "memory_top_k", 8) or 8) > 0):
            selected = self.relevant(
                query, int(getattr(self.cfg, "memory_top_k", 8) or 8))
            note = f"  … ({len(facts)} fatos no total; mostrando os mais relevantes)\n"
        total = 0
        for f in selected:
            line = f"  [{f.get('id')}] {f.get('text', '')}"
            if total + len(line) > MAX_PROMPT_CHARS:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(lines) + (("\n" + note.rstrip()) if note else "")
