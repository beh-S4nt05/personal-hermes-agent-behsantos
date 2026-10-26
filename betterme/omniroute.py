"""🔀 Omniroute local — gateway grátis de LLMs (v6.5.0).

Omniroute (MIT, npm `omniroute`) é um gateway que roda NA máquina e
roteia para pools gratuitos — vários keyless (Pollinations, Cloudflare
AI, …) — expondo UM endpoint OpenAI-compatible em :20128/v1.

Integração com o Betterme:
- `betterme omniroute setup|start|stop|status|apikey|remover`
  (mesmo padrão do ⚙ fluxos/n8n: instala no data-dir, removível);
- provedor `omniroute` no REGISTRY (llm_providers): o roteador de
  cérebro o usa automaticamente quando está rodando (última prioridade
  — provedor direto com chave é sempre melhor que gateway);
- D2 inalterada: o transporte passa pelo DLP `mascarar()` como qualquer
  provedor externo (o gateway repassa a terceiros).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .contratos import acao_de

PORTA = 20128
_PACOTE = "omniroute"

# processos filhos DESTE processo (mesma defesa do fluxos.py)
_PROCS: dict[int, object] = {}


def _dir(cfg) -> Path:
    return Path(cfg.data_dir) / "omniroute"


def bin_omniroute(cfg) -> Path:
    return _dir(cfg) / "node_modules" / ".bin" / "omniroute"


def _pid_file(cfg) -> Path:
    return _dir(cfg) / "omniroute.pid"


def instalado(cfg) -> bool:
    return bin_omniroute(cfg).exists()


def rodando(cfg) -> bool:
    pid_f = _pid_file(cfg)
    if not pid_f.is_file():
        return False
    try:
        pid = int(pid_f.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_f.unlink(missing_ok=True)
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        pid_f.unlink(missing_ok=True)
        return False


# ------------------------------------------------------------- api key
def _key_path(cfg) -> Path:
    # mesmo convenio do llm_providers: secrets/omniroute.key
    return Path(cfg.data_dir) / "secrets" / "omniroute.key"


def salvar_apikey(cfg, key: str) -> Path:
    f = _key_path(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(str(key).strip(), encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass
    return f


def ler_apikey(cfg) -> str:
    try:
        return _key_path(cfg).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ------------------------------------------------------------- setup
def setup(cfg, npm_bin: str = "npm") -> dict:
    """Instala o omniroute LOCAL (npm --prefix no data-dir).
    E2E real (out/2026, omniroute 3.8.52): exige Node ≥ 23 (Node 20
    quebra em util.markAsUncloneable); n8n aceita 20.19–24 — Node 24
    atende os dois."""
    from .fluxos import node_versao
    if not (shutil.which("node") and shutil.which(npm_bin)):
        return {"ok": False,
                "msg": "Node.js/npm não encontrados — instale o Node 24 "
                       "(o omniroute é um servidor Node)"}
    v = node_versao()
    if v and v < (23, 0):
        return {"ok": False,
                "msg": f"omniroute exige Node 23+ (atual: {v[0]}.{v[1]}) "
                       "— o n8n aceita 20.19–24.x; instale o Node 24 para "
                       "os dois"}
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([npm_bin, "install", "--prefix", str(d),
                            _PACOTE], timeout=1800)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "msg": f"npm install falhou: {exc}"}
    if r.returncode != 0 or not instalado(cfg):
        return {"ok": False,
                "msg": "npm install não concluiu — veja a saída do npm acima"}
    try:
        from . import activity
        activity.log(cfg, "omniroute", f"🔀 omniroute instalado em {d}")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True,
            "msg": f"omniroute instalado em {d} (local e removível: "
                   "`betterme omniroute remover`)"}


# ------------------------------------------------------------- runtime
def start(cfg) -> dict:
    if not instalado(cfg):
        return {"ok": False,
                "msg": "omniroute não instalado — rode primeiro: "
                       "`betterme omniroute setup`"}
    if rodando(cfg):
        return {"ok": True, "msg": "omniroute já está rodando", "pid": None}
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    log = d / "omniroute.log"
    from . import plataforma
    with log.open("ab") as fh:
        proc = subprocess.Popen([str(bin_omniroute(cfg))],
                                env=dict(os.environ),
                                stdout=fh, stderr=fh, cwd=str(d),
                                **plataforma.popen_destacado_kwargs())
    _pid_file(cfg).write_text(str(proc.pid), encoding="utf-8")
    _PROCS[proc.pid] = proc
    try:
        from . import activity
        activity.log(cfg, "omniroute",
                     f"🔀 omniroute iniciado (pid {proc.pid}, "
                     f"porta {PORTA})")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "pid": proc.pid,
            "msg": f"omniroute iniciado (pid {proc.pid}) — endpoint "
                   f"http://127.0.0.1:{PORTA}/v1 (model 'auto') · "
                   f"dashboard http://127.0.0.1:{PORTA} · log: {log}"}


def stop(cfg) -> dict:
    pid_f = _pid_file(cfg)
    if not pid_f.is_file():
        return {"ok": True, "msg": "omniroute não está rodando"}
    from . import plataforma
    try:
        pid = int(pid_f.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_f.unlink(missing_ok=True)
        return {"ok": True, "msg": "omniroute parado"}
    plataforma.matar(pid)
    _PROCS.pop(pid, None)
    pid_f.unlink(missing_ok=True)
    return {"ok": True, "msg": f"omniroute parado (pid {pid})"}


def remover(cfg) -> dict:
    stop(cfg)
    import shutil as _sh
    apagou = []
    for d in (_dir(cfg),):
        if d.exists():
            _sh.rmtree(d, ignore_errors=True)
            apagou.append(d.name)
    try:
        _key_path(cfg).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True,
            "msg": "omniroute removido por completo ("
                   + (", ".join(apagou) if apagou else "nada a apagar")
                   + ") — o Betterme segue intacto"}


def status(cfg) -> dict:
    return {"ok": True,
            "instalado": instalado(cfg),
            "rodando": rodando(cfg) if instalado(cfg) else False,
            "porta": PORTA,
            "api_key": bool(ler_apikey(cfg)),
            "endpoint": f"http://127.0.0.1:{PORTA}/v1 · model 'auto'",
            "diretorio": str(_dir(cfg))}


# ------------------------------------------------------------- CLI
def cmd(args, cfg) -> None:
    """`betterme omniroute status|setup|start|stop|apikey|remover`."""
    acao = acao_de(args)
    if acao == "status":
        st = status(cfg)
        print(f"🔀 OMNIROUTE — gateway local de LLMs grátis (porta "
              f"{st['porta']})")
        inst = "✔" if st["instalado"] else "✖ (betterme omniroute setup)"
        print(f"  instalado: {inst}")
        rod = ("✔ sim" if st["rodando"]
               else "✖ não — ligue com: betterme omniroute start")
        print(f"  rodando: {rod}")
        print(f"  endpoint: {st['endpoint']}")
        print(f"  api key local: {'✔' if st['api_key'] else '— (keyless ok)'}")
        print(f"  instalação: {st['diretorio']}")
        print("  remover tudo: betterme omniroute remover")
        return
    if acao == "setup":
        r = setup(cfg, npm_bin=str(getattr(args, "npm", None) or "npm"))
        print(("✔ " if r["ok"] else "✖ ") + r["msg"])
        if r["ok"]:
            print("  próximo passo: betterme omniroute start")
        return
    if acao == "start":
        r = start(cfg)
        print(("✔ " if r["ok"] else "✖ ") + r["msg"])
        if r["ok"]:
            print("  valide: betterme provider test omniroute")
        return
    if acao == "stop":
        print("✔ " + stop(cfg)["msg"])
        return
    if acao == "apikey":
        key = str(getattr(args, "id", "") or "").strip()
        if not key:
            print("✖ informe a chave: betterme omniroute apikey <chave>")
            raise SystemExit(1)
        f = salvar_apikey(cfg, key)
        print(f"✔ api key do omniroute salva em {f} (600) — o provedor "
              "`omniroute` já pode usar")
        return
    if acao == "remover":
        print("✔ " + remover(cfg)["msg"])
        return
    print(f"✖ ação desconhecida: {acao!r} "
          "(status|setup|start|stop|apikey|remover)")
    raise SystemExit(1)
