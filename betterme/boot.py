# -*- coding: utf-8 -*-
"""🔘 Boot — v6.0.0: iniciar com o sistema (Windows | macOS | Linux).

Autostart LOCAL do daemon, por SO, sempre reversível:

- **Linux:** unidade systemd de USUÁRIO em `~/.config/systemd/user/`
  (sem root) + `systemctl --user enable --now`.
- **macOS:** LaunchAgent em `~/Library/LaunchAgents/` + `launchctl`.
- **Windows:** `.bat` na pasta Inicialização do usuário
  (`...\\Startup`) — sem administrador, sobre ao logon.

`betterme boot off` devolve a máquina ao estado anterior (remove o
que foi criado). O comando do daemon é sempre o Python DA MÁQUINA
(`sys.executable -m betterme daemon`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _spec(_so_forcado: str | None = None) -> dict:
    """Caminho + conteúdo + comandos de (des)habilitar por SO."""
    from .plataforma import so
    alvo = _so_forcado or so()
    py = sys.executable
    if alvo == "linux":
        f = (Path.home() / ".config" / "systemd" / "user"
             / "betterme-agent.service")
        conteudo = (
            "[Unit]\n"
            "Description=Betterme Agent (daemon local)\n"
            "\n"
            "[Service]\n"
            f"ExecStart={py} -m betterme daemon\n"
            "Restart=on-failure\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n")
        return {"so": alvo, "arquivo": f, "conteudo": conteudo,
                "habilitar": ["systemctl", "--user", "enable", "--now",
                              "betterme-agent"],
                "desabilitar": ["systemctl", "--user", "disable", "--now",
                                "betterme-agent"]}
    if alvo == "macos":
        f = (Path.home() / "Library" / "LaunchAgents"
             / "com.betterme.agent.plist")
        conteudo = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "  <key>Label</key><string>com.betterme.agent</string>\n"
            "  <key>ProgramArguments</key>\n"
            "  <array>\n"
            f"    <string>{py}</string>\n"
            "    <string>-m</string>\n"
            "    <string>betterme</string>\n"
            "    <string>daemon</string>\n"
            "  </array>\n"
            "  <key>RunAtLoad</key><true/>\n"
            "  <key>KeepAlive</key><false/>\n"
            "</dict>\n"
            "</plist>\n")
        return {"so": alvo, "arquivo": f, "conteudo": conteudo,
                "habilitar": ["launchctl", "load", "-w", str(f)],
                "desabilitar": ["launchctl", "unload", "-w", str(f)]}
    # windows — .bat na Inicialização (sem admin)
    f = (Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows"
         / "Start Menu" / "Programs" / "Startup" / "betterme-agent.bat")
    conteudo = (f'@echo off\r\n'
                f'start "" /min "{py}" -m betterme daemon\r\n')
    return {"so": alvo, "arquivo": f, "conteudo": conteudo,
            "habilitar": None, "desabilitar": None}


def on(cfg) -> dict:
    """Registra o autostart (escreve o arquivo + habilita no SO)."""
    spec = _spec()
    try:
        spec["arquivo"].parent.mkdir(parents=True, exist_ok=True)
        spec["arquivo"].write_text(spec["conteudo"], encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "msg": f"não consegui escrever "
                                    f"{spec['arquivo']}: {exc}"}
    if spec["habilitar"]:
        try:
            subprocess.run(spec["habilitar"], capture_output=True,
                           timeout=30)
        except Exception:  # noqa: BLE001
            pass            # arquivo escrito; serviço ativa no próximo boot
    try:
        from . import activity
        activity.log(cfg, "boot",
                     f"🔘 autostart registrado ({spec['so']}: "
                     f"{spec['arquivo'].name})")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True,
            "msg": f"autostart registrado ({spec['so']}): "
                   f"{spec['arquivo']} — `betterme boot off` remove"}


def off(cfg) -> dict:
    """Remove o autostart (desabilita + apaga o arquivo)."""
    spec = _spec()
    if not spec["arquivo"].exists():
        return {"ok": True, "msg": "autostart não estava registrado"}
    if spec["desabilitar"]:
        try:
            subprocess.run(spec["desabilitar"], capture_output=True,
                           timeout=30)
        except Exception:  # noqa: BLE001
            pass
    try:
        spec["arquivo"].unlink(missing_ok=True)
    except OSError as exc:
        return {"ok": False, "msg": f"não consegui remover "
                                    f"{spec['arquivo']}: {exc}"}
    return {"ok": True, "msg": "autostart removido"}


def status(cfg) -> dict:
    spec = _spec()
    return {"ok": True, "so": spec["so"],
            "registrado": spec["arquivo"].exists(),
            "caminho": str(spec["arquivo"])}


# ------------------------------------------------------------- CLI
def cmd(args, cfg) -> None:
    """`betterme boot on|off|status`."""
    acao = getattr(args, "acao", "status")
    if acao == "on":
        r = on(cfg)
    elif acao == "off":
        r = off(cfg)
    elif acao == "status":
        r = status(cfg)
        print(f"🔘 boot ({r['so']}): "
              f"{'✔ registrado' if r['registrado'] else '✖ não registrado'}"
              f" · {r['caminho']}")
        return
    else:
        print(f"✖ ação desconhecida: {acao!r} (on|off|status)")
        raise SystemExit(1)
    print(("✔ " if r["ok"] else "✖ ") + r["msg"])
    if not r["ok"]:
        raise SystemExit(1)
