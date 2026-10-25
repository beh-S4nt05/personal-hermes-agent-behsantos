"""Loop de aprendizado — v4.0.0 (M6.5).

O agente fecha o ciclo (ideia do Hermes-Nous, formato Qwen, com a nossa
regra): missão complexa bem-sucedida → rascunho de SKILL; missão que
falhou → rascunho de LIÇÃO; documento útil → rascunho via
`hermes skills aprender`. Busca nas conversas passadas fecha a memória.

REGRA DURA (decisão do operador, 24/10/2026): o agente aprende em
DADOS (markdown/memória), JAMAIS em código; e NADA entra no catálogo
ou na memória sem aprovação EXPLÍCITA do operador — em qualquer nível
de autonomia. Rascunhos ficam em staging até serem aprovados.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_MIN_TOOLS_PRA_SKILL = 5          # mesma régua do Hermes da Nous


# ------------------------------------------------------------- staging
def _dir(cfg) -> Path:
    d = Path(cfg.data_dir) / "aprendizados"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(texto: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return (s[:40].strip("-") or "aprendido-" + str(int(time.time())))


def _novo_id() -> str:
    return "ap" + time.strftime("%Y%m%d%H%M%S") + \
        format(int(time.time() * 1000) % 1000, "03d")


def _salvar(cfg, entry: dict) -> dict:
    entry["id"] = _novo_id()
    entry["ts"] = time.time()
    (_dir(cfg) / f"{entry['id']}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


def pendentes(cfg) -> list[dict]:
    out = []
    for p in sorted(_dir(cfg).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


# ------------------------------------------------------------- rascunhos
def rascunho_skill(objetivo: str, relatorio: str, origem: str = "missao") \
        -> dict:
    """Template honesto: procedimento que funcionou, do relatório real."""
    nome = _slug(objetivo)
    gatilhos = " ".join(w for w in re.findall(r"[a-zà-ú]{4,}",
                                              objetivo.lower())[:8])
    corpo = (
        "---\n"
        f"name: {nome}\n"
        f"description: Procedimento aprendido em serviço — {gatilhos}. "
        "Use quando a tarefa combinar com estas palavras.\n"
        "---\n\n"
        f"# {nome} (aprendida em serviço)\n\n"
        "## Contexto de origem\n\n"
        f"Missão: {objetivo[:300]}\n\n"
        "## Procedimento que funcionou\n\n"
        "1. " + "\n1. ".join(
            lin.strip() for lin in relatorio.splitlines()
            if lin.strip() and not lin.startswith("#"))[:2400] + "\n"
    )
    return {"tipo": "skill", "alvo": nome, "titulo": objetivo[:80],
            "rascunho": corpo, "origem": origem, "objetivo": objetivo[:300]}


def rascunho_licao(objetivo: str, relatorio: str) -> dict:
    texto = (f"LIÇÃO (missão reprovada — {objetivo[:120]}): "
             + " ".join(relatorio.split())[:400])
    return {"tipo": "licao", "titulo": objetivo[:80], "rascunho": texto,
            "origem": "missao", "objetivo": objetivo[:300]}


def observar(cfg, objetivo: str, status: str, relatorio: str,
             n_tool_calls: int) -> str:
    """Chamado no fim do pipeline: decide se algo merece virar aprendizado
    e cria o RASCUNHO em staging (aprovação é sempre do operador)."""
    try:
        if status == "aprovada" and n_tool_calls >= _MIN_TOOLS_PRA_SKILL:
            e = _salvar(cfg, rascunho_skill(objetivo, relatorio))
            _nota(cfg, e)
            return (f"📚 {n_tool_calls} ferramentas usadas e missão "
                    f"aprovada — rascunho de skill proposto "
                    f"({e['alvo']}); revise: hermes aprendidos")
        if status == "reprovada":
            e = _salvar(cfg, rascunho_licao(objetivo, relatorio))
            _nota(cfg, e)
            return ("🧠 missão reprovada — lição extraída para revisão "
                    f"({e['id']}); revise: hermes aprendidos")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _nota(cfg, entry: dict) -> None:
    try:
        from . import activity
        activity.log(cfg, "aprendizado",
                     f"{entry['tipo']} proposta: {entry['titulo']}")
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------- aprovar
def aprovar(cfg, id_ap: str) -> tuple[bool, str]:
    """Aplica o aprendizado: skill → catálogo (com backup + auditoria);
    lição → memória. Devolve (ok, mensagem)."""
    p = _dir(cfg) / f"{id_ap}.json"
    if not p.is_file():
        return False, f"rascunho {id_ap!r} não encontrado"
    e = json.loads(p.read_text(encoding="utf-8"))
    if e["tipo"] in ("skill", "skill_patch"):
        # PRIVACIDADE/isolamento: skill aprendida vai para o skills do
        # DATA-DIR (privado), nunca para o skills/ do repo público —
        # skills_dirs[0] é o do projeto (bug pego pela suíte T137)
        destino_dir = Path(cfg.data_dir) / "skills" / e["alvo"]
        destino_dir.mkdir(parents=True, exist_ok=True)
        alvo = destino_dir / "SKILL.md"
        patch = alvo.exists()
        if patch:                        # preserva o anterior (reversível)
            antigo = destino_dir / "SKILL.md.antigo"
            antigo.write_text(alvo.read_text(encoding="utf-8"),
                              encoding="utf-8")
            e["tipo"] = "skill_patch"
        alvo.write_text(e["rascunho"], encoding="utf-8")
        # auditoria do catálogo inteiro DEPOIS de aplicar (trava 4)
        try:
            from .skills_audit import run_audit
            achados = run_audit(cfg, print_fn=lambda *_: None)
        except Exception:  # noqa: BLE001
            achados = 0
        p.unlink()
        verbo = ("ATUALIZADA (backup em SKILL.md.antigo)" if patch
                 else "instalada")
        msg = ("skill " + verbo + ": " + e["alvo"]
               + (f" — ⚠ auditoria com {achados} achado(s), revise!"
                  if achados else " — auditoria limpa"))
        return True, msg
    if e["tipo"] == "licao":
        try:
            from .memory import MemoryStore
            MemoryStore(cfg).add(e["rascunho"])
        except Exception as exc:  # noqa: BLE001
            return False, f"falha ao gravar na memória: {exc}"
        p.unlink()
        return True, "lição gravada na memória do agente"
    return False, f"tipo desconhecido: {e.get('tipo')!r}"


def rejeitar(cfg, id_ap: str) -> tuple[bool, str]:
    p = _dir(cfg) / f"{id_ap}.json"
    if not p.is_file():
        return False, f"rascunho {id_ap!r} não encontrado"
    p.unlink()
    return True, "rascunho descartado"


def cmd(args, cfg) -> None:
    """`hermes aprendidos` — lista/aprova/rejeita rascunhos."""
    acao = str(getattr(args, "acao", "") or "list").lower()
    alvo = str(getattr(args, "id", "") or "").strip()
    if acao == "list":
        ps = pendentes(cfg)
        if not ps:
            print("📚 nenhum aprendizado pendente — o agente propõe "
                  "skills/lições conforme trabalha.")
            return
        print(f"📚 aprendizados aguardando aprovação ({len(ps)}):\n")
        for e in ps:
            print(f"  [{e['id']}] {e['tipo']:<11} {e['titulo']}")
            print(f"      rascunho: {len(e.get('rascunho', ''))} chars · "
                  f"origem: {e.get('origem', '?')}")
        print("\n  aplique: hermes aprendidos aprovar <id> · "
              "descarte: hermes aprendidos rejeitar <id>")
        return
    if acao == "aprovar":
        ok, msg = aprovar(cfg, alvo)
        print(("✔ " if ok else "✖ ") + msg)
        if not ok:
            raise SystemExit(1)
        return
    if acao == "rejeitar":
        ok, msg = rejeitar(cfg, alvo)
        print(("✔ " if ok else "✖ ") + msg)
        if not ok:
            raise SystemExit(1)
        return
    print(f"✖ ação inválida: {acao!r} (use list|aprovar|rejeitar)")
    raise SystemExit(1)


# --------------------------------------------------- aprender de documento
def aprender_de_documento(cfg, fonte: str) -> tuple[bool, str]:
    """`hermes skills aprender <arquivo|url|texto>` — vira RASCUNHO de
    skill (staging + aprovação), como o /learn do Qwen Code."""
    texto = ""
    if re.match(r"^https?://", fonte):
        try:
            from .tools import web_fetch
            r = web_fetch({"url": fonte}, cfg)
            texto = r if "ERRO" not in r[:60] else ""
        except Exception:  # noqa: BLE001
            texto = ""
    elif Path(fonte).is_file():
        try:
            texto = Path(fonte).read_text(encoding="utf-8",
                                          errors="replace")
        except OSError:
            return False, f"não consegui ler: {fonte}"
    else:
        texto = fonte
    if not texto or not texto.strip():
        return False, "fonte vazia (arquivo/URL/texto)"
    # destilação pelo LLM (local; mock devolve genérico e o template segue)
    destilado = ""
    try:
        from .ollama_client import get_client
        cli = get_client(cfg)
        partes = []
        for ch in cli.chat_stream("", [
            {"role": "system", "content":
                "Converta o documento em uma skill SKILL.md com frontmatter "
                "name+description (com palavras-gatilho) e o procedimento "
                "em passos. Responda só o markdown."},
            {"role": "user", "content": texto[:6000]}]):
            t = (ch.get("message") or {}).get("content") or ""
            if t:
                partes.append(t)
        destilado = "".join(partes).strip()
    except Exception:  # noqa: BLE001
        destilado = ""
    if "name:" not in destilado[:200]:
        destilado = ""          # sem frontmatter útil -> template honesto
    primeira = (texto.strip().splitlines() or ["documento"])[0][:60]
    if destilado:
        nome_m = re.search(r"name:\s*(\S+)", destilado)
        e = {"tipo": "skill",
             "alvo": _slug(nome_m.group(1) if nome_m else primeira),
             "titulo": primeira, "rascunho": destilado,
             "origem": "skills-aprender", "objetivo": primeira[:300]}
    else:
        e = rascunho_skill(primeira, texto[:2400],
                           origem="skills-aprender")
    _salvar(cfg, e)
    return True, (f"📚 rascunho de skill criado ({e['alvo']}) — revise e "
                  f"aplique com: hermes aprendidos")


# --------------------------------------------------- busca em conversas
def buscar_conversas(cfg, termo: str, k: int = 8) -> list[dict]:
    """"o que decidimos semana passada?" — busca textual nas sessões."""
    from .conversations import ConversationStore
    store = ConversationStore(cfg)
    achados: list[dict] = []
    try:
        sids = [p.stem for p in store.sessions_dir.glob("*.json")]
    except OSError:
        return achados
    low = termo.lower()
    for sid in sids:
        s = store.load(sid) or {}
        for m in s.get("messages", []):
            c = str(m.get("content", ""))
            if low in c.lower():
                trecho = c[max(0, c.lower().find(low) - 60):
                           c.lower().find(low) + 140].replace("\n", " ")
                achados.append({
                    "session": sid,
                    "data": s.get("updated_at", "?"),
                    "role": m.get("role", "?"),
                    "trecho": trecho,
                    "titulo": s.get("title") or "(sem título)"})
                if len(achados) >= k:
                    return achados
    return achados
