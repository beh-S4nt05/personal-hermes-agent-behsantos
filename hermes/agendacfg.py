"""Configuração da Agenda (Google Calendar) — SOMENTE LEITURA (hermes agenda).

Por que somente leitura: o escopo OAuth pedido é ÚNICO —
    https://www.googleapis.com/auth/calendar.readonly
A API devolve esse direito de forma definitiva: ver eventos, horários,
locais e participantes. NÃO existe, em lugar nenhum deste projeto, uma
ferramenta que crie, altere, mova ou apague eventos — o servidor MCP só
faz GET na API do Calendar.

Credenciais (refresh_token) em <data_dir>/secrets/agenda.json (600, fora
do workspace), lidas DIRETO pelo servidor MCP — nunca passam pelo modelo,
nunca aparecem em logs, auditoria ou respostas.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from .emailcfg import OAUTH_PROVIDERS, oauth_device_flow, refresh_access_token

CAL_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
API_BASE = "https://www.googleapis.com/calendar/v3"


def secrets_path(cfg) -> Path:
    return cfg.data_dir / "secrets" / "agenda.json"


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
    try:
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


def _api_get(acc: dict, path: str, params: dict | None = None,
            api_base: str = "") -> dict:
    """GET autenticado na API do Calendar (único verbo usado — leitura)."""
    token = refresh_access_token(acc)
    url = (api_base or API_BASE) + path
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


def fmt_event(ev: dict) -> str:
    """Uma linha legível: 📅 18/10 14:00–15:00 · Título — 📍 Local · 3 participantes."""
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


def list_events(cfg, account: str | None = None, dias: int = 7,
                limit: int = 20, a_partir_de_agora: bool = False) -> str:
    """Lista eventos (somente leitura) de uma conta da agenda."""
    data = load(cfg)
    accs = data.get("accounts") or []
    if not accs:
        raise RuntimeError("nenhuma agenda configurada — rode: hermes agenda oauth")
    acc = accs[0]
    if account:
        for a in accs:
            if a.get("id") == account or a.get("user") == account:
                acc = a
                break
        else:
            raise RuntimeError(f"agenda '{account}' não encontrada — veja: hermes agenda status")
    params = {"singleEvents": "true", "orderBy": "startTime",
              "maxResults": max(1, min(int(limit), 50))}
    agora = datetime.now().astimezone()
    if a_partir_de_agora:
        params["timeMin"] = agora.isoformat()
    else:
        hoje0 = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        params["timeMin"] = hoje0.isoformat()
        params["timeMax"] = (hoje0 + timedelta(days=max(1, int(dias)))).isoformat()
    resp = _api_get(acc, "/calendars/primary/events", params)
    itens = [e for e in (resp.get("items") or [])
             if e.get("status") != "cancelled"]
    if not itens:
        return f"agenda de {acc.get('user')}: nenhum evento no período"
    cab = (f"🗓 eventos a partir de agora — {acc.get('user')} "
           f"({len(itens)}):" if a_partir_de_agora else
           f"🗓 próximos {dias} dia(s) — {acc.get('user')} ({len(itens)}):")
    return cab + "\n" + "\n".join(fmt_event(e) for e in itens)


def add_account(cfg, user: str, client_id: str, client_secret: str = "",
                print_fn=print) -> tuple[dict, str]:
    """Adiciona a agenda de uma conta Google via device code (2FA do
    provedor, sem senha) e valida o acesso somente leitura."""
    import time as _time
    tok = oauth_device_flow("google", client_id, client_secret, print_fn,
                            scopes=CAL_SCOPE)
    acc = {
        "id": (user.split("@")[0].replace(".", "_") + "_gcal").lower()[:24],
        "user": user, "provider": "google",
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": tok["refresh_token"],
        "oauth_scopes": CAL_SCOPE,
        "token_endpoint": OAUTH_PROVIDERS["google"]["token_endpoint"],
        "access_token": tok.get("access_token"),
        "token_expires": _time.time() + int(tok.get("expires_in", 3600)) - 120,
    }
    cal = _api_get(acc, "/calendars/primary")
    data = load(cfg)
    data["accounts"] = [a for a in data["accounts"] if a.get("id") != acc["id"]] + [acc]
    if not data.get("default"):
        data["default"] = acc["id"]
    save(cfg, data)
    register_mcp(cfg)
    return acc, (f"Agenda OK — “{cal.get('summary') or user}” ({user}) · "
                 "escopo SOMENTE LEITURA (calendar.readonly)")


def register_mcp(cfg) -> None:
    """Registra o servidor MCP 'agenda' (secrets via env — nada no config)."""
    script = Path(__file__).resolve().parent.parent / "mcp-servers" / "agenda_server.py"
    env = {"HERMES_AGENDA_SECRETS": str(secrets_path(cfg))}
    if os.environ.get("HERMES_AGENDA_API"):  # teste/diagnóstico: API falsa
        env["HERMES_AGENDA_API"] = os.environ["HERMES_AGENDA_API"]
    entry = {
        "name": "agenda",
        "command": sys.executable or "python3",
        "args": [str(script)],
        "env": env,
    }
    servers = [s for s in (cfg.mcp_servers or [])
               if not (isinstance(s, dict) and s.get("name") == "agenda")]
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
                      "provider": a.get("provider", "google"),
                      "scope": a.get("oauth_scopes", CAL_SCOPE)}
                     for a in data.get("accounts", [])],
        "default": data.get("default"),
        "mcp_registered": any(isinstance(s, dict) and s.get("name") == "agenda"
                              for s in (cfg.mcp_servers or [])),
    }


def setup_interactive(cfg) -> None:
    """`hermes agenda oauth` — assistente device code (uma vez por conta)."""
    import getpass

    print("\n🗓 Agenda Google — acesso SOMENTE LEITURA (visualizar eventos)")
    print("─" * 56)
    print("  O que o agente ganha: listar/ler seus eventos (hoje, próximos")
    print("  dias, próximo compromisso). O que ele NUNCA faz: criar, mover")
    print("  ou apagar — o escopo OAuth é 'calendar.readonly' e não existe")
    print("  ferramenta de escrita no servidor.")
    print("  O refresh_token fica em:", secrets_path(cfg), "(600, fora do workspace)")
    print("─" * 56)
    print("  ⚠ Requer um client_id Google (uma vez; o MESMO do e-mail serve):")
    print("    console.cloud.google.com → APIs e serviços → Credenciais →")
    print("    'Criar credenciais' → 'ID do cliente OAuth' → tipo")
    print("    'App para TV e dispositivos de entrada limitada'.")
    while True:
        user = input("\n  e-mail da conta Google (vazio encerra): ").strip()
        if not user:
            break
        client_id = input("  client_id: ").strip()
        client_secret = getpass.getpass("  client_secret (não aparece): ").strip()
        if not (user and client_id and client_secret):
            print("  ✖ dados incompletos")
            continue
        try:
            acc, report = add_account(cfg, user, client_id, client_secret)
        except (ValueError, TimeoutError, RuntimeError) as exc:
            print(f"  ✖ {exc}")
            continue
        print(f"  ✔ agenda '{acc['id']}' salva — {report}")
    st = status(cfg)
    if st["accounts"]:
        print("\n  agendas configuradas:")
        for a in st["accounts"]:
            marca = " (padrão)" if a["id"] == st["default"] else ""
            print(f"    · {a['user']} [{a['id']}]{marca} — {a['scope']}")
        print(f"\n  servidor MCP 'agenda' registrado: {'sim' if st['mcp_registered'] else 'NÃO'}")
        print("  reinicie o `hermes server` e peça, por exemplo:")
        print('    "o que tenho na agenda hoje?" ou "qual meu próximo compromisso?"')
    else:
        print("\n  nenhuma agenda configurada.")
