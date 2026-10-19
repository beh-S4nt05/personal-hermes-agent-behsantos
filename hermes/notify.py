"""Central de notificações: o agente avisa o operador sem spam.

Arquivo: <data_dir>/notifications.json (lista, cap 50, lidas/não lidas).
GUI: sininho no cabeçalho; falhas de tarefas e reinícios de MCP aparecem lá.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
MAX_ITEMS = 50


def push(cfg, kind: str, title: str, body: str = "") -> None:
    try:
        with _LOCK:
            path = cfg.data_dir / "notifications.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = []
            data.insert(0, {
                "id": f"n{int(time.time()*1000)}",
                "kind": str(kind)[:16],        # task_error | mcp | info | warn
                "title": str(title)[:140],
                "body": str(body)[:500],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "read": False,
            })
            path.write_text(json.dumps(data[:MAX_ITEMS], ensure_ascii=False,
                                       indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def list_all(cfg) -> list[dict]:
    path = cfg.data_dir / "notifications.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def unread_count(cfg) -> int:
    return sum(1 for n in list_all(cfg) if not n.get("read"))


def mark_all_read(cfg) -> None:
    with _LOCK:
        path = cfg.data_dir / "notifications.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for n in data:
                n["read"] = True
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        except (OSError, ValueError):
            pass
