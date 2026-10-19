"""Ferramentas do agente: shell, arquivos e diagnóstico do sistema.

Segurança:
- Comandos perigosos (rm -rf /, mkfs, dd para disco, shutdown, curl|sh, ...)
  são SEMPRE bloqueados, independente de configuração.
- Com sandbox=True, operações de arquivo ficam restritas ao workspace.
- Todo comando tem timeout e saída truncada.
"""

from __future__ import annotations

import html as _html
import os
import platform
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

MAX_TOOL_OUTPUT = 6000

DANGEROUS_PATTERNS = [
    r"rm\s+[^;|&]*\s+/(?:\s|$)",          # rm ... /
    r"rm\s+-[a-z]*[rf][a-z]*\s+/*\s*$",   # rm -rf / (qualquer raiz)
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\b[^;|&]*of=/dev/",
    r":\s*\(\)\s*\{.*\}\s*;\s*:",          # fork bomb
    r"\b(shutdown|reboot|halt|poweroff|init\s+[06])\b",
    r">\s*/dev/s[a-z]",
    r"chmod\s+-R\s+777\s+/",
    r"(curl|wget)[^|;]*\|\s*(ba|z|sudo\s+)?(sh|bash)\b",
    r"\bmv\s+/\s+\S",
    r"chmod\s+[0-7]{3,4}\s+/dev/sd",
    r"insmod|rmmod\s+-[a-z]*a",
]


def is_dangerous(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in DANGEROUS_PATTERNS)


TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Executa um comando bash no Linux e retorna a saída combinada "
                "(stdout+stderr) com o código de saída. Use para diagnosticar e "
                "gerenciar o sistema."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Comando bash a executar"},
                    "timeout": {"type": "integer", "description": "Timeout opcional em segundos"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lê o conteúdo de um arquivo de texto (relativo ao workspace ou caminho absoluto).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Caminho do arquivo"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Cria/sobrescreve um arquivo de texto com o conteúdo fornecido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho do arquivo"},
                    "content": {"type": "string", "description": "Conteúdo completo a gravar"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lista o conteúdo de um diretório com tipo de cada entrada.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Diretório (padrão: workspace)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sys_info",
            "description": "Diagnóstico rápido da máquina: SO, kernel, CPU, memória, disco, uptime e carga.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lembrar",
            "description": (
                "Salva um fato/preferência sobre o usuário na memória persistente "
                "(ex.: 'meu curso é Engenharia de Produção', 'prefiro resumos curtos', "
                "'aulas de cálculo às terças'). Use SEMPRE que o usuário contar algo "
                "útil para o futuro — a memória vale para todas as conversas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string",
                              "description": "o fato a guardar, em uma frase curta"},
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Pesquisa na internet (DuckDuckGo) e devolve os principais "
                "resultados com título, endereço e resumo. Use para obter "
                "informações atuais, notícias, documentação e preços."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "o que pesquisar"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Baixa uma página da web (http/https) e devolve o texto limpo "
                "(sem HTML). Use depois de web_search para ler o conteúdo de um "
                "resultado, ou para abrir qualquer endereço fornecido pelo usuário."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "endereço http(s):// da página"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esquecer",
            "description": (
                "Apaga um fato da memória persistente pelo id (os ids aparecem "
                "entre colchetes na seção 'Memória' do seu prompt)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "id do fato (ex.: m1a2b3c4)"},
                },
                "required": ["id"],
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


class ToolError(Exception):
    pass


def _truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n… [saída truncada, {len(text)} caracteres no total] …\n" + text[-half:]


def resolve_path(path: str, cfg) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = cfg.workdir / p
    p = p.resolve()
    if cfg.sandbox:
        allowed = [str(cfg.workdir)]
        # skills ficam fora do workspace, mas são leitura/escrita liberada
        for d in getattr(cfg, "skills_dirs", []):
            allowed.append(str(Path(d).resolve()))
        if not any(str(p) == a or str(p).startswith(a + os.sep) for a in allowed):
            raise ToolError(
                f"caminho fora do workspace bloqueado pelo sandbox: {p} "
                f"(desative 'sandbox' nas configurações para liberar)"
            )
    return p


# ---------------------------------------------------------------- executores

def run_command(args: dict, cfg) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        return "ERRO: comando vazio."
    if is_dangerous(command):
        return (
            "BLOQUEADO por segurança: o comando coincide com um padrão perigoso "
            "(ex.: apagar a raiz, formatar disco, desligar a máquina, curl|sh). "
            "Reformule o comando."
        )
    timeout = int(args.get("timeout") or cfg.cmd_timeout)
    timeout = min(max(timeout, 1), 600)
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cfg.workdir),
        )
    except subprocess.TimeoutExpired:
        return f"$ {command}\n[TIMEOUT] execução excedeu {timeout}s e foi cancelada."
    except Exception as exc:
        return f"$ {command}\n[ERRO] {exc.__class__.__name__}: {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parts = [f"$ {command}", f"[código de saída: {proc.returncode}]"]
    if out:
        parts.append(out)
    if err:
        parts.append("[stderr]\n" + err)
    if not out and not err:
        parts.append("(sem saída)")
    return _truncate("\n".join(parts))


def read_file(args: dict, cfg) -> str:
    p = resolve_path(str(args.get("path", "")), cfg)
    if not p.exists():
        return f"ERRO: arquivo não encontrado: {p}"
    if not p.is_file():
        return f"ERRO: não é um arquivo: {p}"
    if p.stat().st_size > 512 * 1024:
        return f"ERRO: arquivo muito grande ({p.stat().st_size} bytes, limite 512 KB)."
    try:
        return _truncate(p.read_text(encoding="utf-8", errors="replace"), 8000)
    except Exception as exc:
        return f"ERRO ao ler {p}: {exc}"


def write_file(args: dict, cfg) -> str:
    p = resolve_path(str(args.get("path", "")), cfg)
    content = str(args.get("content", ""))
    if len(content) > 512 * 1024:
        return "ERRO: conteúdo acima do limite de 512 KB."
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: {len(content)} caracteres gravados em {p}"
    except Exception as exc:
        return f"ERRO ao gravar {p}: {exc}"


def list_dir(args: dict, cfg) -> str:
    p = resolve_path(str(args.get("path") or "."), cfg)
    if not p.exists():
        return f"ERRO: diretório não encontrado: {p}"
    if not p.is_dir():
        return f"ERRO: não é um diretório: {p}"
    try:
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except Exception as exc:
        return f"ERRO ao listar {p}: {exc}"
    lines = [f"{p}  ({len(entries)} entradas)"]
    for e in entries[:300]:
        tag = "dir " if e.is_dir() else "file"
        size = "" if e.is_dir() else f"  {e.stat().st_size} B"
        lines.append(f"[{tag}] {e.name}{size}")
    if len(entries) > 300:
        lines.append(f"… e mais {len(entries) - 300} entradas")
    return "\n".join(lines)


def _read_proc(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    return f"{d}d {h}h {m}min" if d else f"{h}h {m}min"


def sys_info(_args: dict, cfg) -> str:
    info = {
        "hostname": platform.node() or os.uname().nodename,
        "sistema": f"{platform.system()} {platform.release()}",
        "distribuição": " ".join(
            l.strip() for l in (_read_proc("/etc/os-release") or "").splitlines()
            if l.startswith("PRETTY_NAME")
        ).replace('PRETTY_NAME=', "").strip('"') or platform.platform(),
        "kernel": platform.release(),
        "arquitetura": platform.machine(),
        "cpu": f"{os.cpu_count()} núcleos ({platform.processor() or 'n/d'})",
        "python": platform.python_version(),
    }
    load = _read_proc("/proc/loadavg")
    if load:
        info["carga (1/5/15min)"] = " ".join(load.split()[:3])

    meminfo = _read_proc("/proc/meminfo") or ""
    m = re.search(r"MemTotal:\s+(\d+)", meminfo)
    a = re.search(r"MemAvailable:\s+(\d+)", meminfo)
    if m and a:
        total_kb, avail_kb = int(m.group(1)), int(a.group(1))
        info["memória"] = (
            f"{_human_size(total_kb * 1024)} total, {_human_size(avail_kb * 1024)} disponível "
            f"({(total_kb - avail_kb) / total_kb * 100:.0f}% em uso)"
        )
    try:
        du = shutil.disk_usage(str(cfg.workdir))
        info["disco"] = (
            f"{_human_size(du.total)} total, {_human_size(du.free)} livres "
            f"({(du.total - du.free) / du.total * 100:.0f}% em uso)"
        )
    except Exception:
        pass
    up = _read_proc("/proc/uptime")
    if up:
        info["uptime"] = _human_uptime(float(up.split()[0]))

    width = max(len(k) for k in info)
    return "\n".join(f"{k.ljust(width)} : {v}" for k, v in info.items())


# ---------------------------------------------------------------- web
def _web_enabled(cfg) -> bool:
    return bool(getattr(cfg, "web_access", True))


def _ddg_decode(url: str) -> str:
    """O DuckDuckGo devolve links-rediretor .../l/?uddg=<url real>."""
    if "uddg=" in url:
        q = parse_qs(urlparse(url).query).get("uddg", [url])
        return unquote(q[0])
    return url


def _html_to_text(page: str) -> str:
    txt = re.sub(r"(?is)<(script|style|noscript|head|svg)[^>]*>.*?</\1>", " ", page)
    txt = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr|/section)[^>]*>", "\n", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = _html.unescape(txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n\n", txt)
    return txt.strip()


WEB_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) hermes-agent",
               "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"}


def web_search(args: dict, cfg) -> str:
    if not _web_enabled(cfg):
        return "ERRO: acesso à web desativado nas configurações (Ajustes → 🌐 acesso à web)."
    query = str(args.get("query", "")).strip()
    if not query:
        return "ERRO: busca vazia — diga o que pesquisar."
    html = ""
    for endpoint in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
        try:
            r = requests.get(endpoint, params={"q": query}, headers=WEB_HEADERS, timeout=15)
            if r.status_code == 200 and "result" in r.text.lower():
                html = r.text
                break
        except requests.RequestException:
            continue
    if not html:
        return "ERRO: não consegui consultar o DuckDuckGo (sem internet ou bloqueio temporário — tente de novo)."
    raw = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    if not raw:  # formato do lite
        raw = re.findall(r'href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', html, re.S)
    snips = [_html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
             for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)]
    if not raw:
        return f"nenhum resultado para: {query}"
    lines = [f"resultados da web para: {query}"]
    for i, (url, title) in enumerate(raw[:6], 1):
        title = _html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        snip = snips[i - 1][:260] if i - 1 < len(snips) else ""
        lines.append(f"{i}. {title}\n   {_ddg_decode(url)}\n   {snip}")
    return _truncate("\n".join(lines))


def web_fetch(args: dict, cfg) -> str:
    if not _web_enabled(cfg):
        return "ERRO: acesso à web desativado nas configurações (Ajustes → 🌐 acesso à web)."
    url = str(args.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return "ERRO: informe um endereço começando com http:// ou https://"
    try:
        r = requests.get(url, headers=WEB_HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if ctype and not any(x in ctype for x in ("text/", "json", "xml", "html")):
            r.close()
            return (f"ERRO: conteúdo não é texto ({ctype}) — "
                    "use run_command com curl/wget para baixar arquivos.")
        chunks, total = [], 0
        for chunk in r.iter_content(65536):
            chunks.append(chunk)
            total += len(chunk)
            if total > 2 * 1024 * 1024:
                break
        r.close()
        page = b"".join(chunks).decode(r.encoding or "utf-8", errors="replace")
    except requests.RequestException as exc:
        return f"ERRO ao abrir {url}: {exc.__class__.__name__}: {exc}"
    text = _html_to_text(page) if "html" in ctype or "<html" in page[:500].lower() else page
    return _truncate(f"{url}\n{'─' * 60}\n{text}", 8000)


def lembrar(args: dict, cfg) -> str:
    from .memory import MemoryStore

    texto = str(args.get("texto", "")).strip()
    if not texto:
        return "ERRO: texto vazio — diga o que devo lembrar."
    fact = MemoryStore(cfg).add(texto)
    return f"OK: gravado na memória permanente [{fact['id']}]: {fact['text']}"


def esquecer(args: dict, cfg) -> str:
    from .memory import MemoryStore

    fid = str(args.get("id", "")).strip()
    if MemoryStore(cfg).delete(fid):
        return f"OK: fato {fid} apagado da memória."
    return f"ERRO: não encontrei o fato {fid} na memória."


EXECUTORS = {
    "run_command": run_command,
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "sys_info": sys_info,
    "lembrar": lembrar,
    "esquecer": esquecer,
    "web_search": web_search,
    "web_fetch": web_fetch,
}


def execute_tool(name: str, arguments: dict, cfg) -> dict:
    """Executa uma ferramenta e devolve {'ok': bool, 'output': str}."""
    if name not in EXECUTORS:
        return {"ok": False, "output": f"ERRO: ferramenta desconhecida: {name!r}"}
    try:
        args = dict(arguments or {})
        output = EXECUTORS[name](args, cfg)
        ok = not output.startswith(("ERRO", "BLOQUEADO"))
        return {"ok": ok, "output": output}
    except ToolError as exc:
        return {"ok": False, "output": f"ERRO: {exc}"}
    except Exception as exc:
        return {"ok": False, "output": f"ERRO inesperado em {name}: {exc.__class__.__name__}: {exc}"}


def tool_summary() -> str:
    return ", ".join(sorted(TOOL_NAMES))
