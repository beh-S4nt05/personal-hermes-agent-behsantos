"""Auditoria: trilha persistente de TODA ação executada pelo agente.

Arquivo: <data_dir>/audit/audit-YYYY-MM.jsonl (rotação mensal, append-only).
Cada linha: {ts, agent, tool, args, ok, duration_ms, output (400 chars)}
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
MAX_OUTPUT_CHARS = 400


def log(cfg, agent: str, tool: str, args: dict | None, ok: bool,
        output: str = "", duration_ms: int = 0, source: str = "agent") -> None:
    """Registra uma ação (nunca lança — auditoria não pode derrubar nada)."""
    try:
        with _LOCK:
            d = cfg.data_dir / "audit"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"audit-{time.strftime('%Y-%m')}.jsonl"
            rec = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "agent": str(agent)[:24],
                "tool": str(tool)[:64],
                "args": _chop(args),
                "ok": bool(ok),
                "duration_ms": int(duration_ms),
                "source": str(source)[:24],
                "output": str(output or "")[:MAX_OUTPUT_CHARS],
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _chop(args) -> dict:
    if not isinstance(args, dict):
        return {}
    out = {}
    for k, v in args.items():
        s = v if isinstance(v, (int, float, bool)) else str(v)
        out[str(k)[:32]] = s if isinstance(s, (int, float, bool)) else s[:200]
    return out


def query(cfg, agent: str = "", tool: str = "", limit: int = 100,
          day: str = "", month: str = "") -> list[dict]:
    """Lê os registros mais recentes (filtros opcionais)."""
    limit = max(1, min(int(limit or 100), 500))
    month = month or time.strftime("%Y-%m")
    path = cfg.data_dir / "audit" / f"audit-{month}.jsonl"
    if not path.exists():
        return []
    recs: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):  # mais recente primeiro
        if len(recs) >= limit:
            break
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if agent and r.get("agent") != agent:
            continue
        if tool and r.get("tool") != tool:
            continue
        if day and not str(r.get("ts", "")).startswith(day):
            continue
        recs.append(r)
    return recs


def tools_summary(cfg) -> list[dict]:
    """Contagem por ferramenta no mês (para o topo da página Auditoria)."""
    import collections
    path = cfg.data_dir / "audit" / f"audit-{time.strftime('%Y-%m')}.jsonl"
    if not path.exists():
        return []
    try:
        counts = collections.Counter()
        fails: collections.Counter = collections.Counter()
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            counts[r.get("tool", "?")] += 1
            if not r.get("ok"):
                fails[r.get("tool", "?")] += 1
        return [{"tool": t, "count": c, "fails": fails.get(t, 0)}
                for t, c in counts.most_common(12)]
    except OSError:
        return []
