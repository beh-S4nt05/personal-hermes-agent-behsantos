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
import shutil
import subprocess

from . import plataforma
import threading
from contextlib import contextmanager
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
    # v6.0.0: destrutivos do Windows (cmd/PowerShell) — bloqueio em ANY SO
    r"\brd\s+[^|;&]*/[sq]",
    r"\bdel\s+[^|;&]*/[fsq]",
    r"\bformat(\.com)?\s+[a-z]:",
    r"\breg\s+delete\s+[^|;&]*\s/f",
    r"remove-item\s+[^|;&]*(-recurse[^|;&]*-force|-force[^|;&]*-recurse)",
    r"\bdiskpart\b",
]


def is_dangerous(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in DANGEROUS_PATTERNS)


# credenciais do e-mail (v3.1): o agente jamais pode ler/vazar o arquivo
SECRETS_RE = re.compile(
    r"secrets?[/\\~]|email\.json|\.betterme[/\\]+secrets", re.IGNORECASE)


def touches_secrets(command: str) -> bool:
    return bool(SECRETS_RE.search(command))


TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "gerente_codigo",
            "description": (
                "Delega uma task de CÓDIGO ao GERENTE DE CÓDIGO (Claude "
                "Code) e devolve o resultado pleno. Requer ativação "
                "explícita do operador (betterme gerente on --yes) — quando "
                "desligado, explique e faça você mesmo. Use para "
                "refatorações grandes, código complexo ou quando o "
                "operador pedir expressamente o gerente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string",
                             "description": "tarefa de código autônoma e "
                                            "completa (contexto incluso)"},
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conversas_buscar",
            "description": (
                "Busca nas CONVERSAS PASSADAS com o operador (decisões, "
                "contexto, o que já foi combinado). Use quando a resposta "
                "depender de histórico antigo em vez de repetir perguntas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string",
                              "description": "palavra/frase a buscar"},
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "especialista",
            "description": (
                "Invoca um ESPECIALISTA (subagente escopado) para um caso "
                "pontual e recebe um veredito estruturado com evidência. "
                "Use quando quiser uma segunda opinião especializada: "
                "revisar trabalho pronto, diagnosticar erro difícil, "
                "sintetizar fontes ou auditar segurança. O especialista "
                "apenas PROPÕE ações — não executa nada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string",
                        "enum": ["revisor", "debugger", "pesquisador",
                                 "seguranca"],
                        "description": "Qual especialista invocar",
                    },
                    "caso": {
                        "type": "string",
                        "description": (
                            "Descrição autônoma do caso: contexto, o que "
                            "aconteceu, arquivos/linhas/saídas relevantes "
                            "(sem dados pessoais)"
                        ),
                    },
                },
                "required": ["nome", "caso"],
            },
        },
    },
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
            "name": "git_run",
            "description": (
                "Controle de versão git NO PROJETO: init, status, add, "
                "commit, log, diff, branch, tag, config local. Use para "
                "versionar o código produzido (commits claros) e examinar "
                "histórico/alterações."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "description": "Subcomando: init, status, add, "
                                              "commit, log, diff, branch, "
                                              "checkout, show, tag, restore, "
                                              "stash, config"},
                    "args": {"type": "string",
                             "description": "Argumentos extras (ex.: \"-m 'mensagem'\")"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": (
                "Busca na BIBLIOTECA de livros/documentos do operador "
                "(RAG local) e devolve trechos verbatim com a fonte. Use "
                "para consultar referência, documentação, livro, técnica, "
                "padrão de projeto ou sintaxe antes de escrever código."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta"},
                },
                "required": ["query"],
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
            "name": "diagnostico_sistema",
            "description": "Diagnóstico COMPLETO do dispositivo em UMA chamada — disco, memória, processos que mais consomem RAM/CPU, maiores pastas da home, bateria, GPU, uptime e últimos logins, com saída real e compacta. Use para 'como está o sistema', 'uso do dispositivo', 'diagnóstico geral', 'o que está lento', saúde da máquina — NÃO fique chamando sys_info/df/free um por um.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lembrar",
            "description": "Salva um fato sobre o usuário na memória permanente (vale para todas as conversas).",
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
            "description": "Pesquisa na internet (DuckDuckGo): títulos, endereços e resumos. Use para informação atual.",
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
            "description": "Abre uma página http(s) e devolve o texto limpo. Use para ler um resultado da busca.",
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
            "name": "backups",
            "description": (
                "Lista e restaura backups automáticos de arquivos (toda escrita "
                "guarda a versão anterior). action=list (path opcional filtra) "
                "ou action=restore com id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "list | restore"},
                    "path": {"type": "string", "description": "arquivo de origem (filtro)"},
                    "id": {"type": "string", "description": "id do backup (restore)"},
                },
                "required": ["action"],
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
    {
        "type": "function",
        "function": {
            "name": "grafo_query",
            "description": (
                "Consulta o GRAFO DE CÓDIGO do projeto (AST local, "
                "milissegundos, ZERO tokens): onde está a lógica de X? "
                "Use ANTES de ler arquivos às cegas — devolve "
                "função/classe/método com arquivo:linha e o que faz; "
                "com 'de'+'para' traça o caminho de chamadas A→B. "
                "Requer `betterme grafo build` na raiz do projeto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string",
                              "description": "nome (ou parte) de função/"
                                             "classe/método a localizar"},
                    "de": {"type": "string",
                           "description": "origem do caminho de chamadas "
                                          "(usar junto com 'para')"},
                    "para": {"type": "string",
                             "description": "destino do caminho de chamadas"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revisar_diff",
            "description": (
                "Revê o diff não commitado do projeto (git diff HEAD) e "
                "emite veredito com arquivo:linha — gate único pré-push: "
                "varredura objetiva de segredos + revisor LOCAL (código "
                "jamais sai da máquina). Use quando o operador pedir "
                "'revise o diff' ou antes de commitar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "raiz": {"type": "string",
                             "description": "raiz do repo git (default: "
                                            "diretório atual)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fluxos_chamar",
            "description": (
                "Dispara um workflow do n8n LOCAL por webhook "
                "(http://127.0.0.1:5678/webhook/<caminho>). Use para "
                "automações visuais construídas na aba ⚙ Fluxos do GUI. "
                "Requer o n8n rodando (betterme fluxos start). Use "
                "fluxos_listar antes para descobrir os workflows e "
                "seus paths de webhook."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string",
                                "description": "id ou path do webhook do "
                                               "workflow"},
                    "payload": {"type": "object",
                                "description": "dados a enviar (JSON)"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fluxos_listar",
            "description": (
                "v6.3.2: lista os workflows do n8n LOCAL (nome, ativo, "
                "nº de nós e paths de webhook). Use ANTES de "
                "fluxos_chamar para descobrir o path certo — ex.: o "
                "operador pede 'dispare o Backup diário' e você encontra "
                "o path aqui. Requer API key (betterme fluxos apikey) e "
                "n8n rodando (betterme fluxos start)."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
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


# v3.13.1: pastas JAMAIS lidas pelo agente, nem com sandbox_home_read —
# credenciais não entram no contexto do modelo
_SENSITIVE_READ = ["~/.betterme/secrets", "~/.ssh", "~/.gnupg", "~/.config",
                   "~/.aws", "~/.docker", "~/.netrc", "~/.git-credentials"]


# ──────────── v3.15.0 (PR#1): PASTA DO PROJETO declarada no pedido ────────────
# O operador passa a referência (já criada ou a criar); o Betterme percorre/cria
# o caminho em QUALQUER ponto do diretório e trabalha lá — sem interferir na
# própria configuração (~/.betterme). Escopo é por THREAD: tasks concorrentes
# não vazam escopo umas para as outras.

_SCOPE_DENY = ("/tmp", "/proc", "/sys", "/dev", "/etc", "/var", "/usr",
               "/boot", "/run", "/snap")
_TASK_SCOPE = threading.local()


def validar_escopo_projeto(path, cfg=None) -> Path:
    """Valida (sem criar) a pasta de projeto declarada pelo operador."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ToolError(
            "caminho de projeto deve ser absoluto (ex.: /media/Arquivos/projetos "
            "/app ou ~/projetos/app)")
    p = p.resolve()
    if p == Path.home().resolve():
        raise ToolError(
            "escopo recusado: a HOME inteira não pode ser o workspace da task — "
            "aponte a pasta do projeto")
    for sysdir in _SCOPE_DENY:
        if p == Path(sysdir) or Path(sysdir) in p.parents:
            raise ToolError(f"escopo recusado: {sysdir} é diretório do sistema")
    if cfg is not None:
        d = Path(cfg.data_dir).resolve()
        if p == d or d in p.parents:
            raise ToolError(
                "escopo recusado: ~/.betterme é a configuração do Betterme — o "
                "projeto não pode apontar para cá")
    return p


@contextmanager
def task_scope(path, cfg=None):
    """Ativa a pasta do projeto para ESTA task: percorre/cria o caminho,
    vira o cwd dos comandos e libera leitura+escrita DENTRO dela."""
    p = validar_escopo_projeto(path, cfg)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ToolError(
            f"não foi possível criar/percorrer a pasta do projeto {p}: "
            f"{exc}") from exc
    _TASK_SCOPE.workdir = p
    try:
        yield p
    finally:
        _TASK_SCOPE.workdir = None


def scope_dir() -> Path | None:
    """Pasta do projeto ativa nesta thread (None = workspace padrão)."""
    return getattr(_TASK_SCOPE, "workdir", None)


def resolve_path(path: str, cfg, write: bool = False) -> Path:
    """Resolve caminho com as regras de sandbox.

    write=True (write_file): sempre restrito ao workspace + skills.
    write=False (read_file/list_dir): com sandbox_home_read=True, a HOME
    inteira é LEGÍVEL (diagnósticos do sistema) — exceto pastas
    sensíveis, que nunca são."""
    p = Path(path).expanduser()
    esc = scope_dir()
    if not p.is_absolute():
        p = (esc or cfg.workdir) / p   # v3.15.0: relativo → pasta do projeto
    p = p.resolve()
    if cfg.sandbox:
        allowed = [str(cfg.workdir)]
        # skills ficam fora do workspace, mas são leitura/escrita liberada
        for d in getattr(cfg, "skills_dirs", []):
            allowed.append(str(Path(d).resolve()))
        if esc is not None:
            allowed.append(str(esc))  # v3.15.0: pasta do projeto desta task
        ok = any(str(p) == a or str(p).startswith(a + os.sep) for a in allowed)
        if not ok and not write and getattr(cfg, "sandbox_home_read", True):
            home = str(Path.home().resolve())
            dentro_home = str(p) == home or str(p).startswith(home + os.sep)
            sensiveis = [str(Path(s).expanduser().resolve())
                         for s in _SENSITIVE_READ]
            bloqueada = any(str(p) == s or str(p).startswith(s + os.sep)
                            for s in sensiveis)
            if bloqueada:
                raise ToolError(
                    f"pasta sensível bloqueada (credenciais nunca entram no "
                    f"contexto do modelo): {p}")
            if dentro_home:
                return p               # leitura da home liberada (v3.13.1)
        if not ok:
            raise ToolError(
                f"caminho fora do workspace bloqueado pelo sandbox: {p} "
                f"(para ESCRITA, use o workspace; leitura da home: "
                f"sandbox_home_read)"
            )
    return p


# ---------------------------------------------------------------- executores

def run_command(args: dict, cfg) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        return "ERRO: comando vazio."
    if touches_secrets(command):
        return (
            "BLOQUEADO: este comando acessa o arquivo de credenciais (secrets). "
            "As senhas NUNCA passam pelo agente — para ler/responder e-mails, "
            "use as ferramentas mcp_email_* (email_list, email_read, email_send)."
        )
    if is_dangerous(command):
        return (
            "BLOQUEADO por segurança: o comando coincide com um padrão perigoso "
            "(ex.: apagar a raiz, formatar disco, desligar a máquina, curl|sh). "
            "Reformule o comando."
        )
    timeout = int(args.get("timeout") or cfg.cmd_timeout)
    timeout = min(max(timeout, 1), 600)
    try:
        # v4.0.0 (M4): kernel primeiro (bwrap+seccomp), denylist fica como
        # segunda camada — defesa em profundidade; sem bwrap, segue app
        from .sandbox_kernel import envolver_comando, fechar_fds
        _wd = str(scope_dir() or cfg.workdir)
        argv, _fds = envolver_comando(cfg, plataforma.shell_argv(command),
                                    _wd)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=_wd,  # v3.15.0: projeto da task
                pass_fds=tuple(_fds),
            )
        finally:
            fechar_fds(_fds)
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
    from .backups import backup_file

    p = resolve_path(str(args.get("path", "")), cfg, write=True)
    content = str(args.get("content", ""))
    if len(content) > 512 * 1024:
        return "ERRO: conteúdo acima do limite de 512 KB."
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_file(cfg, p)  # v3.0: nada é sobrescrito sem volta
        p.write_text(content, encoding="utf-8")
        nota = f" (backup da versão anterior: {backup.name})" if backup else ""
        return f"OK: {len(content)} caracteres gravados em {p}{nota}"
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


# v3.13.2: bateria fixa e SOMENTE-LEITURA — o modelo não injeta
# comandos aqui; ele recebe o digesto pronto para interpretar
def diagnostico_sistema(_args: dict, cfg) -> str:
    """v3.13.2: o diagnóstico inteiro NUMA chamada só. Devolve digesto
    real e compacto — o executor interpreta, não flailha em dezenas de
    sys_info/df/free (e não precisa inventar dado: ele está aqui)."""
    secoes = []
    from . import plataforma as _plat
    for nome, cmd, tmax in _plat.diag_commands():
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=tmax, check=False)
            out = (r.stdout or "").strip()
        except subprocess.TimeoutExpired:
            out = "(comando demorou — pulado)"
        except Exception as exc:  # noqa: BLE001
            out = f"(falhou: {exc.__class__.__name__})"
        if not out:
            out = "(vazio)"
        out = "\n".join(out.splitlines()[:10])[:600]
        secoes.append(f"== {nome} ==\n{out}")
    return "\n\n".join(secoes)[:4000]


def sys_info(_args: dict, cfg) -> str:
    info = {
        "hostname": plataforma.hostname() or "desconhecido",
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


WEB_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) betterme-agent",
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


def _backups_tool(args: dict, cfg) -> str:
    from .backups import tool_backups
    return tool_backups(args, cfg)


_GIT_OK = {"init", "status", "add", "commit", "log", "diff", "branch",
           "checkout", "show", "tag", "restore", "stash", "config"}


def git_run(args: dict, cfg) -> str:
    """v3.15.0 (PR#2): git com subcomandos permitidos, no projeto da task."""
    import shlex
    acao = str(args.get("action", "")).strip().lower()
    extra = str(args.get("args", "")).strip()
    if acao not in _GIT_OK:
        return (f"BLOQUEADO: subcomando git não permitido: {acao!r}. "
                f"Permitidos: {', '.join(sorted(_GIT_OK))} "
                "(push/pull ficam via run_command, se o operador quiser).")
    if acao == "config" and re.search(r"--global|--system", extra):
        return "BLOQUEADO: config --global/--system altera a máquina do operador — só config local do repositório."
    cmd = ["git", acao] + shlex.split(extra)
    cwd = scope_dir() or cfg.workdir
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                           check=False, cwd=str(cwd))
    except FileNotFoundError:
        return "ERRO: git não está instalado nesta máquina."
    except subprocess.TimeoutExpired:
        return f"$ git {acao}\n[TIMEOUT] excedeu 30s."
    out = ((r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr.strip() else "")).strip()
    return f"$ git {acao} {extra}".strip() + f"\n{out[:4000] if out else '(sem saída)'}"


def gerente_codigo_tool(args: dict, cfg) -> str:
    """v4.0.0 (M7, D5): delega uma task de CÓDIGO ao gerente Claude
    (só se o operador ativou com `betterme gerente on --yes`)."""
    from .code_manager import delegar
    task = str(args.get("task", "")).strip()
    return delegar(cfg, task)


def conversas_buscar(args: dict, cfg) -> str:
    """v4.0.0 (M6.5): busca nas conversas passadas (decisões antigas)."""
    from .learning import buscar_conversas
    termo = str(args.get("termo", "")).strip()
    if not termo:
        return "ERRO: informe 'termo'."
    ach = buscar_conversas(cfg, termo)
    if not ach:
        return f"nenhuma conversa anterior menciona {termo!r}."
    partes = [f"🗂 {len(ach)} trecho(s) de conversas passadas:"]
    for a_ in ach:
        partes.append(f"  • [{a_['data']} · {a_['role']} · {a_['titulo']}"
                      f" ({a_['session']})]")
        partes.append(f"    \"{a_['trecho']}\"")
    return "\n".join(partes)[:4000]


def especialista_tool(args: dict, cfg) -> str:
    """v4.0.0 (M6): o cérebro invoca um especialista (revisor, debugger,
    pesquisador, seguranca) para um caso pontual — veredito com evidência,
    nunca escreve no disco (single-writer)."""
    from .specialists import invocar
    nome = str(args.get("nome", "")).strip().lower()
    caso = str(args.get("caso", "")).strip()
    if not nome or not caso:
        return ("ERRO: informe 'nome' (revisor|debugger|pesquisador|"
                "seguranca) e 'caso' (descrição do problema).")
    r = invocar(cfg, nome, caso)
    if not r.get("ok"):
        return (f"✖ especialista {nome}: REPROVADO — {r.get('motivo', '')} "
                f"(provedor {r.get('provedor')}; o pipeline segue sem ele)")
    v = r["veredito"]["veredito"]
    ev = "\n".join(
        f"  • {e.get('arquivo', '(sem arquivo)')}"
        f"{':' + str(e['linha']) if e.get('linha') else ''}: "
        f"{str(e.get('trecho', ''))[:100]}"
        for e in v.get("evidencia", []))
    return (f"🧪 especialista {nome} ({r.get('provedor')}, "
            f"{r.get('latencia_s')}s, confiança {v.get('confianca')}):\n"
            f"DIAGNÓSTICO: {v.get('diagnostico')}\n"
            f"AÇÃO PROPOSTA: {v.get('acao_proposta')}\n"
            f"EVIDÊNCIA:\n{ev or '  (sem arquivos)'}")


def knowledge_search(args: dict, cfg) -> str:
    """v3.15.0 (PR#2): RAG local — trechos verbatim com fonte."""
    from . import knowledge
    consulta = str(args.get("query", "")).strip()
    if not consulta:
        return "ERRO: consulta vazia."
    achados = knowledge.buscar(cfg, consulta, k=3)
    if not achados:
        st = knowledge.status(cfg)
        return (f"nada encontrado para {consulta!r} "
                f"(biblioteca: {st['livros']} livro(s), {st['blocos']} trechos "
                f"— adicione livros em {knowledge.biblioteca_dir(cfg)} e rode "
                "`betterme rag`)")
    partes = [f"📚 {len(achados)} trecho(s) da biblioteca (verbatim, com fonte):"]
    for i, r in enumerate(achados, 1):
        partes.append(f"\n── [{i}] FONTE: {r['fonte']} "
                      f"(relevância {r['score']})\n{r['texto']}")
    return "\n".join(partes)[:6000]


def fluxos_chamar(args: dict, cfg) -> str:
    """v5.1.0 (PR#11): dispara workflow n8n local por webhook."""
    from . import fluxos
    caminho = str(args.get("caminho", "")).strip()
    payload = args.get("payload") or {}
    if not caminho:
        return "ERRO: informe 'caminho' (id/path do webhook do workflow)."
    r = fluxos.chamar(cfg, caminho, payload)
    if not r.get("ok"):
        return f"ERRO: {r.get('msg', 'webhook falhou')}"
    return f"⛓ workflow disparado (HTTP {r.get('status', '?')}): " \
           f"{str(r.get('msg', ''))[:300]}"


def fluxos_listar(args: dict, cfg) -> str:
    """v6.3.2: lista os workflows do n8n local (nome, ativo, nós,
    webhooks) — o cérebro descobre o path e dispara com fluxos_chamar."""
    from . import fluxos
    r = fluxos.listar(cfg)
    if not r.get("ok"):
        return f"ERRO: {r.get('msg', 'n8n indisponível')}"
    linhas = []
    for w in r["workflows"]:
        estado = "ATIVO" if w["ativo"] else "inativo"
        hooks = ", ".join(w["webhooks"]) or "sem webhook"
        linhas.append(f"· {w['nome']} [{estado}, {w['nos']} nós] — "
                      f"webhook(s): {hooks}")
    if not linhas:
        return ("⛓ nenhum workflow no n8n local — crie um no editor "
                "(aba ⚙ Fluxos) ou importe os templates prontos")
    return ("⛓ workflows do n8n local (dispare com fluxos_chamar usando "
            "o path do webhook):\n" + "\n".join(linhas))


def revisar_diff(args: dict, cfg) -> str:
    """v4.5.0 (PR#8): revisão de diff — veredito com arquivo:linha."""
    from . import revisar
    raiz = str(args.get("raiz", "")).strip() or None
    return revisar.revisar_texto(
        revisar.revisar(cfg, Path(raiz) if raiz else None))


def grafo_query(args: dict, cfg) -> str:
    """v4.4.0 (PR#7): grafo de código — onde está a lógica de X? (zero tokens)."""
    from . import grafo
    de = str(args.get("de", "")).strip()
    para = str(args.get("para", "")).strip()
    if de and para:
        return grafo.path_text(cfg, de, para)
    termo = str(args.get("termo", "")).strip()
    if not termo:
        return "ERRO: informe 'termo' (ou 'de'+'para' para caminho de chamadas)."
    return grafo.query_text(cfg, termo)


EXECUTORS = {
    "run_command": run_command,
    "git_run": git_run,
    "knowledge_search": knowledge_search,
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "sys_info": sys_info,
    "diagnostico_sistema": diagnostico_sistema,
    "lembrar": lembrar,
    "esquecer": esquecer,
    "web_search": web_search,
    "web_fetch": web_fetch,
    "backups": _backups_tool,
    "especialista": especialista_tool,
    "conversas_buscar": conversas_buscar,
    "gerente_codigo": gerente_codigo_tool,
    "grafo_query": grafo_query,
    "revisar_diff": revisar_diff,
    "fluxos_chamar": fluxos_chamar,
    "fluxos_listar": fluxos_listar,
}


def execute_tool(name: str, arguments: dict, cfg, source: str = "agent",
                 agent: str = "betterme") -> dict:
    """Executa uma ferramenta e devolve {'ok': bool, 'output': str}.

    v3.0: toda execução vai para a trilha de auditoria (data/audit/).
    """
    import time as _time
    from . import audit as _audit

    if name not in EXECUTORS:
        return {"ok": False, "output": f"ERRO: ferramenta desconhecida: {name!r}"}
    t0 = _time.time()

    def _atividade(ok: bool, output: str) -> None:
        """v3.1.1: execução visível no Log ao vivo do painel."""
        try:
            from . import activity
            hint = ""
            for k in ("command", "path", "query", "url", "texto", "to"):
                if args.get(k):
                    hint = f" · {str(args[k])[:60]}"
                    break
            activity.log(cfg, "agente",
                         f"⚙ {name}{hint} → {'ok' if ok else 'ERRO'} "
                         f"({int((_time.time() - t0) * 1000)} ms)")
        except Exception:  # noqa: BLE001
            pass

    try:
        args = dict(arguments or {})
        output = EXECUTORS[name](args, cfg)
        ok = not output.startswith(("ERRO", "BLOQUEADO"))
        _audit.log(cfg, agent, name, args, ok, output,
                   duration_ms=int((_time.time() - t0) * 1000), source=source)
        _atividade(ok, output)
        return {"ok": ok, "output": output}
    except ToolError as exc:
        _audit.log(cfg, agent, name, arguments, False, str(exc),
                   duration_ms=int((_time.time() - t0) * 1000), source=source)
        return {"ok": False, "output": f"ERRO: {exc}"}
    except Exception as exc:
        msg = f"ERRO inesperado em {name}: {exc.__class__.__name__}: {exc}"
        _audit.log(cfg, agent, name, arguments, False, msg,
                   duration_ms=int((_time.time() - t0) * 1000), source=source)
        return {"ok": False, "output": msg}


def tool_summary() -> str:
    return ", ".join(sorted(TOOL_NAMES))
