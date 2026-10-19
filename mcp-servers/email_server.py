#!/usr/bin/env python3
"""Servidor MCP de e-mail (stdio) — IMAP para ler, SMTP para enviar.

Ferramentas expostas ao agente (nomes mapeados como mcp_email_*):
  email_list     — lista mensagens (pasta, limite, só não lidas)
  email_read     — lê uma mensagem pelo número (da listagem)
  email_search   — busca por remetente/assunto/texto (últimas 200)
  email_send     — envia e-mail (to, subject, body)
  email_accounts — contas configuradas (sem credenciais)

SEGURANÇA: as credenciais vêm de $HERMES_EMAIL_SECRETS (arquivo 600,
fora do workspace), lidas DIRETO por este processo — nunca passam pelo
modelo, nunca aparecem em respostas, logs ou auditoria. Só o conteúdo
dos e-mails trafega pelas ferramentas.

Stdlib pura (imaplib/smtplib/email) — zero dependências extras.
"""

from __future__ import annotations

import base64
import email
import email.header
import imaplib
import json
import os
import smtplib
import sys
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

SERVER_NAME = "email"
SERVER_VERSION = "1.0.0"
MAX_BODY_CHARS = 3500

TOOLS = [
    {
        "name": "email_list",
        "description": ("Lista e-mails de uma conta (padrão: INBOX, 10 mais "
                        "recentes). Use antes de email_read para obter os números."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "id da conta (omitir = padrão)"},
                "folder": {"type": "string", "description": "pasta (padrão INBOX)"},
                "limit": {"type": "number", "description": "máx. mensagens (padrão 10)"},
                "unread_only": {"type": "boolean", "description": "só não lidas"},
            },
        },
    },
    {
        "name": "email_read",
        "description": "Lê uma mensagem completa pelo número mostrado no email_list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "number": {"type": "number", "description": "número da mensagem na listagem"},
                "account": {"type": "string"},
                "folder": {"type": "string"},
            },
            "required": ["number"],
        },
    },
    {
        "name": "email_search",
        "description": "Busca e-mails por palavra (remetente, assunto ou corpo).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "texto a procurar"},
                "account": {"type": "string"},
                "folder": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "email_send",
        "description": "Envia um e-mail (texto simples) por uma conta configurada.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "destinatário (vários: separar por vírgula)"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "account": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "email_accounts",
        "description": "Lista as contas de e-mail configuradas (ids; sem credenciais).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ───────────────────────────── credenciais ─────────────────────────────

_ACC_CACHE: dict = {"mtime": None, "accs": None, "loaded": 0.0}


def _load_accounts() -> list[dict]:
    """Contas do arquivo de segredos — em CACHE por mtime (o access_token
    renovado fica vivo entre chamadas, sem regravar nada em disco)."""
    path = os.environ.get("HERMES_EMAIL_SECRETS") or \
        str(Path.home() / ".hermes" / "secrets" / "email.json")
    try:
        mtime = os.path.getmtime(path)
        if (_ACC_CACHE["accs"] is not None
                and _ACC_CACHE["mtime"] == mtime
                and time.time() - _ACC_CACHE["loaded"] < 120):
            return _ACC_CACHE["accs"]
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        accs = [a for a in (data.get("accounts") or [])
                if isinstance(a, dict) and a.get("user")]
        _ACC_CACHE.update(mtime=mtime, accs=accs, loaded=time.time())
        return accs
    except (OSError, ValueError):
        return []


def _pick(args: dict) -> dict | None:
    accs = _load_accounts()
    if not accs:
        raise RuntimeError("nenhuma conta configurada — rode: hermes email setup")
    want = str(args.get("account") or "").strip()
    if not want:
        # padrão: primeira conta
        return accs[0]
    for a in accs:
        if a.get("id") == want or a.get("user") == want:
            return a
    raise RuntimeError(f"conta '{want}' não encontrada — use email_accounts para ver os ids")


# ───────────────────────────── helpers IMAP ─────────────────────────────

def _xoauth2(user: str, token: str) -> bytes:
    return f"user={user}\x01auth=Bearer {token}\x01\x01".encode()


def _ensure_token(acc: dict) -> str:
    """Access token válido (renova com o refresh_token se expirado) — stdlib."""
    if acc.get("access_token") and acc.get("token_expires", 0) > time.time() + 60:
        return acc["access_token"]
    form = {"client_id": acc.get("client_id", ""),
            "grant_type": "refresh_token",
            "refresh_token": acc.get("refresh_token", ""),
            "scope": acc.get("oauth_scopes", "")}
    if acc.get("client_secret"):
        form["client_secret"] = acc["client_secret"]
    req = urllib.request.Request(
        acc["token_endpoint"], data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.loads(r.read().decode())
    if "access_token" not in tok:
        raise RuntimeError(f"token endpoint recusou: {str(tok)[:120]}")
    acc["access_token"] = tok["access_token"]
    acc["token_expires"] = time.time() + int(tok.get("expires_in", 3600)) - 120
    return acc["access_token"]


def _connect(acc: dict) -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    if acc.get("imap_tls", "ssl") == "none":
        M = imaplib.IMAP4(acc["imap_host"], int(acc.get("imap_port", 143)), timeout=30)
    else:
        M = imaplib.IMAP4_SSL(acc["imap_host"], int(acc.get("imap_port", 993)), timeout=30)
    if acc.get("auth") == "oauth":
        token = _ensure_token(acc)
        M.authenticate("XOAUTH2", lambda _c: _xoauth2(acc["user"], token))
    else:
        M.login(acc["user"], acc["password"])
    return M


def _decode_hdr(raw: str | None) -> str:
    if not raw:
        return ""
    out = []
    for part, enc in email.header.decode_header(raw):
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)


def _body_text(msg: email.message.Message) -> str:
    """Corpo em texto plano (prefere text/plain; degrada html)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    import re
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:  # noqa: BLE001
                    pass
        return "(mensagem sem texto)"
    try:
        payload = msg.get_payload(decode=True)
        if payload is None:
            return str(msg.get_payload()) or ""
        text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            import re
            text = re.sub(r"<[^>]+>", " ", text)
        return text
    except Exception:  # noqa: BLE001
        return "(corpo ilegível)"


def _summarize(msg: email.message.Message, num: int, unseen: bool) -> str:
    de = _decode_hdr(msg.get("From"))
    assunto = _decode_hdr(msg.get("Subject")) or "(sem assunto)"
    data = _decode_hdr(msg.get("Date"))
    corpo = " ".join(_body_text(msg).split())[:110]
    flag = " · ✉ não lida" if unseen else ""
    return f"#{num} [{data}] {de} — “{assunto}”{flag}\n     {corpo}"


def _fetch_numbers(M, folder: str, unread_only: bool, limit: int) -> tuple[list[str], set]:
    typ, _ = M.select(folder, readonly=True)
    if typ != "OK":
        raise RuntimeError(f"pasta '{folder}' não encontrada")
    crit = "(UNSEEN)" if unread_only else "ALL"
    typ, data = M.search(None, crit)
    nums = data[0].split() if (typ == "OK" and data and data[0]) else []
    # últimos N (números crescem com a chegada)
    tail = nums[-limit:] if limit else nums
    # flags p/ marcar não lidas
    unseen = set()
    if not unread_only:
        typ, data = M.search(None, "(UNSEEN)")
        if typ == "OK" and data and data[0]:
            unseen = set(data[0].split())
    return tail, unseen


def _fetch_msg(M, num: str) -> email.message.Message:
    typ, data = M.fetch(num, "(BODY.PEEK[])")
    if typ != "OK" or not data or not data[0]:
        raise RuntimeError(f"não consegui ler a mensagem {num.decode() if isinstance(num, bytes) else num}")
    raw = data[0][1]
    return email.message_from_bytes(raw)


# ───────────────────────────── ferramentas ─────────────────────────────

def tool_list(args: dict) -> str:
    acc = _pick(args)
    folder = str(args.get("folder") or "INBOX")
    limit = max(1, min(int(args.get("limit") or 10), 50))
    M = _connect(acc)
    try:
        nums, unseen = _fetch_numbers(M, folder, bool(args.get("unread_only")), limit)
        if not nums:
            return f"{folder} de {acc['user']}: nenhuma mensagem" + \
                   (" não lida" if args.get("unread_only") else "")
        linhas = []
        for n in reversed(nums):  # mais recente primeiro
            try:
                msg = _fetch_msg(M, n)
                linhas.append(_summarize(msg, int(n), n in unseen))
            except Exception as exc:  # noqa: BLE001
                linhas.append(f"#{int(n)} (erro ao ler: {exc})")
        return (f"📬 {folder} — {acc['user']} ({len(nums)} mensagens, "
                f"mostrando {len(linhas)} mais recentes):\n\n" + "\n".join(linhas))
    finally:
        try:
            M.logout()
        except Exception:
            pass


def tool_read(args: dict) -> str:
    acc = _pick(args)
    num = int(args.get("number") or 0)
    if num <= 0:
        raise RuntimeError("informe o número da mensagem (do email_list)")
    folder = str(args.get("folder") or "INBOX")
    M = _connect(acc)
    try:
        M.select(folder, readonly=True)
        msg = _fetch_msg(M, str(num).encode())
        corpo = _body_text(msg)[:MAX_BODY_CHARS]
        return (f"De: {_decode_hdr(msg.get('From'))}\n"
                f"Para: {_decode_hdr(msg.get('To'))}\n"
                f"Assunto: {_decode_hdr(msg.get('Subject'))}\n"
                f"Data: {_decode_hdr(msg.get('Date'))}\n"
                + "─" * 40 + "\n" + corpo)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def tool_search(args: dict) -> str:
    acc = _pick(args)
    q = str(args.get("query") or "").strip().lower()
    if not q:
        raise RuntimeError("informe o texto a procurar")
    folder = str(args.get("folder") or "INBOX")
    limit = max(1, min(int(args.get("limit") or 10), 30))
    M = _connect(acc)
    try:
        nums, unseen = _fetch_numbers(M, folder, False, 200)
        achados = []
        for n in reversed(nums):
            if len(achados) >= limit:
                break
            try:
                msg = _fetch_msg(M, n)
                haystack = " ".join([
                    _decode_hdr(msg.get("From")),
                    _decode_hdr(msg.get("Subject")),
                    _body_text(msg)]).lower()
                if q in haystack:
                    achados.append(_summarize(msg, int(n), n in unseen))
            except Exception:  # noqa: BLE001
                continue
        if not achados:
            return f"nada encontrado com “{q}” em {folder} de {acc['user']}"
        return (f"🔍 “{q}” em {folder} — {acc['user']} "
                f"({len(achados)} resultado(s)):\n\n" + "\n".join(achados))
    finally:
        try:
            M.logout()
        except Exception:
            pass


def tool_send(args: dict) -> str:
    acc = _pick(args)
    if not acc.get("smtp_ok", True):
        raise RuntimeError(f"a conta {acc.get('id')} está em modo somente leitura "
                           "(SMTP não validado no setup)")
    to = str(args.get("to") or "").strip()
    subject = str(args.get("subject") or "").strip()
    body = str(args.get("body") or "")
    if not to:
        raise RuntimeError("informe o destinatário")
    if not subject:
        raise RuntimeError("informe o assunto")
    msg = EmailMessage()
    msg["From"] = acc["user"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    tls = acc.get("smtp_tls", "ssl")
    if tls == "ssl":
        S = smtplib.SMTP_SSL(acc["smtp_host"], int(acc.get("smtp_port", 465)), timeout=30)
    else:
        S = smtplib.SMTP(acc["smtp_host"], int(acc.get("smtp_port", 587)), timeout=30)
    try:
        if tls == "starttls":
            S.starttls()
        if acc.get("auth") == "oauth":
            token = _ensure_token(acc)
            S.auth("XOAUTH2",
                   lambda _c=None: _xoauth2(acc["user"], token).decode())
        else:
            S.login(acc["user"], acc["password"])
        S.send_message(msg)
    finally:
        try:
            S.quit()
        except Exception:
            pass
    return (f"✔ e-mail enviado de {acc['user']} para {to}\n"
            f"  assunto: {subject}\n  {len(body)} caracteres de corpo · "
            f"{time.strftime('%Y-%m-%d %H:%M')}")


def tool_accounts(_args: dict) -> str:
    accs = _load_accounts()
    if not accs:
        return ("nenhuma conta configurada — rode `hermes email setup` no terminal "
                "e reinicie o server")
    linhas = [f"- {a.get('id')} → {a.get('user')} "
              f"[{'OAuth' if a.get('auth') == 'oauth' else 'senha'}] "
              f"({'leitura+envio' if a.get('smtp_ok', True) else 'somente leitura'})"
              for a in accs]
    return "Contas de e-mail disponíveis (use o id em 'account'):\n" + "\n".join(linhas)


def _call_tool(name: str, args: dict) -> str:
    if name == "email_list":
        return tool_list(args)
    if name == "email_read":
        return tool_read(args)
    if name == "email_search":
        return tool_search(args)
    if name == "email_send":
        return tool_send(args)
    if name == "email_accounts":
        return tool_accounts(args)
    raise ValueError(f"ferramenta desconhecida: {name}")


# ───────────────────────────── protocolo MCP ─────────────────────────────

def handle(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        text = _call_tool(str(params.get("name", "")), params.get("arguments") or {})
        return {"content": [{"type": "text", "text": text}], "isError": False}
    if method == "ping":
        return {}
    raise ValueError(f"método não suportado: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg:
            continue
        try:
            result = handle(str(msg.get("method", "")), msg.get("params") or {})
            resp = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        except Exception as exc:  # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": msg["id"],
                    "error": {"code": -32000,
                              "message": f"{exc.__class__.__name__}: {exc}"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
