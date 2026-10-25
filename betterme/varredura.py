"""Varredura de segurança/privacidade — v4.0.0 (M1).

Duas funções vitais para a nova arquitetura:

1. ``varrer_*`` — scanner de segredos e dados pessoais em texto, arquivo
   ou repo. Base do ``betterme varredura`` (pré-push) e do gate de entrega
   do modo AUTÔNOMO.

2. ``mascarar`` — DLP (Data Loss Prevention) do pool de provedores
   gratuitos: recebe qualquer texto que vai sair da máquina e devolve o
   texto com segredos e blocos de código substituídos por marcadores.
   Regra D2 do operador: CÓDIGO NUNCA vai a provedores externos.

Falsos positivos: supressão inline com ``# varredura:ok`` na própria
linha e arquivo ``.varredura-ignore`` (globs, um por linha) na raiz.
"""
from __future__ import annotations

import re
from pathlib import Path
from .contratos import MARCA_CODIGO_BLOCO, MARCA_CODIGO_LINHA

# ------------------------------------------------------------- padrões
# (id, regex, severidade, descrição) — severidade: CRITICO bloqueia push
_PADROES: list[tuple[str, "re.Pattern[str]", str, str]] = [
    ("chave_groq", re.compile(r"gsk_[A-Za-z0-9]{20,}"), "CRITICO",
     "chave de API Groq"),
    ("chave_openai", re.compile(r"sk-[A-Za-z0-9]{20,}"), "CRITICO",
     "chave de API OpenAI"),
    ("chave_anthropic", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "CRITICO",
     "chave de API Anthropic"),
    ("chave_gemini", re.compile(r"AIza[0-9A-Za-z\-_]{30,}"), "CRITICO",
     "chave de API Google/Gemini"),
    ("token_github", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "CRITICO",
     "token do GitHub"),
    ("chave_aws", re.compile(r"AKIA[0-9A-Z]{16}"), "CRITICO",
     "access key da AWS"),
    ("chave_privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
     "CRITICO", "chave privada"),
    ("bearer", re.compile(r"Bearer\s+[A-Za-z0-9\-_.=]{25,}"), "CRITICO",
     "token Bearer"),
    ("senha_hardcoded", re.compile(
        r"(?i)\b(password|passwd|senha|secret|api_key|apikey)\b\s*[=:]\s*"
        r"[\"'][^\"'\s]{8,}[\"']"), "ALTO",
     "senha/segredo hardcoded"),
    ("cpf", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "ALTO",
     "número de CPF"),
    ("email_pessoal", re.compile(
        r"\b[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo|icloud|bol|uol)"
        r"\.[a-z]{2,}\b"), "MEDIO",
     "e-mail pessoal"),
]

_SEV_ORDER = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2}
_MARCADOR_SUPRESSAO = "# varredura:ok"

# blocos de código cercados por fences (DLP: código não sai da máquina)
_FENCE = re.compile(r"```.*?```", re.S)
# linhas com cara de código (heurística conservadora p/ texto sem fences)
_LINHA_CODIGO = re.compile(
    r"^\s*(def |class |import |from \w+ import |return |if __|"
    r"for \w+ in |[A-Za-z_][\w.]*\s*=\s*\S)")


def _ignorar(caminho: Path, raiz: Path) -> bool:
    """True se o caminho casa com .varredura-ignore da raiz (globs)."""
    ign = raiz / ".varredura-ignore"
    if not ign.is_file():
        return False
    try:
        import fnmatch
        rel = caminho.relative_to(raiz).as_posix()
        for lin in ign.read_text(encoding="utf-8").splitlines():
            lin = lin.strip()
            if lin and not lin.startswith("#") and fnmatch.fnmatch(rel, lin):
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _nomes_pessoais(cfg) -> list[str]:
    """Nomes que NUNCA devem aparecer em artefatos públicos.

    Vivem em ``<data_dir>/varredura-nomes.txt`` (um por linha) — arquivo
    PRIVADO da máquina do operador, fora do repo.
    """
    arq = Path(cfg.data_dir) / "varredura-nomes.txt"
    if not arq.is_file():
        return []
    try:
        return [l.strip() for l in
                arq.read_text(encoding="utf-8").splitlines()
                if len(l.strip()) >= 4]
    except Exception:  # noqa: BLE001
        return []


class Achado:
    __slots__ = ("id", "severidade", "descricao", "arquivo", "linha",
                 "trecho")

    def __init__(self, id_, sev, desc, arquivo, linha, trecho):
        self.id, self.severidade = id_, sev
        self.descricao, self.arquivo = desc, arquivo
        self.linha, self.trecho = linha, trecho

    def __repr__(self) -> str:  # pragma: no cover
        return (f"[{self.severidade}] {self.id} {self.arquivo}:"
                f"{self.linha} — {self.descricao}")


def _mascarar_trecho(linha: str, nomes: list[str] | None = None) -> str:
    """Trecho de contexto com segredos e nomes já censurados (p/ exibir)."""
    saida = linha.strip()[:100]
    for nome in (nomes or []):
        if nome:
            saida = saida.replace(nome, "×" * len(nome))
    for pid, rx, _s, _d in _PADROES:
        saida = rx.sub(f"[{pid}…]", saida)
    return saida


def varrer_texto(texto: str, arquivo: str = "(texto)",
                 nomes: list[str] | None = None) -> list[Achado]:
    """Varre um texto; linhas com o marcador de supressão são puladas."""
    achados: list[Achado] = []
    for i, lin in enumerate(texto.splitlines(), 1):
        if _MARCADOR_SUPRESSAO in lin:
            continue
        for nome in (nomes or []):
            if nome and nome in lin:
                achados.append(Achado(
                    "nome_pessoal", "ALTO", "nome pessoal configurado",
                    arquivo, i, _mascarar_trecho(lin, [nome])))
        for id_, rx, sev, desc in _PADROES:
            if rx.search(lin):
                achados.append(Achado(
                    id_, sev, desc, arquivo, i, _mascarar_trecho(lin, nomes)))
    return achados


def varrer_arquivo(path: Path, raiz: Path, nomes=None) -> list[Achado]:
    try:
        texto = path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    return varrer_texto(texto, path.relative_to(raiz).as_posix(), nomes)


def varrer_repo(cfg, raiz: Path | None = None) -> list[Achado]:
    """Varre os arquivos rastreados do repo (git ls-files)."""
    raiz = Path(raiz) if raiz else Path.cwd()
    nomes = _nomes_pessoais(cfg)
    arquivos: list[str]
    try:
        import subprocess
        out = subprocess.run(["git", "ls-files"], cwd=raiz,
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:80])
        arquivos = [a for a in out.stdout.splitlines() if a.strip()]
    except Exception:  # noqa: BLE001
        arquivos = [p.relative_to(raiz).as_posix() for p in raiz.rglob("*")
                    if p.is_file() and ".git" not in p.parts]
    achados: list[Achado] = []
    for rel in arquivos:
        p = raiz / rel
        if not p.is_file() or _ignorar(p, raiz):
            continue
        achados.extend(varrer_arquivo(p, raiz, nomes))
    return achados


def varrer_diff(cfg, raiz: Path | None = None) -> list[Achado]:
    """Varre o diff não commitado (staged + unstaged) — uso pré-push."""
    raiz = Path(raiz) if raiz else Path.cwd()
    nomes = _nomes_pessoais(cfg)
    import subprocess
    achados: list[Achado] = []
    for arg in (["diff", "HEAD"], ["diff", "--cached"]):
        try:
            out = subprocess.run(["git"] + arg, cwd=raiz,
                                 capture_output=True, text=True, timeout=30)
            if out.stdout:
                achados.extend(varrer_texto(out.stdout,
                                            f"git {arg[1]}", nomes))
        except Exception:  # noqa: BLE001
            pass
    return achados


# ---------------------------------------------------------------- DLP
def mascarar(texto: str) -> str:
    """DLP do pool externo: censura segredos, CPF, e-mails e CÓDIGO.

    - blocos ```fence``` viram ``[CÓDIGO LOCAL — não é enviado]``
    - linhas soltas com cara de código viram ``[CODIGO LOCAL]``
    - segredos/CPF/e-mails viram ``[REDACTED:<tipo>]``

    Última linha de defesa antes de QUALQUER payload sair para um
    provedor gratuito (regra D2 + risco #2 do pre-mortem v4.0.0).
    """
    saida = _FENCE.sub(MARCA_CODIGO_BLOCO, texto)
    linhas_out = []
    for lin in saida.splitlines():
        if _LINHA_CODIGO.match(lin):
            lin = MARCA_CODIGO_LINHA
        linhas_out.append(lin)
    saida = "\n".join(linhas_out)
    for id_, rx, _s, _d in _PADROES:
        tipo = ("senha" if id_ == "senha_hardcoded" else
                id_ if id_ in ("cpf", "email_pessoal") else "segredo")
        saida = rx.sub(f"[REDACTED:{tipo}]", saida)
    return saida


def cmd(args, cfg) -> int:
    """`betterme varredura` — retorna 1 se houver achado CRITICO."""
    raiz = Path(getattr(args, "raiz", None) or Path.cwd())
    if getattr(args, "tudo", False):
        achados = varrer_repo(cfg, raiz)
        escopo = "repo rastreado inteiro"
    else:
        achados = varrer_diff(cfg, raiz)
        if achados:
            escopo = "diff não commitado"
        else:
            achados = varrer_repo(cfg, raiz)
            escopo = "repo (diff vazio)"
    if not achados:
        print(f"🛡 varredura ({escopo}): limpo — nenhum achado.")
        return 0
    achados.sort(key=lambda a: (_SEV_ORDER.get(a.severidade, 9),
                                a.arquivo, a.linha))
    crit = sum(1 for a in achados if a.severidade == "CRITICO")
    print(f"🛡 varredura ({escopo}): {len(achados)} achado(s) "
          f"({crit} crítico(s))\n")
    for a in achados[:80]:
        print(f"  [{a.severidade:<7}] {a.arquivo}:{a.linha} — {a.id} "
              f"({a.descricao})")
        if a.trecho:
            print(f"           ↳ {a.trecho}")
    if crit:
        print("\n  ✖ CRÍTICO bloqueia o push. Corrija ou marque a linha com "
              "'# varredura:ok' se for falso positivo intencional.")
        return 1
    print("\n  ⚠ sem críticos — push permitido (revise os demais achados).")
    return 0
