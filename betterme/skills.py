"""Sistema de skills do Betterme Agent (formato aberto SKILL.md).

Uma skill é uma pasta com um SKILL.md: frontmatter YAML (name, description)
+ instruções em Markdown, opcionalmente com scripts/ e referências. O agente
recebe apenas o catálogo (nome + descrição + caminho) no prompt de sistema e
lê o conteúdo completo só quando a tarefa combina (progressive disclosure).

Diretórios:
- skills/ do projeto     → skills embutidas (incluídas no repositório)
- <data_dir>/skills/     → skills do usuário (instaladas via GUI/GitHub ou
                           criadas pelo próprio agente com write_file)
"""

from __future__ import annotations

import io
import re
import shutil
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_GITHUB_HOSTS = ("https://github.com/", "http://github.com/", "https://www.github.com/")

# cache simples do catálogo (a GUI consulta a cada poucos segundos)
_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_CACHE_TTL = 5.0


# ──────────── v3.15.0 (PR#3): skills baixadas viram NATIVAS ────────────
# O operador baixa skills do GitHub (zip/clone) ou de onde for; o Betterme
# descobre pastas com SKILL.md válido e importa para ~/.betterme/skills —
# nunca sobrescreve, audita e liga por padrão.

_SKILL_NAME_RE = re.compile(r"[^a-z0-9-]+")


def _slug(nome: str, fallback: str = "skill") -> str:
    s = _SKILL_NAME_RE.sub("-", str(nome or "").strip().lower()).strip("-")
    return (s or fallback)[:48]


def find_skill_dirs(root, depth: int = 3) -> list[Path]:
    """Pastas com SKILL.md válido (name+description) sob `root`."""
    root = Path(root).expanduser().resolve()
    achados: list[Path] = []
    try:
        cand = list(root.rglob("SKILL.md"))
    except OSError:
        return []
    for md in cand[:200]:
        try:
            rel = md.parent.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) > depth:
            continue
        if any(p.startswith(".") for p in rel.parts):
            continue
        try:
            meta, _ = parse_skill_md(
                md.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if meta.get("name") and meta.get("description"):
            achados.append(md.parent)
    return achados


def import_skill_dir(src_dir, cfg) -> dict:
    """Copia UMA pasta de skill para ~/.betterme/skills/<nome>."""
    src_dir = Path(src_dir).resolve()
    md = src_dir / "SKILL.md"
    if not md.is_file():
        return {"ok": False, "msg": f"sem SKILL.md em {src_dir}"}
    meta, _ = parse_skill_md(md.read_text(encoding="utf-8", errors="replace"))
    nome = _slug(meta.get("name"), src_dir.name)
    dest = SkillLoader(cfg).user_dir / nome
    if dest.exists():
        return {"ok": False, "skipped": True, "name": nome,
                "msg": f"skill '{nome}' já existe — nada sobrescrito"}
    shutil.copytree(src_dir, dest)
    _CACHE.clear()          # v3.15.0: skill nova é nativa NA HORA
    return {"ok": True, "name": nome, "dest": str(dest)}


def _importar_todas(dirs: list[Path], cfg) -> dict:
    importadas, puladas = [], []
    for d in dirs:
        r = import_skill_dir(d, cfg)
        if r.get("ok"):
            importadas.append(r["name"])
        elif r.get("skipped"):
            puladas.append(r.get("name", d.name))
    msg = (f"{len(importadas)} skill(s) importada(s)"
           + (f": {', '.join(importadas)}" if importadas else "")
           + (f" · {len(puladas)} já existente(s)" if puladas else "")
           + ("" if importadas else " — nenhuma skill nova encontrada"))
    return {"ok": bool(importadas or not dirs), "importadas": importadas,
            "puladas": puladas, "msg": msg}


def import_from(src: str, cfg) -> dict:
    """Importa skills de QUALQUER fonte: pasta local, arquivo .zip,
    URL git/GitHub ou owner/repo (delega no install_from_github)."""
    src = (src or "").strip()
    if not src:
        return {"ok": False,
                "msg": "informe a fonte: pasta, .zip, URL ou owner/repo"}
    if src.startswith(("http://", "https://", "git@")):
        return SkillLoader(cfg).install_from_github(src)
    if re.fullmatch(r"[\w.-]+/[\w.-]+", src):
        return SkillLoader(cfg).install_from_github(src)
    p = Path(src).expanduser()
    if p.suffix.lower() == ".zip" and p.is_file():
        with tempfile.TemporaryDirectory(prefix="betterme-skills-") as td:
            try:
                with zipfile.ZipFile(p) as zf:
                    for nome in zf.namelist():
                        if ".." in nome.split("/"):
                            raise RuntimeError(f"zip com caminho inválido: {nome!r}")
                    zf.extractall(td)
            except (zipfile.BadZipFile, RuntimeError) as exc:
                return {"ok": False, "msg": f"zip inválido: {exc}"}
            return _importar_todas(find_skill_dirs(Path(td)), cfg)
    if p.is_dir():
        alvos = find_skill_dirs(p)
        if (p / "SKILL.md").is_file():
            alvos = [p] + [a for a in alvos if a != p]
        return _importar_todas(alvos, cfg)
    return {"ok": False, "msg": f"fonte não encontrada: {src}"}


def autoscan(cfg) -> dict:
    """Varre as pastas assistidas (default ~/Downloads) e importa skills
    novas — o 'baixei do GitHub, agora é nativa' sem comando nenhum."""
    if not getattr(cfg, "skills_autoscan", True):
        return {"ok": True, "importadas": [], "msg": "autoscan desligado"}
    pastas = getattr(cfg, "skills_watch_dirs", None) or [
        str(Path.home() / "Downloads")]
    existentes = {s.get("name") for s in SkillLoader(cfg).enabled()}
    importadas: list[str] = []

    def _marca_path() -> Path:
        return SkillLoader(cfg).user_dir / ".autoscan-zips.json"

    def _zips_processados() -> dict:
        try:
            import json as _json
            dados = _json.loads(_marca_path().read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    for pasta in pastas:
        d = Path(str(pasta)).expanduser()
        if not d.is_dir():
            continue
        for sd in find_skill_dirs(d):
            try:
                meta, _ = parse_skill_md(
                    (sd / "SKILL.md").read_text(encoding="utf-8",
                                                errors="replace"))
            except OSError:
                continue
            nome = _slug(meta.get("name"), sd.name)
            if nome in existentes:
                continue
            r = import_skill_dir(sd, cfg)
            if r.get("ok"):
                importadas.append(r["name"])
                existentes.add(r["name"])
        # v3.15.0: zip baixado do GitHub também é fonte — extrai, importa
        # e marca (mesmo nome+size não é reprocessado nos scans seguintes)
        marcados = _zips_processados()
        mudou = False
        for zp in sorted(d.glob("*.zip"))[:20]:
            try:
                chave = f"{zp.name}:{zp.stat().st_size}"
            except OSError:
                continue
            if marcados.get(str(zp)) == chave:
                continue
            with tempfile.TemporaryDirectory(prefix="betterme-zip-") as td:
                try:
                    with zipfile.ZipFile(zp) as zf:
                        for nome in zf.namelist():
                            if ".." in nome.split("/"):
                                raise RuntimeError("caminho inválido")
                        zf.extractall(td)
                except (zipfile.BadZipFile, RuntimeError, OSError):
                    continue
                for sd in find_skill_dirs(Path(td)):
                    r = import_skill_dir(sd, cfg)
                    if r.get("ok") and r["name"] not in existentes:
                        importadas.append(r["name"])
                        existentes.add(r["name"])
            marcados[str(zp)] = chave
            mudou = True
        if mudou:
            try:
                import json as _json
                mp = _marca_path()
                tmp = mp.with_suffix(".json.tmp")
                tmp.write_text(_json.dumps(marcados), encoding="utf-8")
                tmp.replace(mp)
            except OSError:
                pass
    if importadas:
        try:
            from . import activity
            activity.log(cfg, "skills",
                         f"✦ {len(importadas)} skill(s) baixada(s) pelo "
                         f"operador e importada(s): {', '.join(importadas)}")
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "importadas": importadas}


def parse_skill_md(text: str) -> tuple[dict, str]:
    """Separa frontmatter YAML do corpo Markdown."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    return meta, m.group(2)


class SkillLoader:
    def __init__(self, cfg):
        self.cfg = cfg

    # ------------------------------------------------------------ diretórios
    @property
    def dirs(self) -> list[tuple[Path, str]]:
        return [
            (PROJECT_ROOT / "skills", "builtin"),
            (self.cfg.data_dir / "skills", "usuario"),
        ]

    @property
    def user_dir(self) -> Path:
        d = self.cfg.data_dir / "skills"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------------------------------------------------------------- scan
    def scan(self) -> list[dict]:
        key = tuple((str(p), s) for p, s in self.dirs)
        now = time.time()
        cached = _CACHE.get(key)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]

        disabled = set(self.cfg.skills_disabled or [])
        found: list[dict] = []
        seen: set[str] = set()
        for base, source in self.dirs:
            if not base.is_dir():
                continue
            for skill_md in sorted(base.glob("*/SKILL.md")):
                folder = skill_md.parent
                try:
                    meta, _body = parse_skill_md(skill_md.read_text(encoding="utf-8"))
                except Exception:  # arquivo ilegível: ignora sem derrubar nada
                    meta = {}
                name = str(meta.get("name") or folder.name).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                found.append(
                    {
                        "name": name,
                        "description": str(meta.get("description", "")).strip(),
                        "dir": str(folder),
                        "skill_md": str(skill_md),
                        "source": source,
                        "enabled": name not in disabled,
                    }
                )
        _CACHE[key] = (now, found)
        return found

    def enabled(self) -> list[dict]:
        return [s for s in self.scan() if s["enabled"]]

    # ------------------------------------------------------- prompt / leitura
    def catalog(self, query: str | None = None) -> str:
        skills = self.enabled()
        if not skills:
            return ""
        lines = [
            "Habilidades (skills) instaladas — quando a tarefa combinar com uma skill, "
            "PRIMEIRO leia o SKILL.md dela com a ferramenta read_file e siga as instruções:",
        ]
        # v3.15.0 (PR#2): seção ORÇADA — o catálogo cresce (39+ skills)
        # sem inflar o prompt: até 18 linhas, priorizando as relevantes
        # ao pedido; o rodapé aponta o diretório para listar as demais.
        import re as _re
        palavras = {w for w in _re.findall(r"[a-zà-ú]{4,}", (query or "").lower())}

        def _sc(s: dict) -> int:
            alvo = (str(s.get("name", "")) + " "
                    + str(s.get("description", ""))).lower()
            return sum(1 for w in palavras if w in alvo)

        relevantes = sorted((s for s in skills if _sc(s) > 0),
                            key=lambda s: -_sc(s))[:18]
        restantes = [s for s in skills if _sc(s) == 0]
        escolhidas = relevantes + restantes[:max(0, 18 - len(relevantes))]
        for s in escolhidas:
            # v3.13: índice enxuto — o catálogo é só PARA SABER QUE
            # EXISTE (o casamento por gatilhos usa a descrição completa
            # à parte). 60 chars bastam e o prompt fica leve.
            desc = (s["description"] or "(sem descrição)").split(".")[0][:60].rstrip()
            lines.append(f"- {s['name']}: {desc} — ler: {s['skill_md']}")
        outras = len(skills) - len(escolhidas)
        if outras > 0:
            lines.append(f"(+{outras} outras skills — catálogo completo: "
                         f"list_dir {self.dirs[0][0]})")
        return "\n".join(lines)

    def read_skill_md(self, path: str) -> str:
        """Lê um SKILL.md validando que está dentro dos diretórios de skills."""
        p = Path(path).resolve()
        if not any(str(p).startswith(str(base.resolve()) + "/") or p == base.resolve()
                   for base, _ in self.dirs):
            raise PermissionError("caminho fora dos diretórios de skills")
        if p.name != "SKILL.md" or not p.is_file():
            raise FileNotFoundError("arquivo SKILL.md não encontrado")
        return p.read_text(encoding="utf-8")

    # ------------------------------------------------------------- alternar
    def toggle(self, name: str, enabled: bool) -> None:
        disabled = list(self.cfg.skills_disabled or [])
        if enabled and name in disabled:
            disabled.remove(name)
        elif not enabled and name not in disabled:
            disabled.append(name)
        self.cfg.update({"skills_disabled": disabled})

    # -------------------------------------------------- instalar do GitHub
    def install_from_github(self, repo: str, subpath: str = "") -> dict:
        """Baixa skills de um repositório GitHub (tarball do codeload).

        Aceita 'owner/repo' ou URLs https://github.com/owner/repo[/tree/ref/sub].
        Procura pastas com SKILL.md (no subpath, se informado) e copia para o
        diretório de skills do usuário.
        """
        repo = (repo or "").strip().strip("/")
        ref = ""
        if repo.startswith(_GITHUB_HOSTS):
            repo = repo.split("github.com/", 1)[1]
        parts = [p for p in repo.split("/") if p]
        if len(parts) >= 4 and parts[2] in ("tree", "blob"):
            # owner/repo/tree/REF/...(subpath)
            ref = parts[3]
            subpath = "/".join(parts[4:]) or subpath
            parts = parts[:2]
        if len(parts) != 2 or not all(_REPO_RE.fullmatch(f"{parts[0]}/{parts[1]}") for _ in [0]):
            return {"ok": False, "msg": "repositório inválido — use owner/repo ou a URL do GitHub"}
        owner, name = parts
        sub = "/".join(p for p in (subpath or "").strip("/").split("/") if p)

        last_err = ""
        for candidate_ref in filter(None, [ref, "main", "master"]):
            for kind in ("heads", "tags"):
                url = f"https://codeload.github.com/{owner}/{name}/tar.gz/refs/{kind}/{candidate_ref}"
                try:
                    r = requests.get(url, timeout=90, stream=True)
                    if r.status_code != 200:
                        last_err = f"HTTP {r.status_code} em {candidate_ref}"
                        continue
                    buf = io.BytesIO()
                    total = 0
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        total += len(chunk)
                        if total > 60 * 1024 * 1024:
                            return {"ok": False, "msg": "tarball grande demais (>60 MB)"}
                        buf.write(chunk)
                    buf.seek(0)
                    return self._extract_skills(buf, owner, name, sub)
                except requests.RequestException as exc:
                    last_err = str(exc)[:200]
        return {"ok": False, "msg": f"não consegui baixar {owner}/{name}: {last_err or 'repo não encontrado'}"}

    def _extract_skills(self, buf: io.BytesIO, owner: str, repo: str, sub: str) -> dict:
        installed: list[str] = []
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            members = [m for m in tar.getmembers() if m.isfile()]
            # normaliza: remove o prefixo "repo-ref/" do GitHub
            def norm(mpath: str) -> str:
                return mpath.split("/", 1)[1] if "/" in mpath else mpath

            skills_members: dict[str, list] = {}
            for m in members:
                n = norm(m.name)
                if n.endswith("/SKILL.md") or n == "SKILL.md":
                    skills_members[n[: -len("SKILL.md")].rstrip("/")] = []
            if not skills_members:
                return {"ok": False, "msg": "nenhum SKILL.md encontrado nesse repositório"}

            # filtra por subpath, se dado
            if sub:
                sub_n = sub.strip("/")
                skills_members = {
                    d: [] for d in skills_members
                    if d == sub_n or d.startswith(sub_n + "/")
                }
                if not skills_members:
                    return {"ok": False, "msg": f"nenhum SKILL.md em '{sub}' nesse repositório"}

            # mapeia arquivos para cada pasta de skill
            for m in members:
                n = norm(m.name)
                for d in skills_members:
                    if (n.startswith(d + "/") and "/.git/" not in n
                            and m.size <= 3 * 1024 * 1024):
                        skills_members[d].append((n, m))

            for d, files in list(skills_members.items())[:12]:
                skill_name = d.split("/")[-1] or f"{owner}-{repo}"
                dest = self.user_dir / skill_name
                if dest.exists():
                    continue  # não sobrescreve skill existente
                total = 0
                for n, m in files:
                    total += m.size
                    if total > 30 * 1024 * 1024:
                        break
                    rel = n[len(d) + 1:] if d else n
                    if not rel or ".." in rel.split("/"):
                        continue
                    out = dest / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    f = tar.extractfile(m)
                    if f:
                        out.write_bytes(f.read())
                installed.append(skill_name)

        if installed:
            _CACHE.clear()   # v3.15.0: skill instalada é nativa NA HORA
        if not installed:
            return {"ok": False, "msg": "nenhuma skill nova para instalar (já existentes?)"}
        return {"ok": True, "msg": f"{len(installed)} skill(s) instalada(s): {', '.join(installed)}",
                "installed": installed}
