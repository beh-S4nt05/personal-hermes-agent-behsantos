"""Doctor: checklist de saúde do ambiente — CLI (`hermes doctor`) e GUI.

Cada item: {id, name, ok, detail, fix} — `fix` é o comando/ação sugerida.
"""
from __future__ import annotations

import shutil


def run_checks(cfg) -> list[dict]:
    checks: list[dict] = []

    # 1) Ollama acessível?
    ok, detail = False, "servidor não responde"
    try:
        from .ollama_client import get_client
        client = get_client(cfg)
        ok = bool(client.is_running())
        if ok:
            detail = f"respondendo em {cfg.ollama_url}"
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)[:120]
    checks.append({
        "id": "ollama", "name": "Servidor Ollama", "ok": ok, "detail": detail,
        "fix": "systemctl start ollama  (ou ative «ligar automaticamente» na aba Ollama)",
    })

    # 2) Modelo configurado está instalado?
    ok, detail = False, "sem conexão com o Ollama"
    if checks[0]["ok"]:
        try:
            models = get_client(cfg).list_models()
            ok = cfg.model in models
            detail = (f"modelo atual: {cfg.model}" if ok else
                      f"modelo '{cfg.model}' NÃO instalado (instalados: "
                      f"{', '.join(models[:6]) or 'nenhum'})")
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)[:120]
    checks.append({
        "id": "model", "name": "Modelo instalado", "ok": ok, "detail": detail,
        "fix": f"ollama pull {cfg.model}",
    })

    # 3) Ditado por voz (Whisper) disponível?
    try:
        import faster_whisper  # noqa: F401
        ok, detail = True, "faster-whisper pronto (ditado por voz OK)"
    except ImportError:
        ok, detail = False, "faster-whisper não instalado (voz desativada)"
    checks.append({
        "id": "stt", "name": "Ditado por voz", "ok": ok, "detail": detail,
        "fix": './.venv/bin/pip install faster-whisper "av<19"',
        "optional": True,
    })

    # 4) CLI do Claude Code (2º agente) — versão com modo leve?
    exe = shutil.which("claude")
    ok, detail = False, "CLI claude não encontrada (agente 🔌 indisponível)"
    fix = "curl -fsSL https://claude.ai/install.sh | bash"
    if exe:
        import re as _re
        import subprocess as _sp
        try:
            out = _sp.run([exe, "--version"], capture_output=True, text=True,
                          timeout=20)
            m = _re.search(r"(\d+)\.(\d+)\.", out.stdout or "")
            if m and (int(m.group(1)), int(m.group(2))) >= (2, 1):
                ok, detail = True, f"CLI {m.group(0)[:-1]} (modo leve disponível)"
            elif m:
                v = f"{m.group(1)}.{m.group(2)}"
                detail = f"CLI {v} é antiga — modo leve indisponível"
                fix = "claude update"
            else:
                detail = f"CLI presente mas sem versão legível"
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)[:120]
    checks.append({
        "id": "claude", "name": "Claude Code (2º agente)", "ok": ok,
        "detail": detail, "fix": fix, "optional": True,
    })

    # 5) Segurança: exposto na rede sem token?
    host = str(getattr(cfg, "host", "127.0.0.1"))
    exposed = host not in ("127.0.0.1", "localhost", "::1")
    has_token = bool((getattr(cfg, "auth_token", "") or "").strip())
    ok = (not exposed) or has_token
    detail = ("localhost (ok)" if not exposed else
              ("exposto com token (ok)" if has_token else "EXPOSTO SEM TOKEN"))
    checks.append({
        "id": "security", "name": "Segurança do painel", "ok": ok, "detail": detail,
        "fix": "defina um token em Ajustes (ou inicie com --token)",
    })

    return checks


def summary(checks: list[dict]) -> str:
    problems = [c for c in checks if not c["ok"] and not c.get("optional")]
    opts = [c for c in checks if not c["ok"] and c.get("optional")]
    if not problems and not opts:
        return f"✔ todos os {len(checks)} checks passaram"
    parts = []
    if problems:
        parts.append(f"✖ {len(problems)} problema(s): " +
                     ", ".join(c["name"] for c in problems))
    if opts:
        parts.append(f"⚠ opcional(is): " +
                     ", ".join(c["name"] for c in opts))
    return " · ".join(parts)
