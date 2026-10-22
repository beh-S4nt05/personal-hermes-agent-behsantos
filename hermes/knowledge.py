# -*- coding: utf-8 -*-
"""Biblioteca local do operador — RAG determinístico (PR#2, v3.15.0).

Os livros/documentos do operador vivem em `~/.hermes/biblioteca/`
(.md/.txt; .pdf se `pdftotext` estiver instalado). São fatiados em
blocos e indexados por TF-IDF (stdlib pura — sem embeddings, sem GPU,
sem sorte: a mesma consulta sempre devolve o mesmo trecho, citando a
fonte). O agente consulta via ferramenta `knowledge_search`; novos
livros são (re)indexados com `hermes rag`.

Anti-alucinação por construção: o que entra no contexto é TRECHO
VERBATIM do livro, com a fonte — nunca paráfrase do modelo.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

_CHUNK = 1200        # caracteres por bloco
_OVERLAP = 180       # sobreposição entre blocos
_WORD = re.compile(r"[a-zà-ú0-9]{3,}")


def biblioteca_dir(cfg) -> Path:
    d = Path(cfg.data_dir) / "biblioteca"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _arquivos(cfg) -> list[Path]:
    d = biblioteca_dir(cfg)
    out = []
    for ext in ("*.md", "*.txt", "*.pdf"):
        out.extend(sorted(d.rglob(ext)))
    return out


def _ler(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        exe = shutil.which("pdftotext")
        if not exe:
            return ""
        try:
            r = subprocess.run([exe, "-layout", str(path), "-"],
                               capture_output=True, text=True, timeout=60,
                               check=False)
            return r.stdout or ""
        except Exception:  # noqa: BLE001
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _fatiar(texto: str) -> list[str]:
    """Blocos de até _CHUNK chars cortando em quebra de linha próxima."""
    blocos, ini = [], 0
    while ini < len(texto):
        fim = min(ini + _CHUNK, len(texto))
        if fim < len(texto):
            corte = texto.rfind("\n", ini, fim)
            if corte > ini + _CHUNK // 2:
                fim = corte
        bloco = texto[ini:fim].strip()
        if bloco:
            blocos.append(bloco)
        if fim >= len(texto):
            break
        ini = max(fim - _OVERLAP, ini + 1)
    return blocos[:400]            # teto por livro (índice enxuto)


def _tokens(texto: str) -> list[str]:
    return _WORD.findall(texto.lower())


def indexar(cfg) -> dict:
    """(Re)indexa a biblioteca; devolve estatísticas."""
    dest = biblioteca_dir(cfg) / "indice.json"
    indice: dict = {"gerado_em": time.strftime("%Y-%m-%d %H:%M"),
                    "livros": {}}
    for arq in _arquivos(cfg):
        texto = _ler(arq)
        if not texto.strip():
            continue
        blocos = _fatiar(texto)
        indice["livros"][str(arq)] = {
            "blocos": [{"texto": b,
                        "n": len(indice["livros"]) , "i": i}
                       for i, b in enumerate(blocos)],
        }
    # renumera posições globais p/ citação estável
    pos = 0
    for livro in indice["livros"].values():
        for b in livro["blocos"]:
            b["pos"] = pos
            pos += 1
    indice["total_blocos"] = pos
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    tmp.replace(dest)              # atômico
    return {"livros": len(indice["livros"]), "blocos": pos,
            "tamanho": dest.stat().st_size if dest.exists() else 0}


def _carregar(cfg) -> dict:
    try:
        dados = json.loads((biblioteca_dir(cfg) / "indice.json")
                           .read_text(encoding="utf-8"))
        if isinstance(dados, dict) and "livros" in dados:
            return dados
    except (OSError, ValueError):
        pass
    return {"livros": {}, "total_blocos": 0}


def buscar(cfg, consulta: str, k: int = 3, max_chars: int = 1200) -> list[dict]:
    """Top-k blocos por TF-IDF; devolve [{texto, fonte, score}]."""
    indice = _carregar(cfg)
    blocos = [(arq, b) for arq, livro in indice["livros"].items()
              for b in livro["blocos"]]
    if not blocos or not consulta.strip():
        return []
    q = set(_tokens(consulta))
    if not q:
        return []
    # document frequency por termo
    df: dict[str, int] = {}
    tok_cache = []
    for _, b in blocos:
        toks = set(_tokens(b["texto"]))
        tok_cache.append(toks)
        for t in toks:
            df[t] = df.get(t, 0) + 1
    n = len(blocos)
    resultados = []
    for (arq, b), toks in zip(blocos, tok_cache):
        if not (q & toks):
            continue
        score = sum(math.log(1 + n / df[t]) for t in q if t in toks)
        if score <= 0:
            continue
        resultados.append({"texto": b["texto"][:max_chars],
                           "fonte": f"{Path(arq).name} (trecho "
                                    f"#{b['pos'] + 1})",
                           "score": round(score, 3)})
    resultados.sort(key=lambda r: -r["score"])
    return resultados[:k]


def status(cfg) -> dict:
    indice = _carregar(cfg)
    return {"livros": len(indice.get("livros", {})),
            "blocos": int(indice.get("total_blocos", 0)),
            "arquivos": [Path(a).name for a in _arquivos(cfg)]}
