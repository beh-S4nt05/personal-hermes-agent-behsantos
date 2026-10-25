"""Auditoria automática do catálogo de skills (v3.11 — `betterme skills audit`).

Checa por skill: SKILL.md existe · frontmatter com name/description ·
name confere com a pasta · description com texto suficiente para o
casamento de gatilhos · tamanho dentro do orçamento de prompt · padrões
de prompt injection · duplicatas de nome entre diretórios.

Saída: relatório por skill (✔ ok / ⚠ aviso / ✖ erro) + código de saída
(0 = catálogo limpo, 1 = tem erro). Avisos não falham.
"""
from __future__ import annotations

import re
from pathlib import Path

MAX_BYTES = 8192   # orçamento de prompt por skill
MIN_DESC = 30      # abaixo disso o casamento de gatilhos fica fraco

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)

# (padrão, mensagem) — o que uma skill NUNCA deve pedir ao agente
_INJECTION: list[tuple[str, str]] = [
    (r"\bignore\w*\s+(?:todas\s+as\s+)?instru[çc][õo]es\s+"
     r"(?:anteriores|acima|do\s+sistema|pr[ée]vias)",
     "pede para ignorar as instruções do sistema"),
    (r"\b(?:mostre|revele|envie|exponha|liste|transmita|poste)\b[^.\n]{0,80}"
     r"\b(?:chave|token|senha|api[_ ]?key|secret|credencial|\.env|id_rsa)\b",
     "pede para expor segredos ou credenciais"),
    (r"\b(?:envie|mande|poste)\b[^.\n]{0,60}"
     r"\b(?:discord|telegram|webhook|pastebin)\b",
     "possível exfiltração para serviço externo"),
    (r"\bcurl\b[^|\n]{0,140}\|\s*(?:ba)?sh\b",
     "curl canalizado direto para shell"),
    (r"\bwget\b[^|\n]{0,140}\|\s*(?:ba)?sh\b",
     "wget canalizado direto para shell"),
    (r"\bbase64\s+(?:-d|--decode)\b[^|\n]{0,80}\|\s*(?:ba)?sh\b",
     "decodifica base64 e executa"),
    (r"\bdesativ\w+\s+(?:o\s+)?(?:revisor|orquestrador|guarda|filtro)\b",
     "pede para desativar o revisor/guarda"),
]

# negação antes do comando = ensinando a NÃO fazer (ex.: criar-skill)
_NEGACAO = re.compile(r"\b(?:nunca|não|jamais|never)\b[^.\n]{0,40}$",
                      re.IGNORECASE)


def _frontmatter(texto: str) -> tuple[dict, str]:
    """Separa frontmatter simples (chave: valor) do corpo Markdown."""
    m = _FRONT.match(texto)
    if not m:
        return {}, texto
    meta: dict = {}
    for linha in m.group(1).splitlines():
        if ":" in linha:
            k, _, v = linha.partition(":")
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def audit_skill(pasta: Path) -> dict:
    """Audita uma pasta de skill → {name, nivel, problemas[]}."""
    nome = pasta.name
    rel = {"name": nome, "nivel": "ok", "problemas": []}
    arq = pasta / "SKILL.md"
    if not arq.is_file():
        rel["nivel"] = "erro"
        rel["problemas"].append("SKILL.md não encontrado")
        return rel
    try:
        texto = arq.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        rel["nivel"] = "erro"
        rel["problemas"].append(f"SKILL.md ilegível: {exc}")
        return rel
    meta, _corpo = _frontmatter(texto)
    nm = str(meta.get("name") or "").strip()
    rel["fm_name"] = nm                   # p/ detectar duplicatas reais
    desc = str(meta.get("description") or "").strip()
    if not nm:
        rel["problemas"].append("frontmatter sem 'name'")
    elif nm != nome:
        rel["problemas"].append(f"name '{nm}' difere da pasta '{nome}'")
    if not desc:
        rel["problemas"].append("frontmatter sem 'description' (skill nunca casa)")
    elif len(desc) < MIN_DESC:
        rel["problemas"].append(
            f"description curta ({len(desc)} < {MIN_DESC} chars) — gatilhos ficam fracos")
    tam = len(texto.encode("utf-8"))
    if tam > MAX_BYTES:
        rel["problemas"].append(f"SKILL.md grande ({tam} B > {MAX_BYTES} B)")
    for padrao, msg in _INJECTION:
        for m in re.finditer(padrao, texto, re.IGNORECASE):
            if _NEGACAO.search(texto[:m.start()]):
                continue          # "nunca … ignore instruções" = ensinando bem
            rel["problemas"].append(f"injeção: {msg}")
            break
    # nível: erro = injeção/estrutura quebrada/duplicata
    #        aviso = funciona, mas com ressalva (tamanho, description curta)
    def _eErro(p: str) -> bool:
        return (p.startswith(("injeção", "frontmatter", "SKILL.md não",
                              "SKILL.md ilegível", "name "))
                or "duplicado" in p)
    if any(_eErro(p) for p in rel["problemas"]):
        rel["nivel"] = "erro"
    elif rel["problemas"]:
        rel["nivel"] = "aviso"
    return rel


def audit_skills(dirs) -> list[dict]:
    """Audita todos os diretórios de skills + duplicatas de nome."""
    rels: list[dict] = []
    vistos: dict[str, str] = {}
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for pasta in sorted(p for p in d.iterdir() if p.is_dir()):
            rel = audit_skill(pasta)
            fm = rel.pop("fm_name", "") or ""
            if fm:                          # duplicata = mesmo name declarado
                outro = vistos.get(fm)
                if outro:
                    rel["problemas"].append(f"name duplicado com {outro}")
                    rel["nivel"] = "erro"
                else:
                    vistos[fm] = str(pasta)
            rels.append(rel)
    return rels


def run_audit(cfg, print_fn=print) -> int:
    """Roda a auditoria no catálogo configurado; devolve exit code."""
    rels = audit_skills(cfg.skills_dirs)
    if not rels:
        print_fn("nenhuma skill encontrada nos diretórios configurados.")
        return 0
    erros = avisos = 0
    for r in rels:
        icon = "✔" if r["nivel"] == "ok" else ("⚠" if r["nivel"] == "aviso" else "✖")
        print_fn(f"  {icon} {r['name']}")
        for prob in r["problemas"]:
            print_fn(f"      {prob}")
        erros += r["nivel"] == "erro"
        avisos += r["nivel"] == "aviso"
    print_fn(f"\n{len(rels)} skills · {erros} erro(s) · {avisos} aviso(s)")
    if erros:
        print_fn("✖ catálogo COM problemas — corrija antes de confiar.")
        return 1
    print_fn("✔ catálogo limpo.")
    return 0
