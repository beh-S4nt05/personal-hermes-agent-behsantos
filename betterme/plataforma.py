# -*- coding: utf-8 -*-
"""🖥️ Plataforma — v6.0.0: Windows | macOS | Linux (modo local).

Camada ÚNICA de compatibilidade de SO: nada de os.kill/SIGKILL/
start_new_session/apt espalhados pelo código — todo módulo pergunta
aqui. Unix-ismos que QUEBRARIAM no Windows ficam atrás de branches
(o pior: ``os.kill(pid, 0)`` no Windows chama TerminateProcess —
mataria o processo em vez de testá-lo!).

- detecção por ``sys.platform`` (dinâmica → testável com override);
- ``liveness``/``matar`` cross-platform (Unix: sinais; Windows:
  OpenProcess/taskkill — NUNCA os.kill);
- ``shell_argv``: bash -c (Unix) · cmd /c (Windows);
- ``popen_destacado_kwargs``: start_new_session (Unix) ·
  CREATE_NEW_PROCESS_GROUP (Windows);
- ``hint``: instruções de instalação POR SO (apt/brew/winget);
- ``diag_commands``: comandos de diagnóstico reais por SO.
"""
from __future__ import annotations

import platform as _platform
import subprocess
import sys

# override para testes (None = detectar de verdade)
_SO_OVERRIDE: str | None = None


def so(_forcar: str | None = None) -> str:
    """'linux' | 'macos' | 'windows'."""
    alvo = _forcar or _SO_OVERRIDE
    if alvo:
        return alvo
    p = sys.platform
    if p.startswith("win"):
        return "windows"
    if p == "darwin":
        return "macos"
    return "linux"


def hostname() -> str:
    """Nome da máquina SEM depender de os.uname (inexistente no Windows)."""
    try:
        return _platform.node() or ""
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------- processos
def _liveness_unix(pid: int) -> bool:
    import os
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    try:                       # zumbi (pai não colheu) = morto p/ nós
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            tail = fh.read().rsplit(")", 1)
        partes = tail[1].split() if len(tail) > 1 else []
        if partes and partes[0] == "Z":
            return False
    except OSError:
        pass
    return True


def _liveness_windows(pid: int) -> bool:
    try:
        import ctypes
        k32 = ctypes.windll.kernel32      # type: ignore[attr-defined]
        QUERY = 0x1000                    # PROCESS_QUERY_LIMITED_INFORMATION
        STILL_ACTIVE = 259
        h = k32.OpenProcess(QUERY, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            k32.GetExitCodeProcess(h, ctypes.byref(code))
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return False


def liveness(pid: int | None) -> bool:
    """O processo está vivo? (cross-platform — nunca mata nada)."""
    if not pid or int(pid) <= 1:
        return False
    if so() == "windows":
        return _liveness_windows(int(pid))
    return _liveness_unix(int(pid))


def matar(pid: int, forcado: bool = False) -> bool:
    """Desce um processo (SIGTERM→SIGKILL no Unix; taskkill no Windows)."""
    if so() == "windows":
        argv = ["taskkill", "/PID", str(pid)] + (["/F"] if forcado else [])
        try:
            r = subprocess.run(argv, capture_output=True, timeout=15)
            return r.returncode == 0
        except Exception:  # noqa: BLE001
            return False
    import os
    import signal
    try:
        os.kill(int(pid), signal.SIGKILL if forcado else signal.SIGTERM)
        return True
    except OSError:
        return False


def popen_destacado_kwargs() -> dict:
    """Kwargs do Popen para filho que sobrevive ao pai (daemon/n8n)."""
    if so() == "windows":
        return {"creationflags":
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


# ------------------------------------------------------------- shell
def shell_argv(comando: str, _so_forcado: str | None = None) -> list[str]:
    """argv que executa um comando de shell no SO atual.
    Unix: bash -c (macOS tem /bin/bash de fábrica) · Windows: cmd /c."""
    if (_so_forcado or so()) == "windows":
        return ["cmd", "/c", comando]
    return ["bash", "-c", comando]


# ------------------------------------------------------------- hints
_HINTS: dict[str, dict[str, str]] = {
    "ffmpeg": {
        "linux": "sudo apt install ffmpeg",
        "macos": "brew install ffmpeg",
        "windows": "winget install Gyan.FFmpeg (ou baixe em ffmpeg.org "
                   "e adicione ao PATH)",
    },
    "poppler": {
        "linux": "sudo apt install poppler-utils",
        "macos": "brew install poppler",
        "windows": "baixe poppler-windows (github.com/oschwartz10612/"
                   "poppler-windows) e adicione a pasta bin/ ao PATH",
    },
    "node": {
        "linux": "sudo apt install nodejs npm (ou o setup da NodeSource)",
        "macos": "brew install node",
        "windows": "winget install OpenJS.NodeJS.LTS "
                   "(ou baixe o instalador em nodejs.org)",
    },
    "ollama": {
        "linux": "curl -fsSL https://ollama.com/install.sh | sh",
        "macos": "brew install ollama (ou baixe o app em ollama.com)",
        "windows": "baixe o OllamaSetup.exe em ollama.com "
                   "(ou winget install Ollama.Ollama)",
    },
    "ollama_start": {
        "linux": "sudo systemctl start ollama  (ou ative «ligar "
                 "automaticamente» na aba Ollama)",
        "macos": "brew services start ollama — ou abra o app do Ollama",
        "windows": "abra o app do Ollama (ícone na bandeja) — ele sobe "
                   "o servidor local sozinho",
    },
    "ollama_stop": {
        "linux": "pkill ollama",
        "macos": "pkill ollama",
        "windows": "taskkill /IM ollama.exe /F",
    },
}


def hint(programa: str, _so_forcado: str | None = None) -> str:
    """Instrução de instalação/execução PARA O SO ATUAL."""
    tabela = _HINTS.get(programa)
    if not tabela:
        return f"instale {programa}"
    return tabela.get(_so_forcado or so()) or tabela["linux"]


# ------------------------------------------------------------- diagnóstico
_DIAG_LINUX = [
    ("sistema",
     "uname -sr && (head -2 /etc/os-release | cut -d'\"' -f2 "
     "| tr '\n' ' '; echo)", 5),
    ("disco", "df -h | head -7", 5),
    ("memória", "free -h", 5),
    ("top RAM", "ps aux --sort=-%mem | head -7", 5),
    ("top CPU", "ps aux --sort=-%cpu | head -5", 5),
    ("maiores pastas da home",
     "du -xh --max-depth=1 ~ 2>/dev/null | sort -rh | head -10", 25),
    ("bateria",
     "for b in /sys/class/power_supply/BAT*; do "
     "echo $(cat $b/capacity 2>/dev/null)% "
     "$(cat $b/status 2>/dev/null); done", 3),
    ("GPU", "nvidia-smi --query-gpu=name,memory.total,memory.used,"
            "utilization.gpu --format=csv,noheader 2>/dev/null "
            "|| echo (sem nvidia-smi)", 8),
    ("uptime e carga", "uptime", 3),
    ("últimos logins",
     "last -n 4 -w 2>/dev/null | head -5 || echo (last indisponível)", 5),
]

_DIAG_MAC = [
    ("sistema", "sw_vers && sysctl -n machdep.cpu.brand_string", 5),
    ("memória", "vm_stat | head -4", 4),
    ("bateria", "pmset -g batt", 4),
    ("uptime e carga", "uptime", 3),
]

_DIAG_WIN = [
    ("sistema",
     'powershell -NoProfile -Command '
     '"[Environment]::OSVersion.VersionString"', 8),
    ("memória",
     'powershell -NoProfile -Command "Get-CimInstance '
     'Win32_OperatingSystem | ForEach-Object { '
     "[string]([math]::Round($_.FreePhysicalMemory/1MB,1)) "
     "+ ' GB livres de ' "
     "+ [string]([math]::Round($_.TotalVisibleMemorySize/1MB,1)) "
     "+ ' GB' }\"", 12),
    ("bateria",
     'powershell -NoProfile -Command "Get-CimInstance Win32_Battery | '
     'ForEach-Object { $_.EstimatedChargeRemaining }"', 8),
    ("disco",
     'powershell -NoProfile -Command "Get-PSDrive C | ForEach-Object { '
     "'C: livre ' + [string]([math]::Round($_.Free/1GB,1)) + ' GB' }\"",
     8),
]


def diag_commands(_so_forcado: str | None = None) -> list[tuple]:
    """[(nome, comando, timeout)] reais para o SO atual."""
    s = _so_forcado or so()
    if s == "windows":
        return list(_DIAG_WIN)
    if s == "macos":
        return list(_DIAG_MAC)
    return list(_DIAG_LINUX)
