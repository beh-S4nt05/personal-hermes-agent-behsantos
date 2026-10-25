"""Sandbox de kernel — v4.0.0 (M4).

Isolamento em nível de KERNEL para os comandos do agente (o que o Codex
faz no Linux): bubblewrap para filesystem/namespaces + filtro seccomp
(blocklist de syscalls perigosas) — não é promessa no prompt.

Camadas (defesa em profundidade):
  1. kernel: bwrap (fs/namespace) + seccomp (syscalls)   ← este módulo
  2. app: denylist is_dangerous/touches_secrets + escopo  ← tools.py

Degradação honesta (pre-mortem #3/#4): sem bwrap (ou userns bloqueado
em container), o agente segue na camada 2 com aviso no log — nunca
quebra. Modos: ``auto`` (default: kernel se disponível) · ``kernel``
(exige; avisa se cair) · ``app`` (só denylist, como na v3.x).
"""
from __future__ import annotations

import os
import platform
import shutil
import struct
import subprocess

# ------------------------------------------------------- seccomp (BPF)
_BPF_LD_W_ABS = 0x20           # BPF_LD | BPF_W | BPF_ABS
_BPF_JMP_JEQ_K = 0x15          # BPF_JMP | BPF_JEQ | BPF_K
_BPF_RET_K = 0x06              # BPF_RET | BPF_K
_RET_ALLOW = 0x7FFF0000
_RET_ERRNO_EPERM = 0x00050000 | 1          # SECCOMP_RET_ERRNO | EPERM
_ARCH_X86_64 = 0xC000003E

# blocklist (não allowlist — pre-mortem #4): syscalls que um agente de
# tarefas NUNCA precisa; números são de x86_64 (aarch64 fica sem seccomp)
_BLOCKLIST_X86_64 = {
    101: "ptrace", 165: "mount", 166: "umount2", 175: "init_module",
    176: "delete_module", 246: "kexec_load", 250: "keyctl",
    298: "perf_event_open", 303: "name_to_handle_at",
    304: "open_by_handle_at", 313: "finit_module", 321: "bpf",
    323: "userfaultfd",
}


def bpf_blocklist() -> bytes:
    """Programa seccomp clássico: arch x86_64 + blocklist -> EPERM; resto
    ALLOW. Serializado como instruções sock_filter (8 bytes cada)."""
    prog: list[tuple[int, int, int, int]] = [
        (_BPF_LD_W_ABS, 0, 0, 4),                 # ld arch
        (_BPF_JMP_JEQ_K, 1, 0, _ARCH_X86_64),     # x86_64? pula o kill
        (_BPF_RET_K, 0, 0, _RET_ERRNO_EPERM),     # arch estranho → EPERM
    ]
    nrs = sorted(_BLOCKLIST_X86_64)
    idx_errno = 3 + 2 * len(nrs)                  # bloco ERRNO no fim
    for i, nr in enumerate(nrs):
        prog.append((_BPF_LD_W_ABS, 0, 0, 0))     # ld nr
        jt = idx_errno - (4 + 2 * i) - 1          # pula para o ERRNO
        prog.append((_BPF_JMP_JEQ_K, jt, 0, nr))  # bloqueado → EPERM
    prog.append((_BPF_RET_K, 0, 0, _RET_ERRNO_EPERM))
    prog.append((_BPF_RET_K, 0, 0, _RET_ALLOW))
    return b"".join(struct.pack("=HBBI", *ins) for ins in prog)


def _seccomp_fd() -> int | None:
    """fd de pipe com o filtro; caller fecha depois do spawn."""
    if platform.machine() not in ("x86_64", "amd64"):
        return None                              # números p/ x86_64 apenas
    try:
        r, w = os.pipe()
        os.write(w, bpf_blocklist())
        os.close(w)                              # EOF: bwrap lê e fecha
        return r
    except OSError:
        return None


# ------------------------------------------------------- probe/nível
_probe_cache: str | None = None
_probe_feito = False


def disponivel() -> bool:
    return shutil.which("bwrap") is not None


def probe() -> str | None:
    """"seccomp" | "kernel" | None — testa de verdade (userns pode estar
    bloqueado em container; seccomp pode não ser aceito). Cacheado."""
    global _probe_cache, _probe_feito
    if _probe_feito:
        return _probe_cache
    _probe_feito = True
    _probe_cache = None
    if not disponivel():
        return None
    base = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev",
            "--proc", "/proc", "--"]
    try:
        r = subprocess.run(base + ["true"], capture_output=True, timeout=15)
        if r.returncode == 0:
            _probe_cache = "kernel"
    except Exception:  # noqa: BLE001
        return None
    if _probe_cache == "kernel":
        fd = _seccomp_fd()
        if fd is not None:
            try:
                r2 = subprocess.run(
                    base + ["--seccomp", f"/dev/fd/{fd}", "true"],
                    capture_output=True, timeout=15, pass_fds=(fd,))
                if r2.returncode == 0:
                    _probe_cache = "seccomp"
            except Exception:  # noqa: BLE001
                pass
            finally:
                os.close(fd)
    return _probe_cache


def nivel(cfg) -> str | None:
    """Modo resolvido: 'seccomp'/'kernel' (kernel ativo) ou None (app)."""
    modo = str(getattr(cfg, "sandbox_mode", "auto") or "auto").lower()
    if modo in ("app", "off", "desligado"):
        return None
    p = probe()
    if modo == "kernel" and p is None:
        try:
            from . import activity
            activity.log(cfg, "sandbox",
                         "⚠ sandbox de kernel exigido mas indisponível "
                         "(bwrap ausente/userns bloqueado) — usando denylist")
        except Exception:  # noqa: BLE001
            pass
    return p


# ------------------------------------------------------- envolver
def envolver_comando(cfg, argv: list[str], workdir: str,
                     modo: str = "workspace-write", net: bool = True):
    """Wrapper de uso: consulta o nível do cfg e embrulha quando ativo."""
    if not getattr(cfg, "sandbox", True):
        return argv, ()
    nv = nivel(cfg)
    if nv is None:
        return argv, ()
    base = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev",
            "--proc", "/proc"]
    if modo == "workspace-write" and workdir:
        base += ["--bind", str(workdir), str(workdir)]
    if not net:
        base += ["--unshare-net"]                 # kernel desliga a rede
    fds: tuple[int, ...] = ()
    if nv == "seccomp":
        fd = _seccomp_fd()
        if fd is not None:
            base += ["--seccomp", f"/dev/fd/{fd}"]
            fds = (fd,)
    return base + ["--"] + list(argv), fds


def fechar_fds(fds: tuple[int, ...]) -> None:
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass
