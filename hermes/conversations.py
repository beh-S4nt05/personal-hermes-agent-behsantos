"""Armazenamento de conversas do chat (persistência entre recargas).

Cada conversa é uma "sessão" salva em <data>/conversations/sessions/<id>.json
com todas as mensagens (usuário e assistente). A sessão corrente é apontada em
<data>/conversations/current.json — assim, ao recarregar a GUI, a última
conversa volta exatamente de onde estava (nem F5 perde mais nada).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

SESSION_ID_RE = re.compile(r"^[a-z0-9-]{6,64}$")
MAX_SESSIONS = 200


class ConversationStore:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sessions_dir = cfg.conversations_dir / "sessions"

    # ----------------------------------------------------------- internals
    def _path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _ensure_dir(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- CRUD
    def new_session(self) -> dict:
        session = {
            "id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
            "title": "",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [],
        }
        self._ensure_dir()
        self.save(session)
        return session

    def save(self, session: dict) -> None:
        self._ensure_dir()
        session["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        path = self._path(session["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    def load(self, session_id: str) -> dict | None:
        if not SESSION_ID_RE.fullmatch(session_id or ""):
            return None
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("id"):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def append(self, session_id: str, role: str, content: str,
               dur: float | None = None, agent: str | None = None) -> dict | None:
        """Adiciona uma mensagem à sessão (cria o arquivo se preciso)."""
        session = self.load(session_id)
        if session is None:
            return None
        msg: dict = {"role": role, "content": content or ""}
        if dur is not None:
            msg["dur"] = dur  # tempo de geração (s) — exibido no histórico
        if agent:
            msg["agent"] = agent  # qual agente respondeu (hermes/claude)
        session["messages"].append(msg)
        if not session["title"] and role == "user":
            session["title"] = (content or "").strip().splitlines()[0][:70] or "conversa"
        self.save(session)
        return session

    def list(self) -> list[dict]:
        self._ensure_dir()
        out = []
        for f in self.sessions_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                out.append({
                    "id": d.get("id"),
                    "title": d.get("title") or "conversa",
                    "updated_at": d.get("updated_at", ""),
                    "messages": len(d.get("messages", [])),
                })
            except (OSError, json.JSONDecodeError):
                continue
        out = [s for s in out if s["id"]]
        out.sort(key=lambda s: s["updated_at"], reverse=True)
        return out[:MAX_SESSIONS]

    def search(self, query: str) -> list[dict]:
        """Busca texto dentro de TODAS as conversas (mín. 2 caracteres)."""
        q = (query or "").strip().lower()
        if len(q) < 2:
            return []
        self._ensure_dir()
        results: list[dict] = []
        for f in self.sessions_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for m in d.get("messages", []):
                content = str(m.get("content") or "")
                idx = content.lower().find(q)
                if idx < 0:
                    continue
                start = max(0, idx - 40)
                preview = content[start:start + 130].replace("\n", " ")
                preview = ("…" if start > 0 else "") + preview + "…"
                results.append({
                    "id": d.get("id"),
                    "title": d.get("title") or "conversa",
                    "updated_at": d.get("updated_at", ""),
                    "role": m.get("role"),
                    "preview": preview,
                })
                break  # uma ocorrência por conversa basta
        results = [r for r in results if r["id"]]
        results.sort(key=lambda r: r["updated_at"], reverse=True)
        return results[:50]

    def delete(self, session_id: str) -> bool:
        if not SESSION_ID_RE.fullmatch(session_id or ""):
            return False
        p = self._path(session_id)
        if p.exists():
            p.unlink()
            return True
        return False

    # --------------------------------------------------------- ponteiro
    def set_current(self, session_id: str | None) -> None:
        self.cfg.conversations_dir.mkdir(parents=True, exist_ok=True)
        path = self.cfg.conversations_dir / "current.json"
        if session_id and SESSION_ID_RE.fullmatch(session_id):
            path.write_text(json.dumps({"id": session_id}), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)

    def get_current(self) -> str | None:
        try:
            data = json.loads((self.cfg.conversations_dir / "current.json").read_text(encoding="utf-8"))
            cid = data.get("id")
            if cid and self._path(cid).exists():
                return cid
        except (OSError, json.JSONDecodeError):
            pass
        return None
