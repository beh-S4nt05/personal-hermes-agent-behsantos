#!/usr/bin/env python3
"""Servidor MCP de Agenda — Google Calendar, SOMENTE LEITURA (stdio).

Ferramentas expostas ao agente (mcp_agenda_*):
  agenda_hoje     — eventos de hoje
  agenda_listar   — próximos N dias (padrão 7)
  agenda_proximo  — próximos compromissos a partir de agora
  agenda_contas   — agendas configuradas (sem credenciais)

SOMENTE LEITURA POR CONSTRUÇÃO:
  * o escopo OAuth é 'calendar.readonly' (concedido pelo dono da conta);
  * este servidor só faz GET na API do Calendar — não existe código que
    crie, altere ou apague eventos;
  * as credenciais vêm de $HERMES_AGENDA_SECRETS (arquivo 600, fora do
    workspace), lidas DIRETO por este processo — nunca passam pelo modelo.

Stdlib pura (urllib/json) — zero dependências extras.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

SERVER_NAME = "agenda"
SERVER_VERSION = "1.0.0"
API_BASE = os.environ.get("HERMES_AGENDA_API") or \
    "https://www.googleapis.com/calendar/v3"
MAX_EVENTOS = 50

TOOLS = [
    {
        "name": "agenda_hoje",
        "description": ("Lista os eventos de HOJE na agenda (Google Calendar, "
                        "somente leitura)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "id da agenda (omitir = padrão)"},
            },
        },
    },
    {
        "name": "agenda_listar",
        "description": ("Lista os eventos dos próximos N dias (padrão 7). "
                        "Somente leitura."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dias": {"type": "number", "description": "quantos dias à frente (padrão 7)"},
                "limit": {"type": "number", "description": "máx. eventos (padrão 20)"},
                "account": {"type": "string"},
            },
        },
    },
    {
        "name": "agenda_proximo",
        "description": ("Próximos compromissos a partir de AGORA (padrão 3). "
                        "Somente leitura."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "number", "description": "quantos eventos (padrão 3)"},
                "account": {"type": "string"},
            },
        },
    },
    {
        "name": "agenda_contas",
        "description": "Lista as agendas configuradas (ids; sem credenciais).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ───────────────────────────── credenciais ─────────────────────────────

_ACC_CACHE: dict = {"mtime": None, "accs": None, "loaded": 0.0}


def _load_accounts() -> list[dict]:
    """Agendas do arquivo de segredos — cache por mtime (token vivo entre
    chamadas, sem regravar nada em disco)."""
    path = os.environ.get("HERMES_AGENDA_SECRETS") or \
        str(Path.home() / ".hermes" / "secrets" / "agenda.json")
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


def _pick(args: dict) -> dict:
    accs = _load_accounts()
    if not accs:
        raise RuntimeError("nenhuma agenda configurada — rode: hermes agenda oauth")
    want = str(args.get("account") or "").strip()
    if not want:
        return accs[0]
    for a in accs:
        if a.get("id") == want or a.get("user") == want:
            return a
    raise RuntimeError(f"agenda '{want}' não encontrada — use agenda_contas")


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


def _api_get(acc: dict, path: str, params: dict | None = None) -> dict:
    """GET autenticado — único verbo deste servidor (somente leitura)."""
    token = _ensure_token(acc)
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detalhe = exc.read().decode(errors="replace")[:160]
        except Exception:  # noqa: BLE001
            detalhe = str(exc)
        raise RuntimeError(f"Calendar API HTTP {exc.code}: {detalhe}") from exc


# ───────────────────────────── formatação ─────────────────────────────

def _fmt_event(ev: dict) -> str:
    s = ev.get("start") or {}
    e = ev.get("end") or {}
    try:
        if s.get("dateTime"):
            d1 = datetime.fromisoformat(s["dateTime"])
            d2 = datetime.fromisoformat(e["dateTime"]) if e.get("dateTime") else d1
            quando = d1.strftime("%d/%m %H:%M")
            quando += ("–" + d2.strftime("%H:%M") if d2.date() == d1.date()
                       else "–" + d2.strftime("%d/%m %H:%M"))
        elif s.get("date"):
            quando = date.fromisoformat(s["date"]).strftime("%d/%m") + " (dia inteiro)"
        else:
            quando = "(horário?)"
    except Exception:  # noqa: BLE001
        quando = "(horário?)"
    titulo = ev.get("summary") or "(sem título)"
    extra = []
    if ev.get("location"):
        extra.append("📍 " + str(ev["location"])[:60])
    if ev.get("hangoutLink"):
        extra.append("🎥 reunião online")
    n = len(ev.get("attendees") or [])
    if n:
        extra.append(f"{n} participante(s)")
    return f"📅 {quando} · {titulo}" + (" — " + " · ".join(extra) if extra else "")


def _eventos(acc: dict, params: dict) -> str:
    resp = _api_get(acc, "/calendars/primary/events", params)
    itens = [e for e in (resp.get("items") or [])
             if e.get("status") != "cancelled"]
    return itens


# ───────────────────────────── ferramentas ─────────────────────────────

def tool_hoje(args: dict) -> str:
    acc = _pick(args)
    agora = datetime.now().astimezone()
    hoje0 = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    itens = _eventos(acc, {
        "singleEvents": "true", "orderBy": "startTime", "maxResults": MAX_EVENTOS,
        "timeMin": hoje0.isoformat(),
        "timeMax": (hoje0 + timedelta(days=1)).isoformat()})
    if not itens:
        return f"🗓 hoje ({agora.strftime('%d/%m')}) — {acc['user']}: nenhum evento"
    return (f"🗓 hoje ({agora.strftime('%d/%m')}) — {acc['user']} "
            f"({len(itens)} evento(s)):\n" + "\n".join(_fmt_event(e) for e in itens))


def tool_listar(args: dict) -> str:
    acc = _pick(args)
    dias = max(1, min(int(args.get("dias") or 7), 31))
    limit = max(1, min(int(args.get("limit") or 20), MAX_EVENTOS))
    agora = datetime.now().astimezone()
    hoje0 = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    itens = _eventos(acc, {
        "singleEvents": "true", "orderBy": "startTime", "maxResults": limit,
        "timeMin": hoje0.isoformat(),
        "timeMax": (hoje0 + timedelta(days=dias)).isoformat()})
    if not itens:
        return f"🗓 próximos {dias} dia(s) — {acc['user']}: nenhum evento"
    return (f"🗓 próximos {dias} dia(s) — {acc['user']} ({len(itens)} evento(s)):\n"
            + "\n".join(_fmt_event(e) for e in itens))


def tool_proximo(args: dict) -> str:
    acc = _pick(args)
    limit = max(1, min(int(args.get("limit") or 3), 10))
    agora = datetime.now().astimezone()
    itens = _eventos(acc, {
        "singleEvents": "true", "orderBy": "startTime", "maxResults": limit,
        "timeMin": agora.isoformat()})
    if not itens:
        return f"🗓 nenhum compromisso futuro na agenda de {acc['user']}"
    return (f"🗓 a partir de agora ({agora.strftime('%d/%m %H:%M')}) — "
            f"{acc['user']}:\n" + "\n".join(_fmt_event(e) for e in itens))


def tool_contas(_args: dict) -> str:
    accs = _load_accounts()
    if not accs:
        return ("nenhuma agenda configurada — rode `hermes agenda oauth` no "
                "terminal e reinicie o server")
    linhas = [f"- {a.get('id')} → {a.get('user')} · 🔎 somente leitura "
              f"({a.get('oauth_scopes', 'calendar.readonly')})" for a in accs]
    return "Agendas disponíveis (use o id em 'account'):\n" + "\n".join(linhas)


def _call_tool(name: str, args: dict) -> str:
    if name == "agenda_hoje":
        return tool_hoje(args)
    if name == "agenda_listar":
        return tool_listar(args)
    if name == "agenda_proximo":
        return tool_proximo(args)
    if name == "agenda_contas":
        return tool_contas(args)
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
