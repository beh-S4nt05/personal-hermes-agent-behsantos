"""Doctor: checklist de saúde do ambiente — CLI (`betterme doctor`) e GUI.

Cada item: {id, name, ok, detail, fix} — `fix` é o comando/ação sugerida.
"""
from __future__ import annotations

import shutil
from .contratos import (CHECK_CEREBRO, CHECK_CLAUDE,
                          CHECK_DISPOSITIVO, CHECK_FLUXOS, CHECK_MODEL,
                          CHECK_OLLAMA, CHECK_SECURITY, CHECK_STT)


def run_checks(cfg) -> list[dict]:
    checks: list[dict] = []

    # 0) Dispositivo — em qualquer SO (v6.1.0): SO · arquitetura · RAM
    from . import plataforma
    disp = plataforma.dispositivo()
    ram = disp.get("ram_mb")
    if ram and ram >= 12000:
        reco = "hermes3:8b local (ou pool grátis)"
    elif ram and ram >= 6000:
        reco = "hermes3:3b local (o 8b pode faltar RAM)"
    elif ram:
        reco = "hermes3:3b c/ num_ctx 4096 — ou pool grátis (betterme provider set groq)"
    else:
        reco = "RAM não detectada"
    arm = disp.get("arquitetura", "")
    nota_arm = " · ARM64 ✔" if "arm" in arm.lower() or "aarch" in arm.lower() else ""
    checks.append({
        "id": CHECK_DISPOSITIVO, "name": "Dispositivo",
        "ok": True,
        "detail": f"{disp['so_label']} · {arm}{nota_arm} · "
                  f"RAM {ram if ram else '?'} MB · Python {disp['python']}"
                  f" — modelo recomendado: {reco}",
        "fix": "",
    })

    # 0.5) Cérebro (LLM): roteador v6.3.0 — chave guardada = USADA
    prov = str(getattr(cfg, "llm_provider", "local") or "local")
    auto = bool(getattr(cfg, "auto_provider", True))
    rapido = ""
    try:
        from .llm_providers import melhor_provedor
        rapido = melhor_provedor(cfg) or ""
    except Exception:  # noqa: BLE001
        pass
    if prov != "local":
        ok, detail = True, f"provedor externo FIXADO: {prov} (fallback local)"
        fix = ""
    elif rapido and auto:
        ok, detail = True, (f"ROTEADOR automático: {rapido} (chave "
                            "detectada → EM USO; fallback local na falha; "
                            "memória segue 100% local)")
        fix = ""
    elif rapido and not auto:
        ok, detail = False, (f"100% local a seu pedido (provider off) — "
                             f"há uma chave {rapido} guardada e o roteador "
                             "está desligado")
        fix = f"betterme provider set {rapido}   # religa: 3-10× mais rápido"
    else:
        ok, detail = True, "Ollama local (nenhuma chave externa guardada)"
        fix = ("betterme provider set groq   # opcional: chave grátis = "
               "roteador automático + velocidade")
    checks.append({
        "id": CHECK_CEREBRO, "name": "Cérebro (LLM)", "ok": ok,
        "detail": detail, "fix": fix,
    })

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
        "id": CHECK_OLLAMA, "name": "Servidor Ollama", "ok": ok, "detail": detail,
        "fix": __import__("betterme.plataforma", fromlist=["hint"]).hint("ollama_start"),
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
        "id": CHECK_MODEL, "name": "Modelo instalado", "ok": ok, "detail": detail,
        "fix": f"ollama pull {cfg.model}",
    })

    # 3) Ditado por voz (Whisper) disponível?
    try:
        import faster_whisper  # noqa: F401
        ok, detail = True, "faster-whisper pronto (ditado por voz OK)"
    except ImportError:
        ok, detail = False, "faster-whisper não instalado (voz desativada)"
    checks.append({
        "id": CHECK_STT, "name": "Ditado por voz", "ok": ok, "detail": detail,
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
                          timeout=20, check=False)
            m = _re.search(r"(\d+)\.(\d+)\.", out.stdout or "")
            if m and (int(m.group(1)), int(m.group(2))) >= (2, 1):
                ok, detail = True, f"CLI {m.group(0)[:-1]} (modo leve disponível)"
            elif m:
                v = f"{m.group(1)}.{m.group(2)}"
                detail = f"CLI {v} é antiga — modo leve indisponível"
                fix = "claude update"
            else:
                detail = "CLI presente mas sem versão legível"
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)[:120]
    checks.append({
        "id": CHECK_CLAUDE, "name": "Claude Code (2º agente)", "ok": ok,
        "detail": detail, "fix": fix, "optional": True,
    })

    # 4b) v6.3.2: n8n local (opcional) — interliga ⚙ Fluxos ↔ doctor
    try:
        from . import fluxos as _fluxos
        if _fluxos.rodando(cfg):
            _key = bool(_fluxos.ler_apikey(cfg))
            ok = True
            detail = (f"rodando (porta {_fluxos.PORTA}) · API key "
                      f"{'✔' if _key else '✖ (necessária p/ fluxos listar)'}")
            fix = ""
        elif _fluxos.instalado_leve(cfg):
            ok = False
            detail = "instalado, mas parado"
            fix = "betterme fluxos start"
        else:
            ok = False
            detail = "não instalado"
            fix = "betterme fluxos setup (ou python install.py --full)"
    except Exception as exc:  # noqa: BLE001
        ok, detail, fix = False, f"erro: {exc.__class__.__name__}", ""
    checks.append({
        "id": CHECK_FLUXOS, "name": "⚙ Fluxos (n8n)", "ok": ok,
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
        "id": CHECK_SECURITY, "name": "Segurança do painel", "ok": ok, "detail": detail,
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
        parts.append("⚠ opcional(is): " +
                     ", ".join(c["name"] for c in opts))
    return " · ".join(parts)
