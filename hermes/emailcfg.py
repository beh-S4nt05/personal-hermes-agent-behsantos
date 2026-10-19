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

import base64
import imaplib
import json
import os
import smtplib
import stat
import sys
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ── OAuth2 (XOAUTH2) — provedores que bloqueiam senha direta ──
# Microsoft 365/Outlook não aceitam mais "basic auth" em IMAP/SMTP: só OAuth2.
# O fluxo é "device code": o Hermes mostra um código, você entra em
# microsoft.com/link, autentica com 2FA NORMAL e autoriza. Sem segredos no
# terminal. Google também suporta (para quem prefere a app password, o
# setup normal com senha de app continua funcionando).
OAUTH_PROVIDERS = {
    "microsoft": {
        "device_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode",
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": "https://outlook.office365.com/IMAP.AccessAsUser.All "
                  "https://outlook.office365.com/SMTP.Send offline_access",
        "imap_host": "outlook.office365.com", "imap_port": 993, "imap_tls": "ssl",
        "smtp_host": "smtp.office365.com", "smtp_port": 587, "smtp_tls": "starttls",
    },
    "google": {
        "device_endpoint": "https://oauth2.googleapis.com/device/code",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "scopes": "https://mail.google.com/",
        "imap_host": "imap.gmail.com", "imap_port": 993, "imap_tls": "ssl",
        "smtp_host": "smtp.gmail.com", "smtp_port": 465, "smtp_tls": "ssl",
    },
}

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


def xoauth2_string(user: str, token: str) -> bytes:
    """String SASL XOAUTH2 (padrão de OAuth2 para IMAP/SMTP)."""
    return f"user={user}\x01auth=Bearer {token}\x01\x01".encode()


def refresh_access_token(acc: dict) -> str:
    """Access token válido — renova com o refresh_token quando expira."""
    if acc.get("access_token") and acc.get("token_expires", 0) > _time.time() + 60:
        return acc["access_token"]
    form = {"client_id": acc.get("client_id", ""),
            "grant_type": "refresh_token",
            "refresh_token": acc.get("refresh_token", ""),
            "scope": acc.get("oauth_scopes", "")}
    if acc.get("client_secret"):
        form["client_secret"] = acc["client_secret"]
    req = urllib.request.Request(
        acc["token_endpoint"],
        data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.loads(r.read().decode())
    if "access_token" not in tok:
        raise RuntimeError(f"token endpoint recusou: {str(tok)[:120]}")
    acc["access_token"] = tok["access_token"]
    acc["token_expires"] = _time.time() + int(tok.get("expires_in", 3600)) - 120
    return acc["access_token"]


def auth_hint(user: str, error: str) -> str:
    """Diagnóstico amigável: por que o login caiu e o que fazer."""
    e = (error or "").lower()
    dom = user.rsplit("@", 1)[-1].lower() if "@" in user else ""
    if ("application-specific password" in e or "senha de aplicativo" in e
            or ("web browser" in e and "gmail" in e)
            or "please log in via your web browser" in e):
        return ("Gmail: a senha normal NÃO serve para IMAP. Ative a verificação "
                "em 2 etapas e crie uma SENHA DE APLICATIVO (16 caracteres) em "
                "myaccount.google.com/apppasswords — use ELA no setup.")
    if ("authenticationfailed" in e or "authenticate failed" in e
            or "auth failed" in e) and any(d in dom for d in
            ("outlook.", "hotmail.", "live.", "msn.", "office365", "microsoft")):
        return ("Contas Microsoft (Outlook/Hotmail/Office 365) não aceitam mais "
                "senha direta em IMAP — rode: hermes email oauth")
    if "imap" in e and "disabled" in e:
        return "IMAP desabilitado para esta conta (Gmail: ative IMAP nas configurações de e-mail)"
    return ""


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
            if acc.get("auth") == "oauth":
                token = refresh_access_token(acc)
                M.authenticate("XOAUTH2",
                               lambda _c: xoauth2_string(acc["user"], token))
            else:
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
            if acc.get("auth") == "oauth":
                token = refresh_access_token(acc)
                S.auth("XOAUTH2",
                       lambda _c=None: xoauth2_string(acc["user"], token).decode())
            else:
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


def add_account(cfg, user: str, password: str, account_id: str | None = None,
                readonly: bool = True) -> tuple[dict, str]:
    """Testa, salva (600) e registra a conta; devolve (conta, relatório).

    readonly=True (PADRÃO): a conta fica em modo SOMENTE LEITURA — o agente
    lista/lê/busca e-mails, mas NÃO envia (v3.1.3: por padrão o envio fica
    desligado até o operador liberar com `hermes email modo <conta> envio`)."""
    acc, report = probe_account(user, password)
    if acc is None:
        hint = auth_hint(user, last_err if (last_err := report) else "")
        raise ValueError((hint + "\nDetalhe técnico: " if hint else "Falha: ") + report)
    acc["id"] = (account_id or user.split("@")[0].replace(".", "_") + "_" +
                 user.rsplit("@", 1)[-1].split(".")[0]).lower()[:24]
    acc["readonly"] = bool(readonly)
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


def oauth_device_flow(provider: str, client_id: str, client_secret: str = "",
                      print_fn=print, scopes: str = "") -> dict:
    """Fluxo OAuth 'device code' (padrão usado por TVs/CLIs): mostramos um
    código, você abre o link, entra com o 2FA NORMAL do provedor e autoriza.
    Nada de senha no terminal."""
    p = OAUTH_PROVIDERS[provider]
    form = {"client_id": client_id, "scope": scopes or p["scopes"]}
    if client_secret:
        form["client_secret"] = client_secret
    req = urllib.request.Request(
        p["device_endpoint"], data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode())
    url = d.get("verification_uri") or d.get("verification_url") or ""
    print_fn("\n🔐 Autorização do provedor — faça no SEU navegador:")
    print_fn(f"   1. abra:  {url}")
    print_fn(f"   2. código: {d.get('user_code', '?')}  (válido por "
             f"{int(d.get('expires_in', 900)) // 60} min)")
    print_fn("   3. entre com sua conta + 2FA e autorize o acesso\n")
    interval = max(2, int(d.get("interval", 5)))
    deadline = _time.time() + int(d.get("expires_in", 900))
    while _time.time() < deadline:
        _time.sleep(interval)
        body = {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id, "device_code": d["device_code"]}
        if client_secret:
            body["client_secret"] = client_secret
        try:
            req = urllib.request.Request(
                p["token_endpoint"],
                data=urllib.parse.urlencode(body).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=20) as r:
                tok = json.loads(r.read().decode())
            if "refresh_token" not in tok:
                raise RuntimeError(f"provedor não devolveu refresh_token: {str(tok)[:120]}")
            return tok
        except urllib.error.HTTPError as exc:
            try:
                err = json.loads(exc.read().decode()).get("error", "")
            except Exception:  # noqa: BLE001
                err = ""
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 2
                continue
            if err in ("access_denied", "expired_token"):
                raise RuntimeError(f"autorização {err} — comece de novo") from exc
            raise RuntimeError(f"OAuth falhou: HTTP {exc.code} {err}") from exc
    raise TimeoutError("tempo de autorização esgotado — comece de novo")


def add_oauth_account(cfg, user: str, provider: str, client_id: str,
                      client_secret: str = "", print_fn=print,
                      readonly: bool = True) -> tuple[dict, str]:
    """Cria conta via OAuth (device code), valida IMAP/SMTP e salva."""
    p = OAUTH_PROVIDERS[provider]
    tok = oauth_device_flow(provider, client_id, client_secret, print_fn)
    acc = {
        "id": (user.split("@")[0].replace(".", "_") + "_" +
               user.rsplit("@", 1)[-1].split(".")[0]).lower()[:24],
        "user": user, "auth": "oauth", "provider": provider,
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": tok["refresh_token"],
        "oauth_scopes": p["scopes"],
        "token_endpoint": p["token_endpoint"],
        "imap_host": p["imap_host"], "imap_port": p["imap_port"],
        "imap_tls": p["imap_tls"],
        "smtp_host": p["smtp_host"], "smtp_port": p["smtp_port"],
        "smtp_tls": p["smtp_tls"],
        "smtp_ok": False, "readonly": bool(readonly),
    }
    ok, detail = _imap_login(acc)
    if not ok:
        raise ValueError(f"IMAP recusou após OAuth: {detail}")
    sok, sdetail = _smtp_login(acc)
    acc["smtp_ok"] = sok
    data = load(cfg)
    data["accounts"] = [a for a in data["accounts"] if a.get("id") != acc["id"]] + [acc]
    if not data.get("default"):
        data["default"] = acc["id"]
    save(cfg, data)
    register_mcp(cfg)
    report = (f"IMAP OAuth OK ({detail})" +
              (f" · SMTP OAuth OK ({sdetail})" if sok else
               f" · SMTP indisponível ({sdetail[:60]}) — leitura OK, envio desativado"))
    return acc, report


def set_modo(cfg, conta: str, envio: bool) -> dict:
    """Alterna o modo da conta: envio=True libera ENVIO (e exige SMTP válido);
    envio=False volta para SOMENTE LEITURA (visualização)."""
    data = load(cfg)
    for a in data.get("accounts", []):
        if a.get("id") == conta or a.get("user") == conta:
            a["readonly"] = not bool(envio)
            save(cfg, data)
            return a
    raise ValueError(f"conta '{conta}' não encontrada — veja: hermes email status")


def status(cfg) -> dict:
    data = load(cfg)
    return {
        "secrets_file": str(secrets_path(cfg)),
        "exists": secrets_path(cfg).exists(),
        "mode": oct(stat.S_IMODE(secrets_path(cfg).stat().st_mode))
                if secrets_path(cfg).exists() else None,
        "accounts": [{"id": a.get("id"), "user": a.get("user"),
                      "auth": a.get("auth", "password"),
                      "imap_host": a.get("imap_host"), "smtp_ok": a.get("smtp_ok", False),
                      "readonly": a.get("readonly", True)}
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
    print("  PROVEDORES: Gmail → senha de APP (2FA ativo). Microsoft/Outlook →")
    print("  opção 'o' (OAuth, sem senha). Yahoo/iCloud → senha de app. Outros → senha.")
    while True:
        first = input("\n  e-mail (vazio encerra · 'o' = OAuth Microsoft/Google): ").strip()
        if not first:
            break
        if first.lower() == "o":
            _oauth_wizard(cfg)
            continue
        user = first
        if user.rsplit("@", 1)[-1].lower().endswith(("gmail.com", "googlemail.com")):
            print("  ℹ Gmail: use a SENHA DE APLICATIVO (16 caracteres), não a normal —")
            print("    crie em myaccount.google.com/apppasswords (exige 2FA ativo)")
        password = getpass.getpass("  senha (não aparece): ").strip()
        if not password:
            print("  ✖ senha vazia — conta ignorada")
            continue
        envio = input("  permitir ENVIO por esta conta? (s/N): ").strip().lower() == "s"
        print("  testando servidores…")
        try:
            acc, report = add_account(cfg, user, password, readonly=not envio)
        except ValueError as exc:
            print(f"  ✖ {exc}")
            continue
        print(f"  ✔ conta '{acc['id']}' salva — {report}")
    st = status(cfg)
    if st["accounts"]:
        print("\n  contas configuradas:")
        for a in st["accounts"]:
            marca = " (padrão)" if a["id"] == st["default"] else ""
            envio = ("🔎 somente leitura" if a.get("readonly", True)
                     else ("✉ leitura+envio" if a.get("smtp_ok") else "🔎 leitura (SMTP não validado)"))
            tipo = "OAuth" if a.get("auth") == "oauth" else "senha"
            print(f"    · {a['user']} [{a['id']}]{marca} — {a['imap_host']} · {tipo} · {envio}")
        print("  para liberar/bloquear envio: hermes email modo <conta> envio|leitura")
        print(f"\n  servidor MCP 'email' registrado: {'sim' if st['mcp_registered'] else 'NÃO'}")
        print("  reinicie o `hermes server` e peça, por exemplo:")
        print('    "liste meus e-mails não lidos" ou "resuma as últimas 10 mensagens"')
    else:
        print("\n  nenhuma conta configurada.")


def _oauth_wizard(cfg) -> None:
    """Assistente OAuth dentro do `hermes email setup` (opção 'o')."""
    import getpass

    print("\n  🔐 OAuth (Microsoft 365/Outlook ou Google)")
    print("  Microsoft/Outlook/hotmail: a senha direta foi DESATIVADA pela")
    print("  Microsoft — OAuth é o único caminho. Você vai autorizar no")
    print("  navegador com seu 2FA normal; nada de senha aqui.")
    print("  ⚠ Requer um client_id de aplicativo (uma vez):")
    print("    Microsoft: portal.azure.com → 'Registros de aplicativo' → novo")
    print("      app → conta pessoal/da instituição → 'Cliente público' e")
    print("      permita fluxos de dispositivo. Escopos IMAP/SMTP.Send.")
    print("    Google: console.cloud.google.com → credenciais OAuth →")
    print("      'App para TV e dispositivos de entrada limitada'.")
    prov = input("\n  provedor (microsoft/google): ").strip().lower()
    if prov not in OAUTH_PROVIDERS:
        print("  ✖ provedor inválido")
        return
    user = input("  e-mail da conta: ").strip()
    client_id = input("  client_id do aplicativo: ").strip()
    client_secret = ""
    if prov == "google":
        client_secret = getpass.getpass("  client_secret (google exige): ").strip()
    if not user or not client_id:
        print("  ✖ dados incompletos")
        return
    envio = input("  permitir ENVIO por esta conta? (s/N): ").strip().lower() == "s"
    try:
        acc, report = add_oauth_account(cfg, user, prov, client_id, client_secret,
                                        readonly=not envio)
    except (ValueError, TimeoutError, RuntimeError) as exc:
        print(f"  ✖ {exc}")
        return
    print(f"  ✔ conta '{acc['id']}' salva — {report}")
