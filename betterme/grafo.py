# -*- coding: utf-8 -*-
"""🗺️ Grafo de código — v4.4.0 (PR #7, E3).

"Onde está a lógica de X?" em milissegundos, ZERO tokens.

- AST Python PURO (stdlib `ast`) — nenhum código é executado ou sai da
  máquina; o grafo vive em SQLite no data-dir (`grafo.db`).
- Símbolos: funções, classes e métodos (qualificados `modulo.Classe.metodo`)
  com `arquivo:linha` e a primeira linha da docstring.
- Arestas COM PROVENIÊNCIA (estilo Graphify): toda aresta carrega o
  `arquivo:linha` de onde foi EXTRAÍDA — `chama` (linha do call),
  `importa` (linha do import), `herda` (linha do class).
- `build|query|path` via CLI (`betterme grafo ...`) e a ferramenta
  `grafo_query` no cérebro — o modelo pergunta ao grafo em vez de ler
  arquivos às cegas.

Determinístico: mesma árvore → mesmos símbolos e arestas (ordenados);
o build pula .venv/.git/__pycache__/node_modules etc. e NUNCA executa
nada do projeto — só `ast.parse`.
"""
from __future__ import annotations

import ast
import sqlite3
import time
from pathlib import Path
from .contratos import acao_de

# pastas que nunca entram no grafo (dependências, caches, builds)
_PULAR_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".nox", "build", "dist",
    "out", "target", "coverage", ".cache", ".arena", ".next", ".nuxt",
    ".output", ".parcel-cache", ".svelte-kit",
}


def db_path(cfg) -> Path:
    return cfg.data_dir / "grafo.db"


# ------------------------------------------------------------ extração
def _dotted(node) -> str:
    """Nome pontilhado de uma expressão (json.dumps, self.run, foo)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _modulo_de(caminho_rel: str) -> str:
    """'betterme/server/app.py' → 'betterme.server.app';
    '__init__.py' vira o nome do pacote."""
    m = caminho_rel[:-3].replace("/", ".").replace("\\", ".")
    if m.endswith(".__init__"):
        m = m[:-9]
    return m or caminho_rel


def _varrer(caminho_rel: str, tree, simbolos: list, arestas: list) -> None:
    modulo = _modulo_de(caminho_rel)

    def doc_primeira(node) -> str:
        doc = ast.get_docstring(node) or ""
        return doc.strip().splitlines()[0][:120] if doc.strip() else ""

    def coletar_chamadas(node, origem: str) -> None:
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                d = _dotted(n.func)
                if d:
                    arestas.append(("chama", origem, d, caminho_rel,
                                    n.lineno))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            q = f"{modulo}.{node.name}"
            simbolos.append(("funcao", node.name, q, caminho_rel,
                             node.lineno, node.end_lineno or node.lineno,
                             doc_primeira(node)))
            coletar_chamadas(node, q)
        elif isinstance(node, ast.ClassDef):
            q = f"{modulo}.{node.name}"
            simbolos.append(("classe", node.name, q, caminho_rel,
                             node.lineno, node.end_lineno or node.lineno,
                             doc_primeira(node)))
            for base in node.bases:
                d = _dotted(base)
                if d:
                    arestas.append(("herda", q, d, caminho_rel, node.lineno))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qm = f"{q}.{sub.name}"
                    simbolos.append(("metodo", sub.name, qm, caminho_rel,
                                     sub.lineno, sub.end_lineno or sub.lineno,
                                     doc_primeira(sub)))
                    coletar_chamadas(sub, qm)
    # imports (inclusive dentro de funções — origem = módulo)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                arestas.append(("importa", modulo, a.name, caminho_rel,
                                n.lineno))
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                arestas.append(("importa", modulo, f"{n.module}.{a.name}",
                                caminho_rel, n.lineno))


def _arquivos_py(raiz: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(raiz.rglob("*.py")):
        partes = set(p.relative_to(raiz).parts)
        if partes & _PULAR_DIRS:
            continue
        if any(part.endswith(".egg-info") for part in p.relative_to(raiz).parts):
            continue
        out.append(p)
    return out


# ------------------------------------------------------------ build
def build(cfg, raiz: Path | None = None) -> dict:
    """Constrói o grafo AST da árvore em SQLite no data-dir.
    Nada é executado — só `ast.parse`. Devolve stats auditáveis."""
    raiz = Path(raiz or Path.cwd()).resolve()
    simbolos: list[tuple] = []
    arestas: list[tuple] = []
    avisos: list[str] = []
    arquivos = _arquivos_py(raiz)
    for p in arquivos:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"),
                             filename=str(p))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            avisos.append(f"{p.relative_to(raiz).as_posix()}: {exc}")
            continue
        _varrer(p.relative_to(raiz).as_posix(), tree, simbolos, arestas)
    # determinismo: mesma árvore → mesmas linhas, mesma ordem
    simbolos.sort(key=lambda s: (s[3], s[4], s[2]))
    arestas.sort(key=lambda a: (a[3], a[4], a[0], a[1], a[2]))
    db = db_path(cfg)
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)                      # rebuild = recomeça
    con = sqlite3.connect(str(db))
    try:
        con.executescript(
            "CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);"
            "CREATE TABLE simbolos ("
            " tipo TEXT, nome TEXT, qualificado TEXT UNIQUE,"
            " arquivo TEXT, linha INTEGER, fim INTEGER, doc TEXT);"
            "CREATE TABLE arestas ("
            " tipo TEXT, origem TEXT, destino TEXT,"
            " arquivo TEXT, linha INTEGER);")
        con.executemany("INSERT INTO simbolos VALUES (?,?,?,?,?,?,?)",
                        simbolos)
        con.executemany("INSERT INTO arestas VALUES (?,?,?,?,?)", arestas)
        con.executemany("INSERT INTO meta VALUES (?,?)", [
            ("raiz", str(raiz)), ("versao", "v4.4.0"),
            ("gerado_em", time.strftime("%Y-%m-%d %H:%M:%S")),
            ("arquivos", str(len(arquivos))),
            ("simbolos", str(len(simbolos))),
            ("arestas", str(len(arestas))),
        ])
        con.commit()
    finally:
        con.close()
    try:
        from . import activity
        activity.log(cfg, "grafo",
                     f"🗺 build: {len(arquivos)} arquivos · "
                     f"{len(simbolos)} símbolos · {len(arestas)} arestas"
                     f" · raiz {raiz}")
    except Exception:  # noqa: BLE001
        pass
    return {"arquivos": len(arquivos), "simbolos": len(simbolos),
            "arestas": len(arestas), "avisos": avisos, "raiz": str(raiz)}


def _abrir(cfg):
    db = db_path(cfg)
    if not db.exists():
        return None
    return sqlite3.connect(str(db))


# ------------------------------------------------------------ query
def query(cfg, termo: str) -> dict:
    """Busca símbolos por nome (substring, case-insensitive)."""
    termo = (termo or "").strip()
    if not termo:
        return {"ok": False, "msg": "termo vazio"}
    con = _abrir(cfg)
    if con is None:
        return {"ok": False, "msg": _sem_grafo()}
    try:
        linhas = con.execute(
            "SELECT tipo, qualificado, arquivo, linha, doc, "
            "(SELECT COUNT(*) FROM arestas a WHERE a.tipo='chama' "
            " AND a.origem=s.qualificado) AS faz "
            "FROM simbolos s "
            "WHERE LOWER(s.nome) LIKE ? OR LOWER(s.qualificado) LIKE ? "
            "ORDER BY s.arquivo, s.linha LIMIT 40",
            (f"%{termo.lower()}%", f"%{termo.lower()}%")).fetchall()
        stats = dict(con.execute(
            "SELECT chave, valor FROM meta").fetchall())
    finally:
        con.close()
    return {"ok": True, "termo": termo, "simbolos": [
        {"tipo": t, "qualificado": q, "arquivo": a, "linha": l,
         "doc": d, "faz": faz} for t, q, a, l, d, faz in linhas],
        "stats": stats}


def _sem_grafo() -> str:
    return ("nenhum grafo construído — rode `betterme grafo build` na "
            "raiz do projeto (AST local, zero tokens, nada é executado)")


def query_text(cfg, termo: str) -> str:
    r = query(cfg, termo)
    if not r.get("ok"):
        return f"ERRO: {r['msg']}"
    sims = r["simbolos"]
    if not sims:
        return (f"🗺 nenhum símbolo casa com {termo!r} "
                f"(grafo: {r['stats'].get('simbolos', '?')} símbolos)")
    partes = [f"🗺 {len(sims)} símbolo(s) para {termo!r} "
              f"(grafo de {r['stats'].get('arquivos', '?')} arquivos):"]
    for s in sims:
        doc = f" — {s['doc']}" if s["doc"] else ""
        partes.append(f"  {s['tipo']:<7} {s['qualificado']}"
                      f"  📍{s['arquivo']}:{s['linha']}"
                      f"  ({s['faz']} chamada(s)){doc}")
    return "\n".join(partes)


# ------------------------------------------------------------ path A→B
def _resolver(con, nome: str) -> list[str]:
    """Símbolos que casam com o nome: qualificado exato, sufixo ou nome
    curto — ordenados (determinístico)."""
    return [r[0] for r in con.execute(
        "SELECT qualificado FROM simbolos "
        "WHERE qualificado = ? OR qualificado LIKE ? OR nome = ? "
        "ORDER BY qualificado",
        (nome, f"%.{nome}", nome)).fetchall()]


def path(cfg, de: str, para: str) -> dict:
    """Caminho de chamadas A→B (BFS sobre arestas 'chama'; destino
    resolvido pelo último segmento do nome, como escrito no código)."""
    de, para = (de or "").strip(), (para or "").strip()
    if not de or not para:
        return {"ok": False, "msg": "informe 'de' e 'para'"}
    con = _abrir(cfg)
    if con is None:
        return {"ok": False, "msg": _sem_grafo()}
    try:
        origens = _resolver(con, de)
        if not origens:
            return {"ok": False, "msg": f"não achei {de!r} no grafo"}
        destinos = set(_resolver(con, para))
        if not destinos:
            return {"ok": False, "msg": f"não achei {para!r} no grafo"}
        if len(origens) > 1:
            return {"ok": False,
                    "msg": f"{de!r} é ambíguo: {', '.join(origens[:6])}"}
        # índice nome-curto → qualificados (resolução das arestas)
        idx: dict[str, list[str]] = {}
        for (q,) in con.execute(
                "SELECT qualificado FROM simbolos"):
            idx.setdefault(q.rsplit(".", 1)[-1], []).append(q)
        arestas = con.execute(
            "SELECT origem, destino, arquivo, linha FROM arestas "
            "WHERE tipo='chama' ORDER BY arquivo, linha, origem, destino"
        ).fetchall()
        adj: dict[str, list[tuple[str, str, int]]] = {}
        for o, d, a, l in arestas:
            for alvo in idx.get(d.rsplit(".", 1)[-1], []):
                adj.setdefault(o, []).append((alvo, a, l))
        # BFS
        inicio = origens[0]
        fila = [(inicio, [])]
        visitados = {inicio}
        while fila:
            atual, caminho_perc = fila.pop(0)
            if atual in destinos:
                return {"ok": True, "de": inicio, "para": atual,
                        "passos": caminho_perc}
            for alvo, a, l in adj.get(atual, []):
                if alvo not in visitados:
                    visitados.add(alvo)
                    fila.append((alvo, caminho_perc + [(atual, alvo, a, l)]))
        return {"ok": True, "de": inicio, "para": None, "passos": []}
    finally:
        con.close()


def path_text(cfg, de: str, para: str) -> str:
    r = path(cfg, de, para)
    if not r.get("ok"):
        return f"ERRO: {r['msg']}"
    if r["para"] is None:
        return (f"🗺 sem caminho de chamadas {r['de']!r} até {para!r} "
                "no grafo (chamadas diretas de A, BFS)")
    passos = r["passos"]
    if not passos:
        return f"🗺 {r['de']} já É {r['para']}"
    linhas = [f"🗺 caminho {r['de']} → {r['para']} "
              f"({len(passos)} chamada(s)):"]
    for o, d, a, l in passos:
        linhas.append(f"  {o} → {d}   📍{a}:{l}")
    return "\n".join(linhas)


# ------------------------------------------------------------ CLI
def cmd(args, cfg) -> None:
    """`betterme grafo build|query|path`."""
    acao = acao_de(args, "build")
    if acao == "build":
        raiz = getattr(args, "raiz", None) or Path.cwd()
        st = build(cfg, Path(raiz))
        print(f"🗺 grafo construído: {st['arquivos']} arquivos · "
              f"{st['simbolos']} símbolos · {st['arestas']} arestas")
        print(f"   raiz: {st['raiz']} · db: {db_path(cfg)}")
        if st["avisos"]:
            print(f"   ⚠ {len(st['avisos'])} arquivo(s) com erro de "
                  f"sintaxe ignorado(s); primeiro: {st['avisos'][0]}")
        return
    if acao == "query":
        termo = " ".join(getattr(args, "termo", []) or [])
        print(query_text(cfg, termo))
        return
    if acao == "path":
        print(path_text(cfg, getattr(args, "de", ""),
                        getattr(args, "para", "")))
        return
    print(f"✖ ação desconhecida: {acao!r} (build|query|path)")
    raise SystemExit(1)
