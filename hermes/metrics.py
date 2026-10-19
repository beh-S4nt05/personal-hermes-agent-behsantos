"""Métricas de desempenho: cada resposta do agente vira um dado histórico.

Arquivo: <data_dir>/metrics.jsonl (append; podado às 500 linhas).
Registro: {ts, agent, model, duration_s, tokens, tok_s, steps, status}
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
MAX_LINES = 500


def record(cfg, agent: str, model: str, duration_s, tokens: int,
           tok_s, steps: int, status: str = "ok") -> None:
    try:
        with _LOCK:
            path = cfg.data_dir / "metrics.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "agent": str(agent)[:12], "model": str(model)[:48],
                   "duration_s": round(float(duration_s or 0), 1),
                   "tokens": int(tokens or 0),
                   "tok_s": (round(float(tok_s), 1) if tok_s else None),
                   "steps": int(steps or 0), "status": str(status)[:12]}
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            # poda: mantém só as MAX_LINES mais recentes
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                if len(lines) > MAX_LINES + 50:
                    path.write_text("\n".join(lines[-MAX_LINES:]) + "\n",
                                    encoding="utf-8")
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass


def recent(cfg, limit: int = 30, agent: str = "") -> list[dict]:
    limit = max(1, min(int(limit or 30), 200))
    path = cfg.data_dir / "metrics.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        if len(out) >= limit:
            break
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if agent and r.get("agent") != agent:
            continue
        out.append(r)
    return out


def summary(cfg) -> dict:
    """Médias das últimas N respostas (para o painel)."""
    recs = recent(cfg, limit=30)
    if not recs:
        return {"n": 0}
    toks = [r["tok_s"] for r in recs if r.get("tok_s")]
    durs = [r.get("duration_s") or 0 for r in recs]
    return {
        "n": len(recs),
        "avg_tok_s": round(sum(toks) / len(toks), 1) if toks else None,
        "avg_duration_s": round(sum(durs) / len(durs), 1),
        "spark": [r.get("tok_s") for r in reversed(recs[-20:])],
    }
