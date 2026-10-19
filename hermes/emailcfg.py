"""Configuração de contas de e-mail para o servidor MCP (hermes email).

Segurança das credenciais — projeto à prova de vazamento:
  * As senhas vivem em <data_dir>/secrets/email.json com permissão 600
    (diretório 700) — FORA do workspace do agente (o sandbox de arquivos
    já bloqueia leitura fora do workspace).
  * A denylist de comandos bloqueia `run_command` que tente acessar
    caminhos de secrets (cat/grep/less em secrets/...).
  * As credenciais NUNCA passam pelo modelo: o servidor MCP lê o arquivo
    direto; só o CONTEÚDO dos e-mails trafega pelas ferramentas.
  * Nada de credenciais em config.yaml, logs, auditoria ou histórico.
"""

from __future__ import annotations

import imaplib
import json
import os
import smtplib
import stat
import sys
from pathlib import Path

GMAIL = {
    "imap_host": "imap.gmail.com", "imap_port": 993, "imap_tls": "ssl",
    "smtp_host": "smtp.gmail.com", "smtp_port": 465, "smtp_tls": "ssl",
}


def secrets_path(cfg) -> Path:
    return cfg.data_dir / "secrets" / "email.json"


def load(cfg) -> dict:
    p = secrets_path(cfg)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("accounts"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"accounts": [], "default": None}


def save(cfg, data: dict) -> None:
    p = secrets_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:  # diretorio privado
        os.chmod(p.parent, 0o700)
    except OSError:
        pass
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _guess_hosts(user: str) -> list[dict]:
    """Palpites de servidores IMAP/SMTP pelo domínio do e-mail."""
    domain = user.rsplit("@", 1)[-1].lower() if "@" in user else ""
    if domain in ("gmail.com", "googlemail.com"):
        return [dict(GMAIL)]
    if not domain:
        return []
    out = []
    for prefix in ("imap.", "mail."):
        out.append({
            "imap_host": prefix + domain, "imap_port": 993, "imap_tls": "ssl",
            "smtp_host": ("smtp." if prefix == "imap." else prefix) + domain,
            "smtp_port": 587, "smtp_tls": "starttls",
        })
    return out


def _imap_login(acc: dict) -> tuple[bool, str]:
    """Tenta login IMAP; devolve (ok, detalhe)."""
    tls = acc.get("imap_tls", "ssl")
    try:
        if tls == "none":
            M = imaplib.IMAP4(acc["imap_host"], int(acc.get("imap_port", 143)), timeout=20)
        else:
            M = imaplib.IMAP4_SSL(acc["imap_host"], int(acc.get("imap_port", 993)), timeout=20)
        try:
            typ, _ = M.login(acc["user"], acc["password"])
            if typ != "OK":
                return False, "login recusado"
            try:
                M.select("INBOX", readonly=True)
            except Exception:  # pasta padrão ausente: login já validou
                pass
            return True, f"IMAP OK ({acc['imap_host']}:{acc.get('imap_port', 993)})"
        finally:
            try:
                M.logout()
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"


def _smtp_login(acc: dict) -> tuple[bool, str]:
    tls = acc.get("smtp_tls", "ssl")
    try:
        if tls == "ssl":
            S = smtplib.SMTP_SSL(acc["smtp_host"], int(acc.get("smtp_port", 465)), timeout=20)
        else:
            S = smtplib.SMTP(acc["smtp_host"], int(acc.get("smtp_port", 587)), timeout=20)
        try:
            if tls == "starttls":
                S.starttls()
            S.login(acc["user"], acc["password"])
            return True, f"SMTP OK ({acc['smtp_host']}:{acc.get('smtp_port')})"
        finally:
            try:
                S.quit()
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"


def probe_account(user: str, password: str) -> tuple[dict | None, str]:
    """Descobre (por tentativa) os servidores que aceitam o login."""
    last_err = ""
    for cand in _guess_hosts(user):
        ok, detail = _imap_login({**cand, "user": user, "password": password})
        if ok:
            # SMTP: se falhar, envio fica desativado — leitura já funciona
            sok, sdetail = _smtp_login({**cand, "user": user, "password": password})
            acc = {**cand, "user": user, "password": password, "smtp_ok": sok}
            return acc, detail + (" · " + sdetail if sok else
                                  f" · SMTP indisponível ({sdetail[:60]}) — leitura OK, envio desativado")
        last_err = detail
    return None, last_err or "não consegui adivinhar os servidores deste domínio"


def add_account(cfg, user: str, password: str, account_id: str | None = None) -> tuple[dict, str]:
    """Testa, salva (600) e registra a conta; devolve (conta, relatório)."""
    acc, report = probe_account(user, password)
    if acc is None:
        raise ValueError(report)
    acc["id"] = (account_id or user.split("@")[0].replace(".", "_") + "_" +
                 user.rsplit("@", 1)[-1].split(".")[0]).lower()[:24]
    data = load(cfg)
    data["accounts"] = [a for a in data["accounts"] if a.get("id") != acc["id"]] + [acc]
    if not data.get("default"):
        data["default"] = acc["id"]
    save(cfg, data)
    register_mcp(cfg)
    return acc, report


def register_mcp(cfg) -> None:
    """Garante que o servidor MCP 'email' está no config (com caminho do
    arquivo de segredos passado por env — nada de senha no config.yaml)."""
    script = Path(__file__).resolve().parent.parent / "mcp-servers" / "email_server.py"
    entry = {
        "name": "email",
        "command": sys.executable or "python3",
        "args": [str(script)],
        "env": {"HERMES_EMAIL_SECRETS": str(secrets_path(cfg))},
    }
    servers = [s for s in (cfg.mcp_servers or [])
               if not (isinstance(s, dict) and s.get("name") == "email")]
    servers.append(entry)
    cfg.update({"mcp_servers": servers})


def status(cfg) -> dict:
    data = load(cfg)
    return {
        "secrets_file": str(secrets_path(cfg)),
        "exists": secrets_path(cfg).exists(),
        "mode": oct(stat.S_IMODE(secrets_path(cfg).stat().st_mode))
                if secrets_path(cfg).exists() else None,
        "accounts": [{"id": a.get("id"), "user": a.get("user"),
                      "imap_host": a.get("imap_host"), "smtp_ok": a.get("smtp_ok", False)}
                     for a in data.get("accounts", [])],
        "default": data.get("default"),
        "mcp_registered": any(isinstance(s, dict) and s.get("name") == "email"
                              for s in (cfg.mcp_servers or [])),
    }


def setup_interactive(cfg) -> None:
    """`hermes email setup` — pergunta contas, testa, salva e registra."""
    import getpass

    print("\n📧 Configuração de e-mail do Hermes Agent")
    print("─" * 52)
    print("  As senhas ficam em:", secrets_path(cfg))
    print("  · arquivo com permissão 600, fora do workspace do agente")
    print("  · bloqueado na denylist de comandos (cat/grep em secrets)")
    print("  · nunca passam pelo modelo — só o conteúdo dos e-mails")
    print("─" * 52)
    while True:
        user = input("\n  e-mail (vazio para encerrar): ").strip()
        if not user:
            break
        password = getpass.getpass("  senha (app password p/ Gmail; não aparece): ").strip()
        if not password:
            print("  ✖ senha vazia — conta ignorada")
            continue
        print("  testando servidores…")
        try:
            acc, report = add_account(cfg, user, password)
        except ValueError as exc:
            print(f"  ✖ {exc}")
            continue
        print(f"  ✔ conta '{acc['id']}' salva — {report}")
    st = status(cfg)
    if st["accounts"]:
        print("\n  contas configuradas:")
        for a in st["accounts"]:
            marca = " (padrão)" if a["id"] == st["default"] else ""
            envio = "envio ✔" if a["smtp_ok"] else "só leitura"
            print(f"    · {a['user']} [{a['id']}]{marca} — {a['imap_host']} · {envio}")
        print(f"\n  servidor MCP 'email' registrado: {'sim' if st['mcp_registered'] else 'NÃO'}")
        print("  reinicie o `hermes server` e peça, por exemplo:")
        print('    "liste meus e-mails não lidos" ou "resuma as últimas 10 mensagens"')
    else:
        print("\n  nenhuma conta configurada.")
