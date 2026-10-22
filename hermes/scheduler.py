"""Agendador de tarefas — executa pedidos em momentos específicos.

Formatos aceitos (texto em português, campo "quando"):
  "diário 08:30" / "todo dia às 08:30"       -> todos os dias às 08:30
  "seg,qua 14:00" / "semanal seg,sex 07:00"   -> dias da semana específicos
  "uma vez 2026-10-02 14:00" / "amanhã 09:00" -> executa uma vez e desativa
  "a cada 30m" / "a cada 2h"                  -> recorrente por intervalo

As tarefas agendadas rodam de forma DESASSISTIDA: sem confirmação interativa
(nada de "executar mesmo assim?"), mas a denylist de segurança continua
protegendo contra comandos destrutivos (rm -rf /, mkfs, shutdown…).

O agendador vive no processo `hermes server` — mantenha a GUI rodando para
que os horários disparem. Cada execução gera resultado completo em
tasks/done/ e fica registrada na própria tarefa agendada.

v3.0:
- histórico das últimas 20 execuções por tarefa (entry["history"])
- retry com atraso: campos `retries` (0-3) e `retry_delay_min`
- gatilhos: trigger {"type": "webhook"} (POST /api/hooks/<id>) e
  {"type": "watch", "path": dir, "glob": "*.pdf"} (arquivo novo → roda)
- `only_idle`: adia a execução enquanto a máquina estiver ocupada (Linux)
- falhas geram notificação para o operador (data/notifications.json)
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

SCHEDULE_ID_RE = re.compile(r"^[a-z0-9-]{6,64}$")
POLL_SECONDS = 15

_DAYS_PT = {
    "dom": 6, "domingo": 6,
    "seg": 0, "segunda": 0,
    "ter": 1, "terca": 1, "terça": 1,
    "qua": 2, "quarta": 2,
    "qui": 3, "quinta": 3,
    "sex": 4, "sexta": 4,
    "sab": 5, "sabado": 5, "sábado": 5,
}
_DAY_NAMES = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _norm(text: str) -> str:
    text = (text or "").lower().strip()
    subs = {"á": "a", "à": "a", "ã": "a", "â": "a", "é": "e", "ê": "e", "í": "i",
            "ó": "o", "ô": "o", "õ": "o", "ú": "u", "ç": "c"}
    for k, v in subs.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text)


def parse_schedule(text: str) -> dict:
    """Converte texto em português num spec de agendamento."""
    t = _norm(text)
    if not t:
        raise ValueError("informe quando a tarefa deve rodar")

    # a cada Nm / Nh
    m = re.search(r"a cada\s+(\d+)\s*(m|min|minutos?|h|horas?)", t)
    if m:
        n = max(1, int(m.group(1)))
        minutes = n * 60 if m.group(2).startswith("h") else n
        return {"type": "interval", "minutes": minutes}

    # data+hora absoluta: 2026-10-02 14:00 (com ou sem "uma vez")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ t]+(\d{1,2}):(\d{2})", t)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          int(m.group(4)), int(m.group(5)))
        except ValueError as exc:
            raise ValueError(f"data inválida: {exc}") from exc
        return {"type": "once", "at": dt.strftime("%Y-%m-%dT%H:%M")}

    hm = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if hm:
        hh, mm = int(hm.group(1)) % 24, int(hm.group(2))
    else:
        # "às 8h", "às 8h30", "às 8" (às normaliza p/ "as")
        mh = re.search(r"\bas\s+(\d{1,2})h(\d{2})?\b", t) or \
             re.search(r"\bas\s+(\d{1,2})\b", t)
        if not mh:
            raise ValueError(
                "não entendi o horário — exemplos: 'diário 08:30', 'seg,qua 14:00', "
                "'amanhã 09:00', 'a cada 30m'"
            )
        hh, mm = int(mh.group(1)) % 24, (int(mh.group(2)) if mh.lastindex == 2 else 0)

    # hoje/amanhã HH:MM -> once
    if "amanha" in t:
        dt = datetime.combine(date.today() + timedelta(days=1), dtime(hh, mm))
        return {"type": "once", "at": dt.strftime("%Y-%m-%dT%H:%M")}
    if "hoje" in t:
        dt = datetime.combine(date.today(), dtime(hh, mm))
        return {"type": "once", "at": dt.strftime("%Y-%m-%dT%H:%M")}

    # dias da semana -> weekly
    days = sorted({_DAYS_PT[d] for d in _DAYS_PT if re.search(rf"\b{d}\b", t)})
    if days:
        return {"type": "weekly", "days": days, "time": f"{hh:02d}:{mm:02d}"}

    # diário (padrão quando só tem horário)
    return {"type": "daily", "time": f"{hh:02d}:{mm:02d}"}


def human_schedule(spec: dict) -> str:
    t = spec.get("type")
    if t == "daily":
        return f"todos os dias às {spec.get('time')}"
    if t == "weekly":
        dias = ", ".join(_DAY_NAMES[d] for d in spec.get("days", []))
        return f"{dias} às {spec.get('time')}"
    if t == "once":
        return f"uma vez em {spec.get('at', '').replace('T', ' ')}"
    if t == "interval":
        n = spec.get("minutes", 0)
        return f"a cada {n // 60}h{n % 60:02d}m" if n >= 60 else f"a cada {n} min"
    return "?"


def _parse_hm(value: str) -> dtime:
    hh, mm = str(value).split(":")[:2]
    return dtime(int(hh) % 24, int(mm) % 60)


def next_run(entry: dict, now: datetime | None = None) -> datetime | None:
    """Próxima disparada da tarefa (None se não houver)."""
    now = now or datetime.now()
    spec = entry.get("schedule") or {}
    t = spec.get("type")
    if t == "daily":
        hhmm = _parse_hm(spec.get("time", "08:00"))
        candidate = now.replace(hour=hhmm.hour, minute=hhmm.minute,
                                second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    if t == "weekly":
        hhmm = _parse_hm(spec.get("time", "08:00"))
        days = set(spec.get("days") or [0])
        for i in range(8):
            candidate = (now + timedelta(days=i)).replace(
                hour=hhmm.hour, minute=hhmm.minute, second=0, microsecond=0)
            if candidate > now and candidate.weekday() in days:
                return candidate
        return None
    if t == "once":
        try:
            at = datetime.strptime(spec.get("at", ""), "%Y-%m-%dT%H:%M")
        except ValueError:
            return None
        return at if at > now else None
    if t == "interval":
        minutes = max(1, int(spec.get("minutes", 60)))
        base = None
        for key in ("last_run_ts", "created_ts"):
            if entry.get(key):
                base = datetime.fromtimestamp(float(entry[key]))
                break
        if base is None:
            return now
        cand = base + timedelta(minutes=minutes)
        step = timedelta(minutes=minutes)
        while cand <= now:  # pula slots perdidos (server desligado etc.)
            cand += step
        return cand
    return None


def is_due(entry: dict, now: datetime | None = None) -> bool:
    """A tarefa deve disparar AGORA? (next_run é só para exibição.)"""
    now = now or datetime.now()
    spec = entry.get("schedule") or {}
    t = spec.get("type")
    if t in ("daily", "weekly"):
        hhmm = _parse_hm(spec.get("time", "08:00"))
        if now.time() < hhmm:
            return False
        if t == "weekly" and now.weekday() not in set(spec.get("days") or [0]):
            return False
        last = entry.get("last_run_ts")
        if last and datetime.fromtimestamp(float(last)).date() == now.date():
            return False  # já rodou hoje
        created = entry.get("created_ts")
        if not last and created:
            c = datetime.fromtimestamp(float(created))
            if c.date() == now.date() and c.time() > hhmm:
                return False  # criada depois do horário → começa no próximo dia
        return True
    if t == "once":
        try:
            at = datetime.strptime(spec.get("at", ""), "%Y-%m-%dT%H:%M")
        except ValueError:
            return False
        if entry.get("last_run_ts"):
            return False
        # tolerância de 10 min: depois disso, considera perdida
        return at <= now <= at + timedelta(minutes=10)
    if t == "interval":
        minutes = max(1, int(spec.get("minutes", 60)))
        base = None
        for key in ("last_run_ts", "created_ts"):
            if entry.get(key):
                base = datetime.fromtimestamp(float(entry[key]))
                break
        if base is None:
            return True
        return (now - base) >= timedelta(minutes=minutes)
    return False


class ScheduleStore:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dir = cfg.data_dir / "schedules"

    def _path(self, sid: str) -> Path:
        return self.dir / f"{sid}.json"

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, input_text: str, spec: dict, agent: str = "hermes",
               trigger: dict | None = None, retries: int = 0,
               retry_delay_min: int = 5, only_idle: bool = False) -> dict:
        self._ensure()
        entry = {
            "id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
            "input": input_text.strip(),
            "schedule": spec,
            "enabled": True,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "created_ts": time.time(),
            "agent": agent if agent in ("hermes", "claude") else "hermes",
            "run_count": 0,
            "last_run": None,
            "last_status": None,
            "last_duration_s": None,
            "last_output": None,
            "running": False,
            # v3.0
            "trigger": trigger or None,          # {"type":"webhook"|"watch",...}
            "retries": max(0, min(int(retries or 0), 3)),
            "retry_delay_min": max(1, int(retry_delay_min or 5)),
            "only_idle": bool(only_idle),
            "retries_used": 0,
            "retry_at_ts": None,
            "history": [],                       # últimas 20 execuções
        }
        self.save(entry)
        return entry

    def save(self, entry: dict) -> None:
        self._ensure()
        path = self._path(entry["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    def load(self, sid: str) -> dict | None:
        if not SCHEDULE_ID_RE.fullmatch(sid or ""):
            return None
        p = self._path(sid)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_all(self) -> list[dict]:
        self._ensure()
        out = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return out

    def public_list(self) -> list[dict]:
        now = datetime.now()
        items = []
        for e in self.list_all():
            nr = next_run(e, now)
            items.append({
                "id": e.get("id"),
                "input": e.get("input", ""),
                "schedule": e.get("schedule", {}),
                "human": human_schedule(e.get("schedule") or {}),
                "agent": e.get("agent", "hermes"),
                "enabled": bool(e.get("enabled")),
                "running": bool(e.get("running")),
                "next_run": nr.strftime("%Y-%m-%d %H:%M") if (nr and e.get("enabled")) else None,
                "run_count": e.get("run_count", 0),
                "last_run": e.get("last_run"),
                "last_status": e.get("last_status"),
                "last_duration_s": e.get("last_duration_s"),
                "trigger": e.get("trigger"),
                "retries": e.get("retries", 0),
                "only_idle": bool(e.get("only_idle")),
                "retries_used": e.get("retries_used", 0),
                "history_n": len(e.get("history") or []),
                "history": (e.get("history") or [])[:5],
            })
        return items

    def delete(self, sid: str) -> bool:
        if not SCHEDULE_ID_RE.fullmatch(sid or ""):
            return False
        p = self._path(sid)
        if p.exists():
            p.unlink()
            return True
        return False


# ---------------------------------------------------------------- executor

def execute_entry(cfg, entry: dict, on_event=None) -> dict:
    """Roda a tarefa agendada de forma desassistida e devolve o resultado.

    on_event (opcional) recebe os mesmos eventos do chat (step, token,
    tool_start/tool_end, done...) — usado pela visão "ao vivo" da GUI.
    """
    from .agent import Agent

    if getattr(cfg, "auto_start_ollama", False) and not cfg.mock:
        try:
            from .ollama_client import get_client
            if not get_client(cfg).is_running():
                from .manager import OllamaManager
                OllamaManager(cfg).start()
        except Exception:
            pass

    # segundo agente: Claude Code (CLI) em vez do loop Hermes/Ollama
    if entry.get("agent") == "claude":
        from .claude_agent import run_claude
        events: list[dict] = []
        t0 = time.time()
        final = run_claude(cfg, entry["input"], on_event=lambda e: events.append(e))
        status = "ok" if final and "não encontrado neste computador" not in final else "error"
        return {
            "status": status,
            "output": final,
            "tools": [
                {"name": e["name"], "ok": e["ok"], "output": (e.get("output") or "")[-1500:]}
                for e in events if e.get("type") == "tool_end"
            ],
            "duration_s": round(time.time() - t0, 1),
        }

    agent = Agent(cfg)
    events: list[dict] = []
    ev = on_event or (lambda _e: None)

    def _collect(e: dict) -> None:
        events.append(e)
        try:
            ev(e)
        except Exception:
            pass

    t0 = time.time()
    final = agent.run([{"role": "user", "content": entry["input"]}],
                      on_event=_collect)
    # v3.0: erro de verdade conta como erro (habilita retry/notificação)
    falhou = (not final) or final.startswith(("[erro]", "[interrompido"))
    return {
        "status": "error" if falhou else "ok",
        "output": final,
        "tools": [
            {"name": e["name"], "ok": e["ok"], "output": (e.get("output") or "")[-1500:]}
            for e in events if e.get("type") == "tool_end"
        ],
        "duration_s": round(time.time() - t0, 1),
    }


# ---------------------------------------------------------------------------
# Visão "ao vivo": buffer em memória da execução corrente/última de cada tarefa
# ---------------------------------------------------------------------------
LIVE: dict[str, dict] = {}
_LIVE_LOCK = threading.Lock()
LIVE_MAX_EVENTS = 400


def _live_begin(sid: str, input_text: str) -> None:
    with _LIVE_LOCK:
        LIVE[sid] = {"id": sid, "input": input_text, "running": True,
                     "t0": time.time(), "events": [], "tokens": 0}


def _live_push(sid: str, event: dict) -> None:
    with _LIVE_LOCK:
        buf = LIVE.get(sid)
        if buf is None:
            return
        etype = event.get("type")
        if etype == "token":
            buf["tokens"] += 1
            return  # tokens só contam (o console mostra o andamento)
        e = dict(event)
        if etype == "tool_end":
            e["output"] = (e.get("output") or "")[:800]
        if etype in ("done", "error", "cancelled"):
            e["message"] = (e.get("message") or "")[:4000]
        buf["events"].append(e)
        if len(buf["events"]) > LIVE_MAX_EVENTS:
            del buf["events"][:len(buf["events"]) - LIVE_MAX_EVENTS]


def _live_end(sid: str, result: dict) -> None:
    with _LIVE_LOCK:
        buf = LIVE.get(sid)
        if buf is None:
            return
        buf["running"] = False
        buf["duration_s"] = result.get("duration_s")
        buf["ended"] = time.strftime("%Y-%m-%d %H:%M")
        last = buf["events"][-1] if buf["events"] else None
        if not last or last.get("type") not in ("done", "error", "cancelled"):
            buf["events"].append({
                "type": "done" if result.get("status") == "ok" else "error",
                "message": (result.get("output") or "")[:4000],
            })


def live_status(sid: str) -> dict | None:
    """Snapshot do console ao vivo da tarefa (None se nunca rodou neste server)."""
    with _LIVE_LOCK:
        buf = LIVE.get(sid)
        return dict(buf) if buf else None


class Scheduler:
    """Loop que dispara as tarefas agendadas (roda dentro do `hermes server`)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.store = ScheduleStore(cfg)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------- ciclo
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="hermes-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(POLL_SECONDS):
            try:
                self.tick()
            except Exception:
                pass

    def tick(self) -> None:
        now = datetime.now()
        # v3.15.0 (PR#3): skills baixadas pelo operador viram nativas
        try:
            if time.time() - getattr(self, "_last_skills_scan", 0.0) > 600:
                self._last_skills_scan = time.time()
                from .skills import autoscan
                autoscan(self.cfg)
        except Exception:  # noqa: BLE001
            pass
        for entry in self.store.list_all():
            if not entry.get("enabled") or entry.get("running"):
                continue
            trigger = entry.get("trigger") or {}

            # ── v3.0: retry pendente (falhou e tem tentativas restantes) ──
            if entry.get("retry_at_ts"):
                if time.time() >= float(entry["retry_at_ts"]):
                    threading.Thread(target=self._execute, args=(entry["id"],),
                                     kwargs={"is_retry": True}, daemon=True).start()
                continue

            # ── v3.0: gatilhos (webhook não dispara por tempo; watch sim) ──
            if trigger.get("type") == "webhook":
                continue  # só roda via POST /api/hooks/<id>
            if trigger.get("type") == "watch":
                novos = self._watch_new_files(entry)
                if novos:
                    threading.Thread(
                        target=self._execute, args=(entry["id"],),
                        kwargs={"extra_context": "Arquivos novos detectados: "
                                 + ", ".join(novos[:10])}, daemon=True).start()
                continue
            if not trigger and not (entry.get("schedule") or {}):
                continue

            if is_due(entry, now):
                # ── v3.0: tarefa "só quando ocioso" espera a máquina livrar ──
                if entry.get("only_idle") and _system_busy():
                    continue
                threading.Thread(target=self._execute, args=(entry["id"],),
                                 daemon=True).start()
            elif ((entry.get("schedule") or {}).get("type") == "once"
                  and not entry.get("run_count")
                  and next_run(entry, now) is None):
                # once cujo horário passou (mais de 10 min) e nunca rodou → perdida
                entry["enabled"] = False
                entry["last_status"] = "perdida"
                self.store.save(entry)

    # ---------------------------------------------------- watcher (gatilho)
    def _watch_new_files(self, entry: dict) -> list[str]:
        """Arquivos novos que casam com o padrão desde a última verificação."""
        trig = entry.get("trigger") or {}
        path = str(trig.get("path") or "").strip()
        pattern = str(trig.get("glob") or "*").strip() or "*"
        if not path:
            return []
        d = Path(path).expanduser()
        if not d.is_dir():
            return []
        try:
            atual = sorted(p.name for p in d.glob(pattern) if p.is_file())
        except OSError:
            return []
        vistos = entry.get("watch_seen")
        # primeira vez: apenas aprende o estado, não dispara
        if vistos is None:
            entry["watch_seen"] = atual
            self.store.save(entry)
            return []
        novos = [f for f in atual if f not in set(vistos)]
        if novos or len(vistos) != len(atual):
            entry["watch_seen"] = atual
            self.store.save(entry)
        return novos

    # ---------------------------------------------------------- execução
    def _execute(self, sid: str, force: bool = False, is_retry: bool = False,
                 extra_context: str = "") -> dict:
        entry = self.store.load(sid)
        if not entry or entry.get("running"):
            return {"ok": False, "msg": "tarefa não encontrada ou já em execução"}
        entry["running"] = True
        entry["retry_at_ts"] = None
        self.store.save(entry)
        _live_begin(sid, entry["input"])
        try:
            from . import activity
            activity.log(self.cfg, "agendador",
                         f"⏰ tarefa {sid[-6:]} iniciada: {entry['input'][:70]}")
        except Exception:  # noqa: BLE001
            pass
        original_input = entry["input"]
        if extra_context:
            entry = dict(entry)
            entry["input"] = f"{original_input}\n\n(Contexto do gatilho: {extra_context})"
            _live_begin(sid, entry["input"])
        try:
            result = execute_entry(self.cfg, entry,
                                   on_event=lambda e: _live_push(sid, e))
        except Exception as exc:  # noqa: BLE001
            result = {"status": "error",
                      "output": f"[erro] {exc.__class__.__name__}: {exc}",
                      "tools": [], "duration_s": 0}
        _live_end(sid, result)

        entry = self.store.load(sid) or entry
        if extra_context:
            entry["input"] = original_input  # contexto do gatilho é 1-shot
        entry.update({
            "running": False,
            "run_count": entry.get("run_count", 0) + 1,
            "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_run_ts": time.time(),
            "last_status": result["status"],
            "last_duration_s": result["duration_s"],
            "last_output": (result["output"] or "")[:4000],
        })
        # ── v3.0: histórico das últimas 20 execuções ──
        hist = entry.get("history") or []
        hist.insert(0, {
            "ts": entry["last_run"],
            "status": result["status"],
            "duration_s": result["duration_s"],
            "retries_used": entry.get("retries_used", 0) if is_retry else 0,
            "output": (result["output"] or "")[:500],
        })
        entry["history"] = hist[:20]

        spec = entry.get("schedule") or {}
        trigger = entry.get("trigger") or {}
        if spec.get("type") == "once" and not force and not trigger:
            entry["enabled"] = False  # única execução concluída

        # ── v3.0: retry com atraso + notificação de falha ──
        falhou = result["status"] != "ok"
        if falhou:
            from . import notify
            usados = entry.get("retries_used", 0)
            limite = entry.get("retries", 0)
            if usados < limite:
                delay = max(1, int(entry.get("retry_delay_min", 5)))
                entry["retries_used"] = usados + 1
                entry["retry_at_ts"] = time.time() + delay * 60
                notify.push(self.cfg, "task_error",
                            f"Tarefa falhou — nova tentativa em {delay} min",
                            f"“{entry['input'][:80]}” · tentativa "
                            f"{usados + 1}/{limite}")
            else:
                entry["retries_used"] = 0
                notify.push(self.cfg, "task_error",
                            "Tarefa agendada FALHOU",
                            f"“{entry['input'][:80]}” — veja o resultado na "
                            f"aba Tarefas")
        else:
            entry["retries_used"] = 0
        self.store.save(entry)
        try:
            from . import activity
            marca = "✔" if result["status"] == "ok" else "✖"
            activity.log(self.cfg, "agendador",
                         f"{marca} tarefa {sid[-6:]} concluída "
                         f"({result['status']}, {result['duration_s']}s)")
        except Exception:  # noqa: BLE001
            pass

        # resultado completo vai para o histórico de tarefas (aba Tarefas)
        try:
            done = self.cfg.done_dir
            done.mkdir(parents=True, exist_ok=True)
            record = {
                "id": f"{sid}-{int(time.time())}",
                "input": f"⏰ [agendada] {entry['input']}",
                "output": result["output"],
                "tools": result.get("tools", []),
                "status": result["status"],
                "started_at": entry["last_run"],
                "duration_s": result["duration_s"],
            }
            (done / f"{record['id']}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return {"ok": True, "msg": f"tarefa executada ({result['status']}, "
                                   f"{result['duration_s']}s)"}

    def run_now(self, sid: str) -> dict:
        entry = self.store.load(sid)
        if not entry:
            return {"ok": False, "msg": "tarefa não encontrada"}
        threading.Thread(target=self._execute, args=(sid,), kwargs={"force": True},
                         daemon=True).start()
        return {"ok": True, "msg": "executando agora — o resultado aparece em instantes"}


def _system_busy(threshold: float | None = None) -> bool:
    """True se a máquina estiver ocupada (para tarefas 'only_idle').

    v3.0.1: o load é comparado RELATIVO ao número de núcleos — load 3 num
    Ryzen de 16 threads é ocioso; num Atom de 2, é sobrecarga.
    """
    try:
        load1 = float(Path("/proc/loadavg").read_text().split()[0])
        limiar = threshold if threshold is not None else (os.cpu_count() or 2) * 0.75
        return load1 > limiar
    except (OSError, ValueError, IndexError):
        return False  # não-Linux ou leitura falhou: não bloqueia nunca
