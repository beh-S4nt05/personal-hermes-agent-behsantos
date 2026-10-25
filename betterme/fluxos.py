# -*- coding: utf-8 -*-
"""⚙️ Fluxos n8n locais — v5.1.0 (PR #11).

O n8n (Community, Sustainable Use License) EMBUTIDO no Betterme:
construa automações visuais dentro do GUI, grátis e locais.

- **Grátis para uso pessoal/interno** (Sustainable Use License — o
  pago é só hospedar para terceiros/white-label, que não é o caso).
- **Local-first:** instalação via npm DENTRO do data-dir
  (`<data>/fluxos/`), dados/workflows em `<data>/fluxos-user/`,
  telemetria DESLIGADA. Nada no sistema, nada na nuvem.
- **Removível:** `betterme fluxos remover` apaga instalação, perfil e
  workflows (o repo público do Betterme só tem o código desta
  integração — não redistribui o n8n).
- **GUI:** página `/fluxos` (aba ⚙ Fluxos) com o editor embutido em
  iframe (localhost) + "abrir em nova aba" como fallback.
- **Integração nos 2 sentidos:** a tool `fluxos_chamar` dispara
  workflows por webhook (skills do Betterme → n8n); nós HTTP do n8n
  chamam a API local do Betterme (POST sem Origin já passa no CSRF —
  T34; use auth_token em produção).

Requisito: Node.js 20.19–24.x (o 24 do operador ✔). Degradação
honesta sem Node/npm/n8n — nunca quebra.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from .contratos import acao_de

PORTA = 5678


def _dir(cfg) -> Path:
    return Path(cfg.data_dir) / "fluxos"


def _user_dir(cfg) -> Path:
    return Path(cfg.data_dir) / "fluxos-user"


def n8n_bin(cfg) -> Path:
    return _dir(cfg) / "node_modules" / ".bin" / "n8n"


def _pid_file(cfg) -> Path:
    return _dir(cfg) / "n8n.pid"


# processos filhos DESTE processo (start+stop na mesma sessão — evita
# zumbis; via CLI o init re-parenta e reapa sozinho)
_PROCS: dict[int, object] = {}


# ------------------------------------------------------------- node/npm
def node_versao(node_bin: str = "node") -> tuple[int, int] | None:
    try:
        r = subprocess.run([node_bin, "--version"], capture_output=True,
                           text=True, timeout=15)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    m = re.match(r"v(\d+)\.(\d+)", (r.stdout or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def node_ok(node_bin: str = "node") -> tuple[bool, str]:
    """n8n 2.x exige Node entre 20.19 e 24.x (verificado out/2026)."""
    v = node_versao(node_bin)
    if not v:
        return False, ("Node.js não encontrado — instale o Node 22 ou 24 "
                       "(apt via nodesource, ou nvm); o n8n exige "
                       "20.19–24.x")
    major, minor = v
    if (major == 20 and minor >= 19) or major in (22, 24):
        return True, f"Node {major}.{minor} ✔ (n8n exige 20.19–24.x)"
    return False, (f"Node {major}.{minor} não é suportado pelo n8n "
                   "(precisa entre 20.19 e 24.x — instale o 22 ou 24)")


# ------------------------------------------------------------- setup
def setup(cfg, node_bin: str = "node", npm_bin: str = "npm") -> dict:
    """Instala o n8n LOCAL (npm --prefix no data-dir). Requisito: node."""
    ok, msg = node_ok(node_bin)
    if not ok:
        return {"ok": False, "msg": msg}
    if not (shutil.which(npm_bin) or Path(npm_bin).exists()):
        return {"ok": False,
                "msg": "npm não encontrado — instale o Node.js (vem com npm)"}
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([npm_bin, "install", "--prefix", str(d), "n8n"],
                           timeout=1800)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "msg": f"npm install falhou: {exc}"}
    if r.returncode != 0 or not n8n_bin(cfg).exists():
        return {"ok": False,
                "msg": "npm install não concluiu — veja a saída do npm acima"}
    try:
        from . import activity
        activity.log(cfg, "fluxos", f"⚙ n8n instalado localmente em {d}")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True,
            "msg": f"n8n instalado em {d} (local e removível: "
                   "`betterme fluxos remover`)"}


# ------------------------------------------------------------- runtime
def _env(cfg) -> dict:
    env = dict(os.environ)
    env.update({
        "N8N_PORT": str(PORTA),
        "N8N_HOST": "127.0.0.1",
        "N8N_LISTEN_ADDRESS": "127.0.0.1",
        "N8N_USER_FOLDER": str(_user_dir(cfg)),
        # local-first: telemetria/personalização/version-check DESLIGADOS
        "N8N_DIAGNOSTICS_ENABLED": "false",
        "N8N_PERSONALIZATION_ENABLED": "false",
        "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
        "N8N_SECURE_COOKIE": "false",
        # iframe no GUI local (só escuta 127.0.0.1; fallback: nova aba)
        "N8N_DISABLE_UI_SECURITY": "true",
    })
    return env


def instalado_leve(cfg) -> bool:
    """v6.3.2: n8n instalado? (só filesystem — rápido p/ doctor)."""
    return n8n_bin(cfg).exists()


def rodando(cfg) -> bool:
    from . import plataforma
    pid_f = _pid_file(cfg)
    if not pid_f.is_file():
        return False
    try:
        pid = int(pid_f.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_f.unlink(missing_ok=True)     # pid ilegível → arquivo órfão
        return False
    if plataforma.liveness(pid):
        return True
    pid_f.unlink(missing_ok=True)         # pid morto → arquivo órfão
    return False


def start(cfg) -> dict:
    bin_ = n8n_bin(cfg)
    if not bin_.exists():
        return {"ok": False,
                "msg": "n8n não instalado — rode primeiro: "
                       "`betterme fluxos setup`"}
    if rodando(cfg):
        return {"ok": True, "msg": "n8n já está rodando", "pid": None}
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    log = d / "n8n.log"
    from . import plataforma
    with log.open("ab") as fh:
        proc = subprocess.Popen([str(bin_)], env=_env(cfg),
                                stdout=fh, stderr=fh, cwd=str(d),
                                **plataforma.popen_destacado_kwargs())
    _pid_file(cfg).write_text(str(proc.pid), encoding="utf-8")
    _PROCS[proc.pid] = proc
    try:
        from . import activity
        activity.log(cfg, "fluxos",
                     f"⚙ n8n iniciado (pid {proc.pid}, porta {PORTA})")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "pid": proc.pid,
            "msg": f"n8n iniciado (pid {proc.pid}) — editor em "
                   f"http://127.0.0.1:{PORTA} · log: {log}"}


def stop(cfg) -> dict:
    pid_f = _pid_file(cfg)
    if not pid_f.is_file():
        return {"ok": True, "msg": "n8n não está rodando"}
    from . import plataforma
    try:
        pid = int(pid_f.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_f.unlink(missing_ok=True)
        return {"ok": True, "msg": "n8n parado"}
    plataforma.matar(pid)
    for _ in range(40):                   # até 10 s para descer
        time.sleep(0.25)
        if not plataforma.liveness(pid):
            break
    else:
        plataforma.matar(pid, forcado=True)
    proc = _PROCS.pop(pid, None)
    if proc is not None:                 # reap do filho (anti-zumbi)
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
    pid_f.unlink(missing_ok=True)
    return {"ok": True, "msg": "n8n parado"}


def remover(cfg) -> dict:
    """Apaga instalação + perfil + workflows (removível de verdade)."""
    stop(cfg)
    for d in (_dir(cfg), _user_dir(cfg)):
        shutil.rmtree(d, ignore_errors=True)
    try:
        from . import activity
        activity.log(cfg, "fluxos", "⚙ n8n removido (instalação+perfil)")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "msg": "n8n removido por completo (instalação, "
                               "perfil e workflows)"}


def chamar(cfg, caminho: str, payload: dict, _post=None,
            timeout: int = 60) -> dict:
    """v6.3.0: dispara um workflow por webhook local (tool do cérebro).
    Espera a resposta do workflow (nó "Respond to Webhook" no n8n)."""
    caminho = str(caminho or "").strip().strip("/")
    if not caminho:
        return {"ok": False, "msg": "informe o caminho do webhook "
                                    "(id ou path do workflow)"}
    url = f"http://127.0.0.1:{PORTA}/webhook/{caminho}"

    def _mapa(res: dict) -> dict:
        if res.get("status") == 404:
            res["ok"] = False
            res["msg"] = ("webhook respondeu 404 — o workflow não está "
                          "ATIVO ou o caminho mudou (ative no editor n8n "
                          "e confira o Production URL)")
        return res

    if _post is not None:
        return _mapa(_post(url, payload or {}))
    import requests
    try:
        r = requests.post(url, json=payload or {}, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "msg": f"n8n não respondeu em {url} — rode "
                       f"`betterme fluxos start` ({exc.__class__.__name__})"}
    return _mapa({"ok": r.status_code < 400, "status": r.status_code,
                  "msg": (r.text or "")[:500]})


# ------------------------------------------------- API pública do n8n
def _key_path(cfg) -> Path:
    return Path(cfg.data_dir) / "secrets" / "n8n.key"


def salvar_apikey(cfg, key: str) -> Path:
    """API key do n8n (Settings → n8n API) em secrets/ com chmod 600."""
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


def listar(cfg, _get=None) -> dict:
    """v6.3.0: lista os workflows do n8n via API pública local."""
    if not rodando(cfg):
        return {"ok": False, "msg": "n8n não está rodando — "
                                    "`betterme fluxos start`"}
    key = ler_apikey(cfg)
    if not key:
        return {"ok": False, "msg": "sem API key — crie no editor do n8n "
                                    "(Settings → n8n API) e rode: "
                                    "`betterme fluxos apikey <chave>`"}
    url = f"http://127.0.0.1:{PORTA}/api/v1/workflows?limit=50"
    if _get is not None:
        dados = _get(url, key)
    else:
        import requests
        try:
            r = requests.get(url, headers={"X-N8N-API-KEY": key},
                             timeout=15)
            dados = r.json() if r.status_code == 200 else {"erro": r.text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "msg": f"API do n8n falhou: "
                                        f"{exc.__class__.__name__}"}
    if "erro" in dados or not isinstance(dados.get("data"), list):
        return {"ok": False, "msg": "resposta inesperada da API do n8n — "
                                    "confira a API key"}
    wfs = []
    for w in dados["data"]:
        # v6.3.2: paths de webhook de cada workflow — permite o cérebro
        # ir de "dispare o Backup diário" ao path certo (fluxos_listar)
        hooks = sorted({str((n.get("parameters") or {}).get("path"))
                        for n in (w.get("nodes") or [])
                        if isinstance(n, dict)
                        and str(n.get("type") or "").endswith("webhook")
                        and (n.get("parameters") or {}).get("path")})
        wfs.append({"id": w.get("id"), "nome": w.get("name"),
                    "ativo": bool(w.get("active")),
                    "nos": len(w.get("nodes") or []),
                    "webhooks": hooks})
    return {"ok": True, "workflows": wfs}


def status(cfg, node_bin: str = "node") -> dict:
    ok_node, msg_node = node_ok(node_bin)
    instalado = instalado_leve(cfg)
    return {"ok": True, "node_ok": ok_node, "node_msg": msg_node,
            "npm": bool(shutil.which("npm")),
            "n8n_instalado": instalado,
            "rodando": rodando(cfg) if instalado else False,
            "porta": PORTA,
            "api_key": bool(ler_apikey(cfg)),
            # v6.3.0: gatilho n8n → Betterme (tarefa agendada tipo webhook)
            "hook_url": (f"http://127.0.0.1:{getattr(cfg, 'port', 8080)}"
                         "/api/hooks/<id-da-tarefa-agendada>"),
            "diretorio": str(_dir(cfg)),
            "user_dir": str(_user_dir(cfg))}


# ------------------------------------------------------------- CLI
def cmd(args, cfg) -> None:
    """`betterme fluxos status|setup|start|stop|remover`."""
    acao = acao_de(args)
    if acao == "status":
        st = status(cfg, node_bin=getattr(args, "node", None) or "node")
        print(f"⚙ FLUXOS n8n — porta {st['porta']}")
        print(f"  node: {st['node_msg']}")
        print(f"  npm: {'✔' if st['npm'] else '✖ não encontrado'}")
        inst = "✔" if st["n8n_instalado"] else "✖ (betterme fluxos setup)"
        print(f"  n8n instalado: {inst}")
        rod = ("✔ sim" if st["rodando"] else
          "✖ não — ligue com: betterme fluxos start")
        print(f"  rodando: {rod}")
        print(f"  instalação: {st['diretorio']}")
        print(f"  dados/workflows: {st['user_dir']}")
        print("  remover tudo: betterme fluxos remover")
        return
    if acao == "setup":
        r = setup(cfg, node_bin=getattr(args, "node", None) or "node",
                  npm_bin=getattr(args, "npm", None) or "npm")
        print(("✔ " if r["ok"] else "✖ ") + r["msg"])
        if not r["ok"]:
            raise SystemExit(1)
        return
    if acao == "start":
        r = start(cfg)
        print(("✔ " if r["ok"] else "✖ ") + r["msg"])
        if not r["ok"]:
            raise SystemExit(1)
        return
    if acao == "stop":
        print("✔ " + stop(cfg)["msg"])
        return
    if acao == "remover":
        print("✔ " + remover(cfg)["msg"])
        return
    if acao == "apikey":
        key = str(getattr(args, "id", "") or "").strip()
        if not key:
            print("✖ informe a chave: betterme fluxos apikey <chave>")
            raise SystemExit(1)
        f = salvar_apikey(cfg, key)
        print(f"✔ API key do n8n salva em {f} (600) — "
              "`betterme fluxos listar` agora funciona")
        return
    if acao == "listar":
        r = listar(cfg)
        if not r.get("ok"):
            print("✖ " + r["msg"])
            raise SystemExit(1)
        print(f"⛓ {len(r['workflows'])} workflow(s) no n8n local:")
        for w in r["workflows"]:
            estado = "🟢 ativo" if w["ativo"] else "⚪ inativo"
            print(f"  · {w['nome']} ({w['nos']} nós) {estado} · id "
                  f"{w['id']}")
        return
    if acao == "abrir":
        import webbrowser
        try:
            webbrowser.open(f"http://127.0.0.1:{PORTA}")
            print(f"✔ abrindo o editor em http://127.0.0.1:{PORTA}")
        except Exception:  # noqa: BLE001
            print(f"ℹ abra manualmente: http://127.0.0.1:{PORTA}")
        return
    print(f"✖ ação desconhecida: {acao!r} "
          "(status|setup|start|stop|apikey|listar|abrir|remover)")
    raise SystemExit(1)
