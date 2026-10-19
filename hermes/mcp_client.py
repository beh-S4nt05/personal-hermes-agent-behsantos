"""Cliente MCP (Model Context Protocol) para o Hermes Agent.

Conecta o agente a servidores MCP externos (Figma, GitHub, bancos de dados…).
As ferramentas de cada servidor aparecem para o modelo como tools normais,
prefixadas: mcp_<servidor>_<ferramenta> (ex.: mcp_figma_create_design).

Transportes suportados:
- stdio: servidor lançado como processo local (ex.: npx figma-developer-mcp)
- http:  servidor Streamable HTTP (ex.: Figma Dev Mode em 127.0.0.1:3845/mcp)

Configuração (config.yaml):
  mcp_servers:
    - name: figma
      command: npx
      args: ["-y", "figma-developer-mcp", "--figma-api-key=SUA-CHAVE", "--stdio"]
    - name: figma-devmode
      url: http://127.0.0.1:3845/mcp
"""

from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import threading
from collections import deque
from pathlib import Path

import requests

PROTOCOL_VERSION = "2024-11-05"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MCPError(Exception):
    pass


def map_tool_name(server_name: str, tool_name: str) -> str:
    """figma-demo + figma_create_design -> mcp_figma_demo_figma_create_design"""
    raw = f"{server_name}_{tool_name}"
    return "mcp_" + re.sub(r"[^a-z0-9_]", "_", raw.lower())


def _content_to_text(result: dict) -> str:
    parts = []
    for c in result.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(str(c.get("text", "")))
    return "\n".join(p for p in parts if p)


class BaseMCPServer:
    """Handshake JSON-RPC 2.0: initialize -> tools/list -> tools/call."""

    def __init__(self, name: str, timeout: float = 60):
        self.name = name
        self.timeout = timeout
        self.started = False
        self._id = 0

    # ------------------------------------------------- interface transporte
    def _rpc(self, method: str, params: dict | None, timeout: float) -> dict:
        raise NotImplementedError

    def _notify(self, obj: dict) -> None:
        pass

    def start(self) -> dict:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hermes-agent", "version": "1.0.0"},
            },
            self.timeout,
        )
        self._notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.started = True
        return result

    def stop(self) -> None:
        self.started = False

    def alive(self) -> bool:
        return self.started

    # ----------------------------------------------------------- operações
    def list_tools(self) -> list[dict]:
        result = self._rpc("tools/list", {}, self.timeout)
        return result.get("tools") or []

    def call_tool(self, tool: str, arguments: dict) -> str:
        result = self._rpc(
            "tools/call", {"name": tool, "arguments": arguments or {}}, self.timeout * 2
        )
        text = _content_to_text(result)
        if result.get("isError"):
            raise MCPError(f"{self.name}.{tool}: {text or 'erro na ferramenta'}")
        return text or "(sem saída)"


# ------------------------------------------------------------------- stdio

class StdioServer(BaseMCPServer):
    """Servidor MCP como processo local, JSON-RPC por linhas no stdin/stdout."""

    def __init__(self, name, command, args=None, env=None, cwd=None, timeout=60):
        super().__init__(name, timeout)
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd or str(PROJECT_ROOT)
        self.proc: subprocess.Popen | None = None
        self.stderr_tail: deque[str] = deque(maxlen=6)
        self._lock = threading.Lock()
        self._responses: dict[int, dict] = {}
        self._events: dict[int, threading.Event] = {}

    def start(self) -> dict:
        if self.proc and self.proc.poll() is None and self.started:
            return {}
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in self.env.items()})
        try:
            self.proc = subprocess.Popen(
                [self.command, *self.args],
                cwd=self.cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise MCPError(
                f"comando não encontrado para o servidor MCP '{self.name}': "
                f"{self.command} ({exc})"
            ) from exc
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            return super().start()
        except MCPError:
            self.stop()
            raise

    def _read_stdout(self) -> None:
        proc = self.proc
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = msg.get("id")
                if rid is not None and ("result" in msg or "error" in msg):
                    with self._lock:
                        self._responses[rid] = msg
                        ev = self._events.get(rid)
                    if ev:
                        ev.set()
        except Exception:
            pass

    def _read_stderr(self) -> None:
        proc = self.proc
        if not proc or not proc.stderr:
            return
        try:
            for line in proc.stderr:
                self.stderr_tail.append(line.rstrip()[:300])
        except Exception:
            pass

    def _rpc(self, method, params, timeout):
        proc = self.proc
        if not proc or proc.poll() is not None or not proc.stdin:
            raise MCPError(f"servidor MCP '{self.name}' não está ativo")
        self._id += 1
        rid = self._id
        ev = threading.Event()
        with self._lock:
            self._events[rid] = ev
            self._responses.pop(rid, None)
        payload = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        try:
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            if not ev.wait(timeout):
                tail = " | ".join(list(self.stderr_tail)[-3:])
                raise MCPError(
                    f"timeout ({timeout:g}s) aguardando o servidor MCP '{self.name}'"
                    + (f" — stderr: {tail}" if tail else "")
                )
            with self._lock:
                resp = self._responses.pop(rid, {})
        finally:
            with self._lock:
                self._events.pop(rid, None)
        if "error" in resp:
            err = resp["error"] or {}
            raise MCPError(f"{self.name}: {err.get('message') or err}")
        return resp.get("result") or {}

    def _notify(self, obj) -> None:
        proc = self.proc
        try:
            if proc and proc.stdin and proc.poll() is None:
                proc.stdin.write(json.dumps(obj) + "\n")
                proc.stdin.flush()
        except OSError:
            pass

    def alive(self) -> bool:
        return bool(self.started and self.proc and self.proc.poll() is None)

    def stop(self) -> None:
        self.started = False
        proc, self.proc = self.proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(3)
            except subprocess.TimeoutExpired:
                proc.kill()


# -------------------------------------------------------------------- http

class HTTPServer(BaseMCPServer):
    """Servidor MCP via Streamable HTTP (POST JSON-RPC; resposta JSON ou SSE)."""

    def __init__(self, name, url, headers=None, timeout=60):
        super().__init__(name, timeout)
        self.url = url
        self.headers = dict(headers or {})
        self.session_id: str | None = None

    def start(self) -> dict:
        result = super().start()
        self.started = True
        return result

    def _post(self, obj: dict, timeout: float) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        r = requests.post(self.url, json=obj, headers=headers, timeout=timeout)
        sid = r.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if r.status_code >= 400:
            raise MCPError(f"{self.name}: HTTP {r.status_code}: {r.text[:200]}")
        return self._parse(r)

    @staticmethod
    def _parse(r) -> dict:
        ctype = r.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            data = None
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    data = line[5:].strip()
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return {}
            return {}
        try:
            return r.json()
        except ValueError:
            return {}

    def _rpc(self, method, params, timeout):
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        resp = self._post(payload, timeout)
        if "error" in resp:
            err = resp["error"] or {}
            raise MCPError(f"{self.name}: {err.get('message') or err}")
        return resp.get("result") or {}

    def _notify(self, obj) -> None:
        try:
            self._post(obj, self.timeout)
        except MCPError:
            pass

    def alive(self) -> bool:
        return self.started and self.session_id is not None

    def stop(self) -> None:
        self.started = False
        self.session_id = None


# ----------------------------------------------------------------- gerente

_MANAGERS: dict[str, "MCPManager"] = {}


def get_manager(cfg) -> "MCPManager":
    key = str(cfg.data_dir)
    if key not in _MANAGERS:
        _MANAGERS[key] = MCPManager(cfg)
    return _MANAGERS[key]


class MCPManager:
    """Gerencia todos os servidores MCP configurados (uma instância por data dir)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._servers: dict[str, BaseMCPServer] = {}
        self._map: dict[str, tuple[str, str]] = {}      # mcp_x -> (servidor, original)
        self._meta: dict[str, dict] = {}                # mcp_x -> schema bruto
        self._server_tools: dict[str, list[str]] = {}   # servidor -> [mcp_x]
        self._state: dict[str, dict] = {}
        self._tried = False

    # ----------------------------------------------------------- configuração
    def _entries(self) -> list[dict]:
        out = []
        for e in self.cfg.mcp_servers or []:
            if isinstance(e, dict) and e.get("name"):
                out.append(e)
        return out

    def _make(self, e: dict) -> BaseMCPServer:
        timeout = float(e.get("timeout") or getattr(self.cfg, "mcp_timeout", 120))
        if e.get("url"):
            return HTTPServer(e["name"], e["url"], e.get("headers"), timeout)
        command = e.get("command")
        if not command:
            raise MCPError(f"servidor MCP '{e.get('name')}' sem 'command' nem 'url'")
        return StdioServer(
            e["name"], command, e.get("args") or [], e.get("env"),
            e.get("cwd") or str(PROJECT_ROOT), timeout,
        )

    # --------------------------------------------------------------- ciclo
    def start_all(self) -> None:
        self._tried = True
        for e in self._entries():
            name = str(e["name"])
            srv = self._servers.get(name)
            if srv and srv.alive():
                continue
            # placeholders de token no config = servidor nunca vai subir;
            # pula com mensagem clara em vez de travar o chat com timeout
            target = " ".join(
                [str(e.get("command", ""))] + [str(a) for a in e.get("args") or []]
                + [str(e.get("url", ""))]
            )
            if any(ph in target for ph in ("SEU-TOKEN", "YOUR-KEY", "SUA-CHAVE", "SUA-SENHA")):
                self._state[name] = {
                    "state": "erro",
                    "error": "placeholder de token no config — substitua pelo token real",
                }
                continue
            try:
                srv = self._make(e)
                srv.start()
                raw_tools = srv.list_tools()
                self._servers[name] = srv
                mapped_names = []
                for t in raw_tools:
                    orig = str(t.get("name") or "")
                    if not orig:
                        continue
                    mapped = map_tool_name(name, orig)
                    self._map[mapped] = (name, orig)
                    self._meta[mapped] = t
                    mapped_names.append(mapped)
                self._server_tools[name] = mapped_names
                self._state[name] = {"state": "ativo", "error": None}
            except Exception as exc:
                self._servers.pop(name, None)
                self._server_tools.pop(name, None)
                self._state[name] = {"state": "erro", "error": str(exc)[:400]}

    def _ensure(self) -> None:
        # Inicia UMA vez automaticamente. Servidores em erro NÃO são retentados
        # a cada mensagem (evita travar o chat esperando timeout) — use a GUI
        # (▶ ativar / ⟳ reiniciar) ou a API para tentar de novo.
        if not self._tried:
            self.start_all()

    def stop_all(self) -> None:
        for srv in self._servers.values():
            try:
                srv.stop()
            except Exception:
                pass
        self._servers.clear()
        self._map.clear()
        self._meta.clear()
        self._server_tools.clear()
        self._tried = False

    def restart(self) -> None:
        self.stop_all()
        self.start_all()

    # ------------------------------------------------------------- ferramentas
    def openai_tools(self) -> list[dict]:
        if not self._entries():
            return []
        self._ensure()
        tools = []
        for mapped, meta in self._meta.items():
            schema = meta.get("inputSchema") or {"type": "object", "properties": {}}
            desc = str(meta.get("description") or mapped).strip()[:600] or mapped
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": mapped,
                        "description": f"[MCP] {desc}",
                        "parameters": schema,
                    },
                }
            )
        return tools

    def handles(self, name: str) -> bool:
        return name in self._map

    def call(self, mapped: str, arguments: dict) -> dict:
        if mapped not in self._map:
            return {"ok": False, "output": f"ERRO: ferramenta MCP desconhecida: {mapped}"}
        sname, orig = self._map[mapped]
        srv = self._servers.get(sname)
        if not srv or not srv.alive():
            return {
                "ok": False,
                "output": f"ERRO: servidor MCP '{sname}' não está ativo "
                          "(ative no Painel → Servidores MCP e tente de novo)",
            }
        try:
            out = srv.call_tool(orig, arguments or {})
            return {"ok": True, "output": out[:6000]}
        except Exception as exc:
            # uma tentativa de recuperação: reinicia o servidor e repete
            try:
                srv.stop()
                srv.start()
                out = srv.call_tool(orig, arguments or {})
                return {"ok": True, "output": out[:6000]}
            except Exception:
                return {"ok": False, "output": f"ERRO MCP ({sname}.{orig}): {exc}"}

    # ---------------------------------------------------------------- status
    def status(self) -> list[dict]:
        out = []
        for e in self._entries():
            name = str(e["name"])
            srv = self._servers.get(name)
            if srv and srv.alive():
                state = "ativo"
                error = None
            elif name in self._state:
                state = self._state[name]["state"]
                error = self._state[name].get("error")
            else:
                state, error = "inativo", None
            transport = "http" if e.get("url") else "stdio"
            target = e.get("url") or " ".join([str(e.get("command", ""))] + [str(a) for a in e.get("args") or []])
            out.append(
                {
                    "name": name,
                    "transport": transport,
                    "target": target[:120],
                    "state": state,
                    "error": error,
                    "tools": self._server_tools.get(name, []),
                }
            )
        return out


def _shutdown_all() -> None:
    for mgr in _MANAGERS.values():
        try:
            mgr.stop_all()
        except Exception:
            pass


atexit.register(_shutdown_all)
