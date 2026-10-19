"""Daemon do agente: fica ligado em segundo plano e consome tarefas da fila.

A GUI controla esse processo (ligar/desligar) através do manager. As tarefas
são arquivos JSON em data_dir/tasks/*.json e os resultados em tasks/done/.
"""

from __future__ import annotations

import glob
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

from .agent import Agent
from .config import Config


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def _write_heartbeat(cfg: Config, status: str, task: str | None, started_at: float) -> None:
    payload = {
        "pid": os.getpid(),
        "status": status,
        "task": task,
        "started_at": started_at,
        "ts": time.time(),
    }
    tmp = cfg.heartbeat_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(cfg.heartbeat_path)


def enqueue(cfg: Config, text: str) -> dict:
    """Cria um arquivo de tarefa na fila e devolve o registro."""
    cfg.ensure_dirs()
    task = {
        "id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "input": text.strip(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = cfg.spool_dir / f"{task['id']}.json"
    path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return task


def list_tasks(cfg: Config) -> dict:
    cfg.ensure_dirs()
    pending = []
    for f in sorted(glob.glob(str(cfg.spool_dir / "*.json"))):
        try:
            pending.append(json.loads(Path(f).read_text(encoding="utf-8")))
        except Exception:
            continue
    done = []
    for f in sorted(glob.glob(str(cfg.done_dir / "*.json")), reverse=True):
        try:
            done.append(json.loads(Path(f).read_text(encoding="utf-8")))
        except Exception:
            continue
    done = done[:50]
    return {"pending": pending, "done": done}


def run_daemon(cfg: Config | None = None) -> None:
    cfg = cfg or Config()
    cfg.ensure_dirs()

    running = {"flag": True}
    started_at = time.time()

    def _stop(signum, _frame):
        running["flag"] = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    mock_note = " (SIMULAÇÃO: Ollama simulado)" if cfg.mock else ""
    log(f"=== Hermes Agent daemon iniciado {mock_note} — pid {os.getpid()} ===")
    log(f"modelo: {cfg.model} | ollama: {cfg.ollama_url} | fila: {cfg.spool_dir}")

    agent = Agent(cfg)
    _write_heartbeat(cfg, "starting", None, started_at)

    try:
        while running["flag"]:
            _write_heartbeat(cfg, "idle", None, started_at)
            for task_file in sorted(glob.glob(str(cfg.spool_dir / "*.json"))):
                if not running["flag"]:
                    break
                try:
                    task = json.loads(Path(task_file).read_text(encoding="utf-8"))
                except Exception as exc:
                    log(f"!!! tarefa corrompida {task_file}: {exc} — descartando")
                    Path(task_file).unlink(missing_ok=True)
                    continue

                task_id = task.get("id", Path(task_file).stem)
                log(f">>> tarefa {task_id}: {task.get('input', '')[:100]}")
                _write_heartbeat(cfg, "running", task_id, started_at)

                events: list[dict] = []
                t0 = time.time()
                try:
                    final = agent.run(
                        [{"role": "user", "content": task.get("input", "")}],
                        on_event=events.append,
                    )
                    status = "ok"
                except Exception as exc:  # nunca derruba o daemon
                    final = f"[erro interno] {exc.__class__.__name__}: {exc}"
                    status = "error"

                result = {
                    "id": task_id,
                    "input": task.get("input", ""),
                    "output": final,
                    "tools": [
                        {"name": e["name"], "ok": e["ok"], "output": e["output"][-1500:]}
                        for e in events if e.get("type") == "tool_end"
                    ],
                    "status": status,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
                    "duration_s": round(time.time() - t0, 1),
                }
                out = cfg.done_dir / f"{task_id}.json"
                out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                Path(task_file).unlink(missing_ok=True)
                log(f"<<< tarefa {task_id} concluída ({status}, {result['duration_s']}s)")

            time.sleep(1)
    finally:
        _write_heartbeat(cfg, "stopping", None, started_at)
        log("=== Hermes Agent daemon encerrado ===")
        cfg.heartbeat_path.unlink(missing_ok=True)
        sys.exit(0)
