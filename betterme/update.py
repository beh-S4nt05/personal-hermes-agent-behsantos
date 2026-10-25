"""`betterme update` — atualiza o projeto a partir do GitHub (v3.10).

Fluxo: consulta a última tag no repositório oficial → compara com a
versão instalada → baixa o zip da tag → aplica sobre a instalação atual
(preservando data/, .venv e .git). Stdlib pura (urllib/zipfile/shutil).

  betterme update --check   # só verifica se há versão nova
  betterme update           # verifica, confirma e aplica
  betterme update -y        # aplica sem perguntar (scripts)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .config import VERSION

REPO = "beh-S4nt05/personal-hermes-agent-behsantos"
TAGS_API = f"https://api.github.com/repos/{REPO}/tags?per_page=30"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/tags/{{tag}}.zip"

# o que NUNCA é tocado ao aplicar uma atualização
_PULA_DIRETORIOS = {"data", ".venv", ".git", ".github", "__pycache__",
                    "betterme_agent.egg-info", "node_modules"}
_PULA_ARQUIVOS = {".gitignore"}


def _parse_version(tag: str) -> tuple[int, ...]:
    """'v3.10.0' → (3,10,0); tags com sufixo (-beta, -rc) ficam (0,)."""
    parts = str(tag).lstrip("v").strip().split(".")
    if len(parts) != 3 or not all(x.isdigit() for x in parts):
        return (0,)
    return tuple(int(x) for x in parts)


def latest_tag(fetch=None) -> str | None:
    """Última tag do repositório (None se não conseguir consultar).
    `fetch(url) -> str` injetável para testes offline."""
    getter = fetch or (lambda url: urllib.request.urlopen(url, timeout=15)
                       .read().decode())
    try:
        tags = [t.get("name", "") for t in json.loads(getter(TAGS_API))]
        validas = [t for t in tags if _parse_version(t)]
        return max(validas, key=_parse_version) if validas else None
    except Exception:  # noqa: BLE001
        return None


def _project_root() -> Path:
    """Raiz da instalação (pasta que contém betterme/ e pyproject.toml)."""
    return Path(__file__).resolve().parent.parent


def _assert_zip_seguro(zf: zipfile.ZipFile, dest_dir: Path) -> None:
    """v3.14.2: defesa zip-slip — nenhum membro do zip pode escapar do
    diretório de destino (caminho absoluto ou com '..' é recusado)."""
    base = dest_dir.resolve()
    for nome in zf.namelist():
        if (dest_dir / nome).resolve() != base / nome.lstrip("/"):
            raise RuntimeError(f"zip com caminho inválido: {nome!r}")


def download(tag: str, dest_dir: Path) -> Path:
    """Baixa e extrai o zip da tag; devolve a raiz extraída."""
    url = ZIP_URL.format(tag=tag)
    zpath = dest_dir / f"{tag}.zip"
    with urllib.request.urlopen(url, timeout=120) as r, zpath.open("wb") as f:
        shutil.copyfileobj(r, f)
    with zipfile.ZipFile(zpath) as zf:
        _assert_zip_seguro(zf, dest_dir)
        zf.extractall(dest_dir)
    raiz = dest_dir / f"{REPO.split('/')[-1]}-{tag}"
    if not raiz.is_dir():
        # GitHub pode usar "personal-hermes-agent-behsantos-<sem v>"
        alt = dest_dir / f"{REPO.split('/')[-1]}-{tag.lstrip('v')}"
        if alt.is_dir():
            raiz = alt
        else:
            raise RuntimeError("zip extraído sem a pasta esperada do projeto")
    return raiz


def apply_update(src_root: Path, dest_root: Path,
                 log=print) -> list[str]:
    """Copia a nova versão sobre a instalação — preserva data/, .venv e
    .git. Devolve a lista de itens atualizados."""
    atualizados: list[str] = []
    for item in sorted(src_root.iterdir()):
        nome = item.name
        if nome in _PULA_DIRETORIOS or nome in _PULA_ARQUIVOS:
            continue
        if item.is_dir():
            shutil.copytree(item, dest_root / nome,
                            dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(
                                "__pycache__", "*.pyc", ".venv"))
        else:
            shutil.copy2(item, dest_root / nome)
        atualizados.append(nome)
    log(f"  ✔ {len(atualizados)} itens atualizados: "
        + ", ".join(atualizados[:8]) + ("…" if len(atualizados) > 8 else ""))
    return atualizados


def run(check_only: bool = False, assume_yes: bool = False,
        print_fn=print) -> int:
    """Executa o update; devolve código de saída (0 = ok/atualizado)."""
    print_fn(f"⬇ betterme update · versão instalada: v{VERSION}")
    tag = latest_tag()
    if not tag:
        print_fn("✖ não consegui consultar o GitHub (sem internet?) — "
                 "tente: betterme update --check")
        return 1
    print_fn(f"  última versão no GitHub: {tag}")
    if _parse_version(tag) <= _parse_version(VERSION):
        print_fn("✔ você já está na versão mais recente.")
        return 0
    if check_only:
        print_fn(f"ℹ há atualização: v{VERSION} → {tag} — rode: betterme update")
        return 0
    if not assume_yes:
        try:
            resp = input(f"  aplicar v{VERSION} → {tag}? [s/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = ""
        if resp not in ("s", "sim", "y", "yes"):
            print_fn("  cancelado.")
            return 1
    root = _project_root()
    with tempfile.TemporaryDirectory(prefix="betterme-update-") as tmp:
        src = download(tag, Path(tmp))
        print_fn(f"  baixado e extraído: {tag}")
        apply_update(src, root, log=print_fn)
    print_fn("\n  ✔ atualização aplicada. Se o `betterme server` estiver rodando,")
    print_fn("    reinicie-o (GUI: ⏹ Desligar → ▶ Ligar) para valer.")
    print_fn("    Dependências novas (se houver): ./.venv/bin/pip install -e . -q")
    return 0
