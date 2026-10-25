"""Backups automáticos: toda gravação de arquivo pelo agente salva a versão
anterior em <data_dir>/backups/ — nada é sobrescrito sem volta.

Estrutura: backups/YYYY-MM-DD/HHMMSS-<nome>  (+ sufixo .N se colidir)
Retenção: por arquivo original, mantém os N mais recentes (padrão 20).
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:120] or "arquivo"


def backup_file(cfg, path: Path) -> Path | None:
    """Copia `path` (se existir) para a área de backups; devolve o destino."""
    try:
        if not path or not path.is_file():
            return None
    except OSError:
        return None
    day = time.strftime("%Y-%m-%d")
    stamp = time.strftime("%H%M%S")
    dest_dir = cfg.data_dir / "backups" / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stamp}-{_safe_name(path.name)}"
    n = 1
    while dest.exists():
        dest = dest_dir / f"{stamp}-{_safe_name(path.name)}.{n}"
        n += 1
    try:
        shutil.copy2(path, dest)
    except OSError:
        return None
    _remember_origin(cfg, dest.relative_to(cfg.data_dir / "backups").as_posix(), path)
    prune(cfg, path)
    return dest


def _origin_key(path: Path) -> str:
    return str(path.resolve())


def list_backups(cfg, origin: str | None = None) -> list[dict]:
    """Backups disponíveis (mais recentes primeiro), opcionalmente de um arquivo."""
    root = cfg.data_dir / "backups"
    if not root.exists():
        return []
    origin = (origin or "").strip()
    key = _origin_key(Path(origin).expanduser()) if origin else ""
    out = []
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir() or day_dir.name.startswith("."):
            continue  # .origins é metadado interno, não é backup
        for f in sorted(day_dir.iterdir(), reverse=True):
            if not f.is_file():
                continue
            info = {
                "id": f.relative_to(root).as_posix(),
                "name": f.name,
                "day": day_dir.name,
                "size": f.stat().st_size if f.exists() else 0,
                "ts": f.stat().st_mtime if f.exists() else 0,
                "origin": "",
            }
            # o lado <data>/backups/.origins/<id> guarda de onde veio o backup
            origin_file = root / ".origins" / (info["id"].replace("/", "__") + ".txt")
            if origin_file.exists():
                try:
                    info["origin"] = origin_file.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
            if key and info["origin"] != key:
                continue
            out.append(info)
    return out


def _remember_origin(cfg, backup_rel_id: str, origin: Path) -> None:
    odir = cfg.data_dir / "backups" / ".origins"
    odir.mkdir(parents=True, exist_ok=True)
    (odir / (backup_rel_id.replace("/", "__") + ".txt")).write_text(
        _origin_key(origin), encoding="utf-8")


def restore(cfg, backup_id: str) -> dict:
    """Devolve o backup `id` ao arquivo de origem (sobrescreve o atual)."""
    root = cfg.data_dir / "backups"
    try:
        src = (root / backup_id).resolve()
        src.relative_to(root.resolve())  # segue dentro da área de backups
    except (ValueError, OSError):
        return {"ok": False, "msg": "backup inválido"}
    if not src.is_file():
        return {"ok": False, "msg": "backup não encontrado"}
    origin_file = root / ".origins" / (backup_id.replace("/", "__") + ".txt")
    if not origin_file.exists():
        return {"ok": False, "msg": "origem do backup desconhecida"}
    origin = Path(origin_file.read_text(encoding="utf-8").strip())
    # segurança: restaura apenas dentro do workdir (ou caminhos já permitidos)
    try:
        origin.resolve().relative_to(cfg.workdir.resolve())
    except ValueError:
        if getattr(cfg, "sandbox", True):
            return {"ok": False, "msg": f"fora do workspace: {origin}"}
    try:
        # o atual também é preservado antes de ser sobrescrito
        if origin.is_file():
            backup_file(cfg, origin)
        origin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, origin)
    except OSError as exc:
        return {"ok": False, "msg": f"falha ao restaurar: {exc}"}
    return {"ok": True, "msg": f"restaurado: {origin}", "path": str(origin)}


def prune(cfg, origin: Path, keep: int | None = None) -> int:
    """Mantém apenas os N backups mais recentes de `origin`; devolve os apagados."""
    keep = keep if keep is not None else int(getattr(cfg, "backups_keep", 20) or 20)
    key = _origin_key(origin)
    mine = [b for b in list_backups(cfg, str(origin)) if b["origin"] == key]
    removed = 0
    for b in mine[keep:]:
        try:
            (cfg.data_dir / "backups" / b["id"]).unlink(missing_ok=True)
            (cfg.data_dir / "backups" / ".origins" / (b["id"].replace("/", "__") + ".txt")).unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed


# ferramenta exposta ao agente: listar/restaurar pelo próprio chat
def tool_backups(args: dict, cfg) -> str:
    act = str(args.get("action") or "list")
    if act == "list":
        items = list_backups(cfg, str(args.get("path") or "") or None)[:30]
        if not items:
            return "Nenhum backup disponível ainda."
        return "\n".join(
            f"- {b['id']} → {b['origin'] or '?'} ({b['size']} bytes)" for b in items)
    if act == "restore":
        res = restore(cfg, str(args.get("id") or ""))
        return ("OK: " + res["msg"]) if res["ok"] else "ERRO: " + res["msg"]
    return "ERRO: use action=list ou action=restore (id=...)."
