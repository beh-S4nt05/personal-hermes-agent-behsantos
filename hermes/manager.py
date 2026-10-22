"""Gerenciamento de processos: agente (daemon) e servidor Ollama.

É aqui que a GUI implementa o "ligado/desligado":
- DaemonManager: inicia/para/reinicia o processo do agente (heartbeat + sinais).
- OllamaManager: detecta, liga e desliga o Ollama (systemd quando existir,
  senão sobe `ollama serve` como processo gerenciado por nós). Também expõe
  a "visão de processo" que no Windows fica no app da bandeja: PID, tempo
  ligado, memória, modelos carregados, arranque no boot e diagnóstico de
  conexão passo a passo.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import VERSION
from .ollama_client import OllamaClient

HEARTBEAT_STALE_S = 30
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    # processo zumbi (pai não fez wait) é considerado morto
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            tail = fh.read().rsplit(")", 1)
        state = tail[1].split()[0] if len(tail) > 1 and tail[1].split() else ""
        if state == "Z":
            return False
    except OSError:
        pass
    return True


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          check=False)  # rc é tratado por cada chamador


def python_env_check() -> dict:
    """Confere se as dependências Python estão íntegras.

    Detecta o caso do PyYAML 'quebrado': `import yaml` funciona mas o pacote
    está incompleto (sem safe_load/YAMLError) — típico de venv em disco
    NTFS/Windows ou instalação interrompida. Sem isso, /api/status vira 500.
    """
    import importlib

    missing = []
    for mod in ("flask", "requests", "yaml"):
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{mod} ({exc.__class__.__name__})")
    if missing:
        return {
            "name": "ambiente python",
            "ok": False,
            "detail": "não importou: " + ", ".join(missing)
                      + " — rode: ./.venv/bin/pip install -e .",
        }
    import yaml
    if not (hasattr(yaml, "safe_load") and hasattr(yaml, "YAMLError")):
        return {
            "name": "ambiente python",
            "ok": False,
            "detail": (
                f"PyYAML quebrado em {getattr(yaml, '__file__', '?')} — instalação "
                "incompleta (comum com projeto em disco NTFS). Conserte com: "
                "./.venv/bin/pip install --force-reinstall --no-cache-dir PyYAML"
            ),
        }
    return {"name": "ambiente python", "ok": True,
            "detail": "dependências íntegras (flask, requests, PyYAML)"}


class DaemonManager:
    """Controla o processo do agente (o 'coração' que executa tarefas)."""

    def __init__(self, cfg):
        self.cfg = cfg

    # ------------------------------------------------------------ status
    def _heartbeat(self) -> dict:
        try:
            return json.loads(self.cfg.heartbeat_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def status(self) -> dict:
        hb = self._heartbeat()
        pid = hb.get("pid")
        running = _pid_alive(pid)
        st = {
            "running": running,
            "pid": pid if running else None,
            "status": hb.get("status") if running else "desligado",
            "task": hb.get("task") if running else None,
            "started_at": hb.get("started_at") if running else None,
            "uptime_s": None,
            "stale": False,
        }
        if running:
            if hb.get("started_at"):
                st["uptime_s"] = round(max(0.0, time.time() - hb["started_at"]), 0)
            if time.time() - hb.get("ts", 0) > HEARTBEAT_STALE_S:
                st["stale"] = True
        return st

    # -------------------------------------------------------------- ações
    def start(self) -> dict:
        st = self.status()
        if st["running"]:
            return {"ok": False, "msg": f"o agente já está ligado (pid {st['pid']})"}
        self.cfg.ensure_dirs()
        self.cfg.heartbeat_path.unlink(missing_ok=True)
        with open(self.cfg.logfile, "a", encoding="utf-8") as lf:
            lf.write(f"\n===== [{time.strftime('%Y-%m-%d %H:%M:%S')}] solicitado pelo gerenciador "
                     f"(hermes-agent v{VERSION}) =====\n")
            lf.flush()
            proc = subprocess.Popen(
                [sys.executable, "-m", "hermes", "daemon"],
                cwd=str(PROJECT_ROOT),
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.time() + 12
        while time.time() < deadline:
            if proc.poll() is not None:  # morreu logo ao subir (e foi "colhido")
                return {"ok": False,
                        "msg": "o processo do agente morreu ao subir — veja logs/agent.log"}
            hb = self._heartbeat()
            if hb.get("pid") and _pid_alive(hb["pid"]):
                return {"ok": True, "msg": f"agente ligado (pid {hb['pid']})"}
            time.sleep(0.25)
        if self.status()["running"]:
            return {"ok": True, "msg": "agente ligado"}
        return {"ok": False, "msg": "o processo não subiu — veja os logs em logs/agent.log"}

    def stop(self) -> dict:
        st = self.status()
        if not st["running"]:
            self.cfg.heartbeat_path.unlink(missing_ok=True)
            return {"ok": True, "msg": "o agente já estava desligado"}
        pid = st["pid"]
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            return {"ok": False, "msg": f"falha ao sinalizar pid {pid}: {exc}"}
        deadline = time.time() + 12
        while time.time() < deadline:
            if not _pid_alive(pid):
                self.cfg.heartbeat_path.unlink(missing_ok=True)
                return {"ok": True, "msg": f"agente desligado (pid {pid})"}
            time.sleep(0.25)
        try:
            os.kill(pid, signal.SIGKILL)
            self.cfg.heartbeat_path.unlink(missing_ok=True)
            return {"ok": True, "msg": f"agente encerrado à força (pid {pid})"}
        except OSError:
            return {"ok": False, "msg": f"não consegui encerrar o pid {pid}"}

    def restart(self) -> dict:
        self.stop()
        time.sleep(0.4)
        return self.start()


class OllamaManager:
    """Detecta, liga, desliga e *monitora* o servidor Ollama.

    Fornece a visibilidade que o app desktop do Windows dá na bandeja:
    PID, tempo ligado, memória RSS, modelos carregados em memória/VRAM
    (API /api/ps), se sobe junto do boot (systemd) e um diagnóstico de
    conexão passo a passo com teste de geração real.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = OllamaClient(cfg.ollama_url)

    # ------------------------------------------------------------ detecção
    def _systemd(self) -> bool:
        """True se existe unidade systemd 'ollama' neste host."""
        if not shutil.which("systemctl"):
            return False
        try:
            return _run(["systemctl", "cat", "ollama"], timeout=8).returncode == 0
        except Exception:
            return False

    def _spawned_pid(self) -> int | None:
        try:
            return int(self.cfg.ollama_pidfile.read_text().strip() or 0)
        except Exception:
            return None

    def _find_pid(self) -> int | None:
        """Localiza o PID do servidor Ollama (nosso, systemd ou pgrep)."""
        pid = self._spawned_pid()
        if _pid_alive(pid):
            return pid
        if self._systemd():
            try:
                r = _run(["systemctl", "show", "-p", "MainPID", "--value", "ollama"], timeout=8)
                p = int((r.stdout or "0").strip() or 0)
                if p:
                    return p
            except Exception:
                pass
        try:
            r = _run(["pgrep", "-x", "ollama"], timeout=8)
            for line in (r.stdout or "").split():
                try:
                    p = int(line)
                except ValueError:
                    continue
                if _pid_alive(p):
                    return p
        except Exception:
            pass
        return None

    def _proc_info(self) -> dict:
        """PID, uptime e memória RSS do processo do Ollama (via /proc)."""
        info = {"pid": None, "uptime_s": None, "mem_mb": None}
        pid = self._find_pid()
        if not pid:
            return info
        info["pid"] = pid
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
                stat = fh.read()
            fields = stat.rsplit(")", 1)[1].split()
            starttime = int(fields[19])  # campo 22 (starttime) após o nome do processo
            hz = os.sysconf("SC_CLK_TCK")
            btime = 0
            with open("/proc/stat", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("btime"):
                        btime = int(line.split()[1])
                        break
            info["uptime_s"] = round(max(0.0, time.time() - (btime + starttime / hz)), 0)
        except Exception:
            pass
        try:
            with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        info["mem_mb"] = round(int(line.split()[1]) / 1024, 0)
                        break
        except Exception:
            pass
        return info

    def _boot_enabled(self) -> bool:
        if not self._systemd():
            return False
        try:
            r = _run(["systemctl", "is-enabled", "ollama"], timeout=8)
            return r.returncode == 0 and "enabled" in (r.stdout or "")
        except Exception:
            return False

    # -------------------------------------------------------------- status
    def status(self) -> dict:
        if self.cfg.mock:
            return {
                "installed": True,
                "running": True,
                "version": "simulado",
                "managed_by": "simulação (demonstração)",
                "models": ["hermes3:8b", "hermes3:3b"],
                "url": self.cfg.ollama_url,
                "pid": None,
                "uptime_s": None,
                "mem_mb": None,
                "loaded": [],
                "boot_enabled": False,
            }
        installed = shutil.which("ollama") is not None or self._systemd()
        running = self.client.is_running()
        info: dict = {
            "installed": installed,
            "running": running,
            "version": self.client.version() if running else None,
            "managed_by": None,
            "models": [],
            "url": self.cfg.ollama_url,
            "pid": None,
            "uptime_s": None,
            "mem_mb": None,
            "loaded": [],
            "boot_enabled": False,
        }
        if running:
            info["models"] = self.client.list_models()
            info["loaded"] = [m.get("name") for m in self.client.ps()]
            if self._systemd():
                info["managed_by"] = "systemd"
            elif _pid_alive(self._spawned_pid()):
                info["managed_by"] = "gerenciado pelo Hermes"
            else:
                info["managed_by"] = "processo externo"
            info.update(self._proc_info())
            info["boot_enabled"] = self._boot_enabled()
        return info

    # -------------------------------------------------------------- ações
    def start(self) -> dict:
        if self.cfg.mock:
            return {"ok": True, "msg": "modo demonstração: Ollama simulado já está 'ligado'"}
        if not shutil.which("ollama"):
            return {
                "ok": False,
                "msg": "Ollama não instalado. Instale com: curl -fsSL https://ollama.com/install.sh | sh "
                       "(ou rode ./install.sh do projeto)",
            }
        if self.client.is_running():
            return {"ok": False, "msg": "Ollama já está ligado"}

        if self._systemd():
            r = _run(["systemctl", "start", "ollama"])
            if r.returncode != 0:
                return {"ok": False, "msg": f"systemctl start ollama falhou: {r.stderr.strip()}"}
        else:
            self.cfg.data_dir.joinpath("logs").mkdir(parents=True, exist_ok=True)
            # noqa: SIM115 — o fd é herdado pelo filho e fechado no finally
            logf = open(self.cfg.data_dir / "logs" / "ollama.log", "ab")
            try:
                proc = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                logf.close()  # v3.14.2: o filho herda o fd; o pai fecha o seu
            self.cfg.ollama_pidfile.write_text(str(proc.pid), encoding="utf-8")

        deadline = time.time() + 40
        while time.time() < deadline:
            if self.client.is_running():
                who = "via systemd" if self._systemd() else "como processo gerenciado"
                return {"ok": True, "msg": f"Ollama ligado ({who})"}
            time.sleep(0.5)
        return {"ok": False, "msg": "Ollama subiu mas a API não respondeu em 40s — veja logs/ollama.log"}

    def stop(self) -> dict:
        if self.cfg.mock:
            return {"ok": True, "msg": "modo demonstração: nada a desligar"}
        if not self.client.is_running():
            return {"ok": True, "msg": "Ollama já está desligado"}
        if self._systemd():
            r = _run(["systemctl", "stop", "ollama"])
            if r.returncode != 0:
                return {"ok": False, "msg": f"systemctl stop ollama falhou: {r.stderr.strip()}"}
            return {"ok": True, "msg": "Ollama desligado (systemd)"}
        pid = self._spawned_pid()
        if _pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
            deadline = time.time() + 10
            while time.time() < deadline:
                if not _pid_alive(pid):
                    break
                time.sleep(0.3)
            if _pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
            self.cfg.ollama_pidfile.unlink(missing_ok=True)
            return {"ok": True, "msg": "Ollama desligado"}
        return {
            "ok": False,
            "msg": "o Ollama foi iniciado fora do Hermes; encerre-o manualmente "
                   "(ex.: pkill ollama)",
        }

    def restart(self) -> dict:
        if self.cfg.mock:
            return {"ok": True, "msg": "modo demonstração: nada a reiniciar"}
        self.stop()
        time.sleep(0.5)
        return self.start()

    def set_boot(self, enabled: bool) -> dict:
        """Liga/desliga a inicialização do Ollama junto do sistema (systemd)."""
        if self.cfg.mock:
            return {"ok": True, "msg": "modo demonstração"}
        if not self._systemd():
            return {
                "ok": False,
                "msg": "serviço systemd 'ollama' não encontrado — instale o Ollama pelo "
                       "instalador oficial para que ele crie o serviço",
            }
        cmd = (["systemctl", "enable", "--now", "ollama"] if enabled
               else ["systemctl", "disable", "--now", "ollama"])
        r = _run(cmd, timeout=30)
        if r.returncode == 0:
            acao = "inicializará junto do sistema" if enabled else "não inicializará junto do sistema"
            return {"ok": True, "msg": f"Ollama {acao}"}
        return {"ok": False, "msg": f"requer root — rode manualmente: sudo {' '.join(cmd)}"}

    # ---------------------------------------------------------- diagnóstico
    def diagnose(self, deep: bool = False) -> dict:
        """Verifica a conexão com o Ollama passo a passo.

        Passos: instalação, serviço/API, modelos instalados, modelo configurado
        e (deep=True) uma geração de teste real que mede a latência de ponta a
        ponta — a validação completa antes de usar o agente.
        """
        if self.cfg.mock:
            steps = [
                {"name": "instalação", "ok": True, "detail": "simulado (modo demonstração)"},
                {"name": "serviço / API", "ok": True,
                 "detail": f"{self.cfg.ollama_url} (simulado)"},
                {"name": "modelos instalados", "ok": True,
                 "detail": "hermes3:8b, hermes3:3b (simulados)"},
                {"name": "modelo configurado", "ok": True,
                 "detail": f"{self.cfg.model} (simulado)"},
            ]
            if deep:
                steps.append({"name": "geração de teste", "ok": True,
                              "detail": "simulado — resposta em 0.0s"})
            return {"ok": True, "steps": steps, "simulated": True}

        steps: list[dict] = []
        bin_path = shutil.which("ollama")
        steps.append({
            "name": "instalação",
            "ok": bin_path is not None,
            "detail": bin_path or "Ollama não instalado — rode: curl -fsSL https://ollama.com/install.sh | sh",
        })
        running = self.client.is_running()
        ver = self.client.version()
        steps.append({
            "name": "serviço / API",
            "ok": running,
            "detail": f"{self.cfg.ollama_url}" + (f" — versão {ver}" if ver else " (sem resposta)"),
        })
        models = self.client.list_models() if running else []
        steps.append({
            "name": "modelos instalados",
            "ok": bool(models),
            "detail": ", ".join(models) if models
            else "nenhum modelo — baixe na aba Ollama ou rode: ollama pull hermes3:8b",
        })
        cfg_ok = self.cfg.model in models
        steps.append({
            "name": "modelo configurado",
            "ok": cfg_ok,
            "detail": f"{self.cfg.model} " + ("disponível" if cfg_ok
                      else "NÃO instalado — baixe na aba Ollama"),
        })
        if deep:
            if running and cfg_ok:
                try:
                    res = self.client.test_generation(self.cfg.model)
                    steps.append({
                        "name": "geração de teste",
                        "ok": True,
                        "detail": f"respondeu «{res['response'].strip()[:40]}» em {res['latency_s']}s",
                    })
                except Exception as exc:
                    steps.append({"name": "geração de teste", "ok": False,
                                  "detail": str(exc)[:200]})
            else:
                steps.append({"name": "geração de teste", "ok": False,
                              "detail": "pulada — serviço ou modelo indisponíveis"})
        return {"ok": all(s["ok"] for s in steps), "steps": steps}
