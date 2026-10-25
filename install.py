#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🧩 Instalador universal do Betterme Agent — Windows | macOS | Linux.

Roda em QUALQUER dispositivo com Python 3.9+ (x86-64 ou ARM64: PC,
notebook, Mac, mini PC, Raspberry Pi…). Python puro — nada de bash.

O que faz:
  1. Confere o Python (>= 3.9) e o sistema operacional
  2. Cria o .venv do projeto
  3. Atualiza pip/setuptools (setuptools >= 64 = instalação editável)
  4. Instala o Betterme (pip install -e .) — comandos betterme + hermes
  5. Checa o Ollama e orienta a instalação POR SO se faltar
  6. Imprime os próximos passos

Uso:
    python3 install.py [--model hermes3:8b] [--skip-ollama-check]
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MIN_PY = (3, 9)

HINTS = {
    "ollama": {
        "linux": "curl -fsSL https://ollama.com/install.sh | sh",
        "macos": "brew install ollama  (ou baixe o app em ollama.com)",
        "windows": "baixe o OllamaSetup.exe em ollama.com "
                   "(ou winget install Ollama.Ollama)",
    },
}


def so() -> str:
    p = sys.platform
    if p.startswith("win"):
        return "windows"
    if p == "darwin":
        return "macos"
    return "linux"


def py_do_venv() -> Path:
    return (RAIZ / ".venv" / ("Scripts/python.exe" if so() == "windows"
                              else "bin/python"))


def rodar(cmd: list[str], **kw) -> int:
    print("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], **kw).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Instalador do Betterme Agent")
    ap.add_argument("--model", default="hermes3:8b",
                    help="modelo sugerido ao final (default hermes3:8b)")
    ap.add_argument("--skip-ollama-check", action="store_true",
                    help="não checar o Ollama ao final")
    ap.add_argument("--full", action="store_true",
                    help="carrega TUDO para iniciar plenamente: playwright "
                         "(WhatsApp), Ollama (instala se faltar), modelo, "
                         "n8n (fluxos) e doctor final")
    ap.add_argument("--skip-n8n", action="store_true",
                    help="(com --full) não instalar o n8n")
    ap.add_argument("--skip-playwright", action="store_true",
                    help="(com --full) não instalar playwright/chromium")
    args = ap.parse_args()

    print("🧩 Betterme Agent — instalador universal")
    if sys.version_info < MIN_PY:
        print(f"✖ Python {MIN_PY[0]}.{MIN_PY[1]}+ necessário "
              f"(atual: {platform.python_version()})")
        return 1
    sis = so()
    arq = platform.machine() or "?"
    print(f"  dispositivo: {sis} · {arq} · Python "
          f"{platform.python_version()}")

    # 1) venv
    py = py_do_venv()
    if not py.exists():
        print("  ✔ criando .venv …")
        venv.create(str(RAIZ / ".venv"), with_pip=True)
    if not py.exists():
        print("✖ não consegui criar o .venv — rode: python3 -m venv .venv")
        return 1

    # 2) ferramentas de build modernas (PEP 660 — lição do v6.0.2)
    print("  ✔ atualizando pip/setuptools …")
    rodar([py, "-m", "pip", "install", "-q", "--upgrade",
           "pip", "setuptools"])

    # 3) o Betterme em si
    print("  ✔ instalando o Betterme (editável) …")
    rc = rodar([py, "-m", "pip", "install", "-q", "-e", "."],
               cwd=str(RAIZ))
    if rc != 0:
        print("✖ falha no pip — rode manualmente: "
              f"{py} -m pip install -e .")
        return 1
    print("  ✔ comandos registrados: betterme (+ alias hermes)")

    # 4) Ollama (opcional — só orienta, nunca instala por conta própria)
    if not args.skip_ollama_check:
        if shutil.which("ollama"):
            print(f"  ✔ Ollama encontrado — modelo sugerido: "
                  f"ollama pull {args.model}")
        else:
            print("  ℹ Ollama não encontrado (o cérebro local). Instale:")
            print(f"     {HINTS['ollama'][sis]}")
            print("     (sem Ollama agora? Tudo bem — o modo demo "
                  "(BETTERME_MOCK=1) e o pool grátis funcionam)")

    # ── --full: carregar TUDO para iniciar plenamente ──────────────
    if args.full:
        print("\n📦 MODO COMPLETO — carregando tudo (pode demorar):")
        # (a) playwright (WhatsApp) + chromium
        if not args.skip_playwright:
            print("  ✔ playwright (canal WhatsApp) …")
            rodar([py, "-m", "pip", "install", "-q", "-e", ".[whatsapp]"])
            rodar([py, "-m", "playwright", "install", "chromium"])
        # (b) Ollama — instala se faltar (por SO, best-effort)
        if not args.skip_ollama_check:
            if shutil.which("ollama"):
                print("  ✔ Ollama já presente")
            elif sis == "linux":
                print("  ✔ instalando Ollama (script oficial — pode pedir sudo)…")
                rodar(["bash", "-c",
                       "curl -fsSL https://ollama.com/install.sh | sh"])
            elif sis == "macos" and shutil.which("brew"):
                print("  ✔ instalando Ollama via brew …")
                rodar(["brew", "install", "ollama"])
            elif sis == "windows" and shutil.which("winget"):
                print("  ✔ instalando Ollama via winget …")
                rodar(["winget", "install", "--id", "Ollama.Ollama", "-e",
                       "--accept-source-agreements",
                       "--accept-package-agreements"])
            else:
                print(f"  ℹ instale o Ollama manualmente: "
                      f"{HINTS['ollama'][sis]}")
        # (c) modelo local
        if shutil.which("ollama") and not args.skip_ollama_check:
            print(f"  ✔ baixando modelo {args.model} (GBs — paciência)…")
            rodar(["ollama", "pull", args.model])
        # (d) n8n (aba ⚙ Fluxos) — instala no data-dir e sobe
        if not args.skip_n8n:
            print("  ✔ n8n (fluxos) — instalando no data-dir …")
            r1 = rodar([py, "-m", "betterme", "fluxos", "setup"])
            if r1 == 0:
                rodar([py, "-m", "betterme", "fluxos", "start"])
            else:
                print("  ℹ n8n precisa do Node.js 20.19–24.x — "
                      "instale (ex.: winget install OpenJS.NodeJS.LTS / "
                      "brew install node) e rode: betterme fluxos setup")
        # (e) veredito final
        print("\n🩺 veredito do ambiente:")
        rodar([py, "-m", "betterme", "doctor"])

    # 5) próximos passos
    ativa = (r".venv\Scripts\activate" if sis == "windows"
             else "source .venv/bin/activate")
    print("\n🎉 pronto! Próximos passos:")
    print(f"    {ativa}")
    print("    betterme doctor     # checa dispositivo, Ollama e modelo")
    print("    betterme server     # GUI web em http://127.0.0.1:8080")
    print("    betterme chat       # chat no terminal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
