"""Orquestrador + Revisor (v3.3) — pipeline plan → execute → review.

Fluxo de uma mensagem do chat (agente Hermes) — v3.4 acrescenta
goals de sessão (/goal), skills aplicadas automaticamente, portão de
APROVAÇÃO para tarefas de criação e eventos "brain" (visão por baixo
dos panos na GUI):

    mensagem ──► 🎯 ORQUESTRADOR (rápido, JSON)
                   │ rota "responder"  ──► resposta direta (fluxo de antes)
                   │ rota "executar"
                   ▼
                 TASK criada (registrada em data/orchestrator_tasks.jsonl)
                   ▼
                 ⚡ EXECUTOR (o Agent de sempre: ferramentas reais)
                   ▼
                 🔍 REVISOR (rápido, JSON): o resultado cumpre o objetivo?
                   │ "ok"      ──► entrega (com selo de revisada)
                   │ "refazer" ──► re-executa com o problema apontado
                   │              (máx. 2 tentativas — nunca loop infinito)
                   ▼
                 resposta revisada entregue ao operador

Decisões de PERFORMANCE (modelo local ≤8B):
  * orquestrador e revisor usam chamadas RÁPIDAS (num_predict ~200,
    temperature 0) — 1 a 3 s cada;
  * conversa simples ("oi", perguntas) NÃO passa pelo pipeline: a rota
    "responder" tem custo zero adicional;
  * tentativas limitadas (2), prompts curtos, excertos truncados;
  * tudo local, nada sai da máquina; em modo mock o roteamento é
    heurístico e determinístico (demo estável).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

# ── roteamento heurístico (fallback e modo mock — determinístico) ──
_ACAO_RE = re.compile(
    r"\b(crie|criar|cria|execute|executar|executa|rode|rodar|roda|liste|listar|"
    r"lista|verifique|verificar|verifica|analise|analisar|analisa|instale|"
    r"instalar|instala|configure|configurar|configura|escreva|escrever|gere|"
    r"gerar|apague|apagar|limpe|limpar|atualize|atualizar|mova|mover|copie|"
    r"copiar|envie|enviar|resuma|resumir|sumarize|baixe|baixar|monitore|"
    r"monitorar|otimize|otimizar|corrija|corrigir|mostre|mostrar|consulte|"
    r"consultar|leia|ler|busque|buscar|pesquise|pesquisar|conclua|concluir|"
    r"conclui|continue|continuar|retome)\b", re.IGNORECASE)

# v3.5: a MENTE do orquestrador — um sênior de 30 anos de estrada.
# Com modelos ≤8B, persona clara + regras curtas + exemplos firmes rendem
# planos muito melhores do que instruções vagas.
_PLANO_JSON = (
    "Você é o ORQUESTRADOR do Hermes: engenheiro de sistemas SÊNIOR, 30 anos "
    "de Linux, automação e operação — um veterano calmo e direto que já viu "
    "de tudo e só se importa com resultado certo na PRIMEIRA tentativa.\n"
    "Leia a mensagem como esse profissional: identifique a INTENÇÃO real (o "
    "que o usuário PRECISA, não só o que disse) e decida:\n"
    '{"rota":"responder"} — conversa, dúvida, opinião, saudação, explicação;\n'
    '{"rota":"executar","tipo":"leitura|criacao","objetivo":"...",'
    '"passos":["..."],"criterios":["..."]}'
    " — trabalho a fazer. tipo='criacao' quando cria/modifica/apaga/envia/"
    "instala algo; tipo='leitura' quando só consulta/analisa/relata.\n"
    "Padrão de qualidade do veterano (obedecer):\n"
    "- objetivo: UMA frase com verbo de conclusão e a interpretação mais "
    "útil se o pedido for vago;\n"
    "- no máximo 4 passos, curtos e CONCRETOS: cite o comando ou a ferramenta "
    "(ex.: 'executar free -h', 'ps aux --sort=-%mem | head -15') — nunca "
    "'verificar X' sem dizer como;\n"
    "- critérios VERIFICÁVEIS na resposta (ex.: 'a saída real do comando "
    "aparece', 'o caminho do arquivo criado aparece', 'a resposta explica "
    "o que os dados significam');\n"
    "Exemplos:\n"
    '"me conta uma piada" → {"rota":"responder"}\n'
    '"como funciona o DNS?" → {"rota":"responder"}\n'
    '"tem alguma coisa estranha no disco?" → {"rota":"executar","tipo":"leitura",'
    '"objetivo":"Diagnosticar o uso de disco e apontar anomalias com dados reais",'
    '"passos":["executar df -h","executar du -xh / | sort -rh | head -15"],'
    '"criterios":["saída real dos comandos na resposta"]}\n'
    '"quais processos estão usando?" (após pedido sobre memória RAM) → '
    '{"rota":"executar","tipo":"leitura","objetivo":"Listar os processos que '
    'mais consomem memória RAM, com dados reais","passos":["executar '
    'ps aux --sort=-%mem | head -15"],"criterios":["a listagem real de '
    'processos aparece na resposta"]}\n'
    "REGRA DE CONTINUAÇÃO: se a mensagem se referir a um pedido ANTERIOR "
    "('pedido anterior', 'de novo', 'conclua', 'continue', 'mesma conversa'), "
    "o objetivo é completar AQUELE pedido (use o contexto/última task).\n"
    "Responda APENAS o JSON."
)

# v3.5: o REVISOR é o sênior que ASSINA embaixo — cobrar para não haver
# retrabalho é o trabalho dele.
_REVISAO_JSON = (
    "Você é o REVISOR SÊNIOR do Hermes: um veterano exigente, 30 anos de "
    "operação, que assina embaixo do que aprova — e o operador não pode "
    "receber retrabalho. COBRE. Verifique item a item:\n"
    "1. CUMPRIMENTO — o resultado realiza o OBJETIVO por completo?\n"
    "2. EVIDÊNCIA REAL — contém dados reais (saída de comando, conteúdo de "
    "arquivo/e-mail/agenda), ou só conversa e promessas?\n"
    "3. PROIBIÇÕES — pediu ao usuário para executar/verificar algo? (falha "
    "grave) · inventou dados? · ficou no 'vou fazer'?\n"
    "4. ENTREGA — claro, direto, em português, com o resultado visível e "
    "ENTENDÍVEL para a pessoa que pediu (explica o que os dados significam, "
    "não só cola saída crua)?\n"
    "DISCIPLINA DO VETERANO: julgue APENAS pelo OBJETIVO e pelos CRITÉRIOS "
    "dados — NÃO invente critérios novos nem exija o que não foi pedido; "
    "perguntas de cortesia no fim da resposta ('precisa de algo mais?') NÃO "
    "são motivo para reprovar; se o objetivo era exibir/consultar algo e os "
    "dados reais estão na resposta, APROVE.\n"
    "Aprove SÓ se TODOS os itens do checklist passarem. Responda APENAS um JSON:\n"
    '{"veredito":"ok"}\n'
    '{"veredito":"refazer","problema":"o que exatamente faltou, em uma frase '
    'acionável"}\n'
    "Não exija perfeição estética (formatação) — exija cumprimento e verdade."
)


# ───────────────────────────── infra ─────────────────────────────

# v3.4 🧠 rastro das chamadas do orquestrador/revisor (visão "por baixo
# dos panos" na GUI — eventos `brain`). Zerado a cada pipeline.
TRACE: list[dict] = []

def tasks_path(cfg) -> Path:
    return cfg.data_dir / "orchestrator_tasks.jsonl"


def model_for(cfg, role: str) -> str:
    """Modelo de um PAPEL (orquestrador/executor). Vazio = cfg.model.
    Um modelo por vez: o pipeline é SEQUENCIAL — o Ollama carrega cada
    modelo sob demanda (swap de alguns segundos), nunca dois em paralelo
    (RAM/VRAM não permite em máquina local)."""
    return str(getattr(cfg, f"{role}_model", "") or "").strip() or str(cfg.model)


def _fast(cfg, system: str, user: str, ntok: int = 200,
          stage: str = "chamada") -> str:
    """Chamada rápida e curta ao modelo (orquestrador/revisor). Nunca lança;
    em modo mock devolve '' (o chamador cai na heurística/fallback)."""
    if getattr(cfg, "mock", False):
        return ""
    try:
        from .ollama_client import get_client
        client = get_client(cfg)
        out = []
        for chunk in client.chat_stream(
                model_for(cfg, "orchestrator"),
                [{"role": "system", "content": system},
                 {"role": "user", "content": user[:1800]}],
                options={"num_predict": ntok, "temperature": 0}):
            msg = chunk.get("message") or {}
            piece = msg.get("content") or ""
            if piece:
                out.append(piece)
            if chunk.get("done"):
                break
        texto = "".join(out)
        TRACE.append({"stage": stage, "pergunta": user[:240],
                      "resposta_bruta": texto[:500] or "(vazio)"})
        return texto
    except Exception:  # noqa: BLE001
        return ""


def _extract_json(text: str) -> dict | None:
    """Primeiro objeto JSON balanceado do texto (modelos pequenos cercam
    o JSON de prosa) — None se não achar nada válido."""
    t = text or ""
    i = t.find("{")
    while i != -1:
        prof, ini, em_str, esc = 0, i, False, False
        for j in range(i, len(t)):
            c = t[j]
            if em_str:
                if esc:                      # caractere escapado (\" \\ ...)
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    em_str = False
                continue
            if c == '"':
                em_str = True
            elif c == "{":
                prof += 1
            elif c == "}":
                prof -= 1
                if prof == 0:
                    try:
                        obj = json.loads(t[ini:j + 1])
                        return obj if isinstance(obj, dict) else None
                    except ValueError:
                        break
        i = t.find("{", i + 1)
    return None


# ───────────────────────────── 🎯 plano ─────────────────────────────

_FOLLOWUP_RE = re.compile(
    r"\b(pedido|tarefa|anterior|de novo|continu|conclu|repita|refa\w*|"
    r"mesma conversa)\b", re.IGNORECASE)

_CRIACAO_RE = re.compile(
    r"\b(crie|criar|cria|escreva|escrever|gere|gerar|instale|instalar|"
    r"apague|apagar|delete|deletar|mova|mover|copie|copiar|envie|enviar|"
    r"modifique|modificar|atualize|atualizar|edite|editar|baixe|baixar|"
    r"monte|montar|construa|construir|salve|salvar|renomeie|renomear)\b",
    re.IGNORECASE)


def _heuristic(message: str) -> dict:
    msg = message or ""
    if _ACAO_RE.search(msg):
        return {
            "rota": "executar",
            "tipo": "criacao" if _CRIACAO_RE.search(msg) else "leitura",
            "objetivo": msg.strip()[:300],
            "passos": [],
            "criterios": ["a ação foi realmente executada e o resultado "
                          "real está na resposta"],
        }
    return {"rota": "responder"}


def plan(cfg, message: str, history: list[dict] | None = None) -> dict:
    """🎯 Orquestrador: decide a rota e monta o plano. Nunca lança —
    qualquer falha cai na heurística (o chat nunca quebra)."""
    if not getattr(cfg, "orchestrator_on", True):
        return {"rota": "responder"}
    try:
        # v3.6: o sênior lê a conversa, não a linha isolada — evita
        # interpretar "você tem acesso a esses dados" como pedido de ls.
        partes = []
        conv = [m for m in (history or [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                and str(m.get("content") or "").strip()]
        if conv:
            partes.append("CONTEXTO da conversa (últimas falas):")
            for m in conv[-4:]:
                quem = "usuário" if m.get("role") == "user" else "agente"
                partes.append(f"{quem}: {str(m['content'])[:180]}")
            partes.append("")
        # v3.6: "conclua meu pedido anterior" → herda a última task
        if _FOLLOWUP_RE.search(message or ""):
            try:
                ult = (list_tasks(cfg, limit=1) or [{}])[0]
                if ult.get("objetivo"):
                    partes.append(
                        f"[ÚLTIMA TASK: {ult.get('id')} — {ult.get('objetivo')} — "
                        f"status {ult.get('status', '?')}. Se a mensagem atual se "
                        "refere a ela, o objetivo é CONCLUIR essa task.]")
            except Exception:  # noqa: BLE001
                pass
        partes.append("MENSAGEM ATUAL: " + (message or ""))
        texto = _fast(cfg, _PLANO_JSON, "\n".join(partes), ntok=220,
                      stage="🎯 orquestrador")
        obj = _extract_json(texto)
        if obj and obj.get("rota") in ("responder", "executar"):
            if obj["rota"] == "executar":
                obj.setdefault("objetivo", message[:300])
                obj.setdefault("passos", [])
                obj.setdefault("criterios", [])
                if obj.get("tipo") not in ("leitura", "criacao"):
                    obj["tipo"] = ("criacao" if _CRIACAO_RE.search(message or "")
                                   else "leitura")
                obj["passos"] = [str(p)[:160] for p in (obj.get("passos") or [])[:4]]
                obj["criterios"] = [str(c)[:160] for c in (obj.get("criterios") or [])[:3]]
            return obj
    except Exception:  # noqa: BLE001
        pass
    return _heuristic(message)


# ───────────────────────────── 🔍 revisão ─────────────────────────────

def review(cfg, objetivo: str, criterios: list[str], resultado: str) -> dict:
    """🔍 Revisor: o resultado cumpre o objetivo? Nunca lança — falha de
    parse devolve 'ok' (entrega sem travar o chat)."""
    if not getattr(cfg, "reviewer_on", True):
        return {"veredito": "ok"}
    try:
        crit = "\n".join(f"- {c}" for c in (criterios or [])[:3]) or "- cumprir o objetivo"
        user = (f"OBJETIVO: {objetivo}\nCRITÉRIOS:\n{crit}\n\n"
                f"RESULTADO (trecho):\n{resultado[:1800]}")
        texto = _fast(cfg, _REVISAO_JSON, user, ntok=140,
                      stage="🔍 revisor")
        obj = _extract_json(texto)
        if obj and obj.get("veredito") == "refazer":
            return {"veredito": "refazer",
                    "problema": str(obj.get("problema", ""))[:300] or "resultado insuficiente"}
        if obj and obj.get("veredito") == "ok":
            return {"veredito": "ok"}
    except Exception:  # noqa: BLE001
        pass
    return {"veredito": "ok"}


# ───────────────────────── registro das tasks ─────────────────────────

def record(cfg, entry: dict, tid: str | None = None) -> str:
    """Anexa o registro da task (auditoria leve, sem banco)."""
    p = tasks_path(cfg)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not tid:
            n = sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
            tid = f"T{n + 1:04d}"
        entry = {"id": tid, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                 **{k: v for k, v in entry.items() if k != "id"}}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return tid
    except OSError:
        return tid or "?"


def _next_id(cfg) -> str:
    p = tasks_path(cfg)
    try:
        n = sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
        return f"T{n + 1:04d}"
    except OSError:
        return "T0001"


def list_tasks(cfg, limit: int = 100) -> list[dict]:
    p = tasks_path(cfg)
    try:
        linhas = p.read_text(encoding="utf-8").splitlines()
        return [json.loads(l) for l in linhas[-limit:] if l.strip()][::-1]
    except (OSError, ValueError):
        return []


# ──────────────────── 🎯 goals de sessão (/goal) ────────────────────

SESSION_GOALS: dict[str, str] = {}


def set_goal(session_id: str, texto: str) -> None:
    sid = (session_id or "default").strip() or "default"
    if texto and texto.strip():
        SESSION_GOALS[sid] = texto.strip()[:500]
    else:
        SESSION_GOALS.pop(sid, None)


def get_goal(session_id: str) -> str:
    return SESSION_GOALS.get((session_id or "default").strip() or "default", "")


# ──────────────────── ✦ skills aplicadas à task ────────────────────

_STOPWORDS = set("""a o as os um uma de do da dos das em no na nos nas para por com sem sobre
e ou que qual quais quando onde como porque ao aos à às pelo pela os isso este esta
esse essa ser estar ter fazer quero queria preciso pode podem deve devem vou vai
task tarefa use quando envolver qualquer
resumo resumir resumida resumido detalhado detalhes uso usa usar dados dado mostra
mostre mostrar listagem informação informações relatório máquina dispositivo
notebook computador sistema pessoa pessoas""".split())


def skills_for(cfg, text: str, max_skills: int = 2) -> list[dict]:
    """Skills ATIVAS relevantes ao texto (por palavras-chave da descrição).
    Devolve [{name, path, score}] — no máximo 2, score mínimo 2."""
    try:
        from .skills import SkillLoader
        ativas = SkillLoader(cfg).enabled()
    except Exception:  # noqa: BLE001
        return []
    palavras = {w for w in re.findall(r"[a-zà-ú]{4,}", (text or "").lower())
                if w not in _STOPWORDS}
    if not palavras:
        return []
    resultados = []
    for s in ativas:
        alvo = (str(s.get("name", "")) + " " + str(s.get("description", ""))).lower()
        score = sum(1 for w in palavras if w in alvo)
        if score >= 2:
            resultados.append({"name": s.get("name", "?"),
                               "skill_md": s.get("skill_md", ""), "score": score})
    resultados.sort(key=lambda x: -x["score"])
    return resultados[:max_skills]


def _skill_conteudo(cfg, skills: list[dict]) -> str:
    """Conteúdo das SKILLs selecionadas (para injetar no executor)."""
    try:
        from .skills import SkillLoader
        loader = SkillLoader(cfg)
        partes = []
        for s in skills[:2]:
            try:
                md = loader.read_skill_md(s["skill_md"])[:2400]
                partes.append(f"[✦ SKILL {s['name']} — SIGA estas instruções]\n{md}")
            except Exception:  # noqa: BLE001
                continue
        return "\n\n".join(partes)
    except Exception:  # noqa: BLE001
        return ""


# ──────────────────── 🔒 aprovação do operador ────────────────────
# Tarefas de CRIAÇÃO pausam e esperam o operador (✅ aprovar · ✏️ editar ·
# ⛔ cancelar) antes de executar — e a entrega final pode ser editada.

import threading as _threading

_APPROVALS: dict[str, dict] = {}
_AP_LOCK = _threading.Lock()
APPROVAL_TIMEOUT_S = 300.0   # tempo máximo esperando o operador (testes reduzem)


def request_approval(tid: str, timeout: float = 300.0,
                     check=None) -> tuple[str, dict | None]:
    """Bloqueia até o operador decidir (ou esgotar o tempo). Devolve
    (ação, edição): aprovar|editar|cancelar|refazer|entregar · None em
    timeout/cancelamento externo."""
    evt = _threading.Event()
    with _AP_LOCK:
        _APPROVALS[tid] = {"event": evt, "action": None, "edit": None}
    decidiu = evt.wait(timeout) if check is None else False
    if check is not None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if evt.wait(0.25):
                decidiu = True
                break
            if check():
                break
    with _AP_LOCK:
        item = _APPROVALS.pop(tid, None)
    if not item or not decidiu:
        return ("cancelado" if check and check() else "timeout"), None
    return item["action"] or "cancelar", item["edit"]


def approve(tid: str, action: str, edit: dict | None = None) -> bool:
    """Registra a decisão do operador (chamado pelo endpoint da GUI)."""
    with _AP_LOCK:
        item = _APPROVALS.get(tid)
        if not item:
            return False
        item["action"] = str(action or "").strip() or "aprovar"
        item["edit"] = edit if isinstance(edit, dict) else None
        item["event"].set()
        return True


# ───────────────────────── pipeline completo ─────────────────────────

def run_pipeline(agent, cfg, message: str, history: list[dict],
                 on_event=None, cancel=None, max_tentativas: int = 2,
                 goal: str = "", session_id: str = "") -> str:
    """Conversa → 🎯 plano → [🔒 aprovação p/ criação] → ⚡ execução →
    🔍 revisão → [🔒 entrega editável p/ criação] → done.

    Emite eventos `note` (etapas, visíveis sempre) e `brain` (por baixo
    dos panos — a GUI mostra quando o operador liga 🔬).
    """
    ev = on_event or (lambda _e: None)
    from . import activity

    def _cancelado() -> bool:
        return cancel is not None and cancel.is_set()

    TRACE.clear()
    goal_txt = (f"\n[🎯 OBJETIVO DA SESSÃO definido pelo operador: {goal}]"
                if goal else "")
    plano = plan(cfg, message, history)
    ev({"type": "brain", "stage": "🎯 orquestrador",
        "data": {"decisao": plano, "chamadas": list(TRACE)}})

    # rota direta: conversa comum — custo zero adicional
    if plano.get("rota") != "executar":
        return agent.run(history + [{"role": "user",
                                     "content": message + goal_txt}],
                         on_event=on_event, cancel=cancel)

    objetivo = str(plano.get("objetivo") or message)[:300]
    passos = [str(p)[:160] for p in (plano.get("passos") or [])[:4]]
    criterios = [str(c)[:160] for c in (plano.get("criterios") or [])[:3]]
    tipo = plano.get("tipo") if plano.get("tipo") in ("leitura", "criacao") else "leitura"

    # ✦ skills ativas relevantes → instruções injetadas no executor
    sks = skills_for(cfg, message + " " + objetivo)
    skills_txt = ""
    if sks:
        ev({"type": "note",
            "message": "✦ skills aplicadas: " + ", ".join(s["name"] for s in sks)})
        ev({"type": "brain", "stage": "✦ skills",
            "data": {"aplicadas": sks}})
        skills_txt = "\n\n" + _skill_conteudo(cfg, sks)

    tid = _next_id(cfg)
    t0 = time.time()
    ev({"type": "note",
        "message": f"🎯 orquestrador: task {tid} criada ({tipo}) — {objetivo}"})
    activity.log(cfg, "chat", f"🎯 task {tid} ({tipo}) — {objetivo[:80]}")

    def _plano_txt() -> str:
        pt = ("[PLANO DO ORQUESTRADOR — ordem de serviço de um sênior]\n"
              f"Objetivo: {objetivo}")
        if passos:
            pt += "\nPassos:\n" + "\n".join(f"- {p}" for p in passos)
        if criterios:
            pt += "\nCritérios de aceitação (o revisor vai cobrar):\n" + \
                  "\n".join(f"- {c}" for c in criterios)
        pt += ("\nPadrão de qualidade: complete a tarefa até o fim na "
               "PRIMEIRA tentativa; a resposta deve trazer a EVIDÊNCIA real "
               "(saídas de comandos, conteúdos lidos) e nunca pedir ao "
               "usuário para executar ou verificar algo.\n"
               "COMUNICAÇÃO: escreva para a PESSOA que pediu — explique o "
               "que os dados SIGNIFICAM em português claro (ex.: 'a memória "
               "está 41% em uso, sobra 9 GB — saudável'), sem jargão e sem "
               "colar saída crua sem explicação.")
        return pt + goal_txt + skills_txt

    # ── 🔒 portão 1: aprovação do PLANO (só tarefas de criação) ──
    aprovacao = "auto"
    exige_aprovacao = (tipo == "criacao"
                       and getattr(cfg, "creation_approval", True))
    if exige_aprovacao and not _cancelado():
        ev({"type": "approval_request", "id": tid, "kind": "plano",
            "objetivo": objetivo, "passos": passos,
            "skills": [s["name"] for s in sks],
            "msg": "🔒 tarefa de CRIAÇÃO — aprove o plano antes de executar"})
        act, edit = request_approval(
            tid, timeout=APPROVAL_TIMEOUT_S,
            check=lambda: cancel is not None and cancel.is_set())
        if act in ("cancelar", "cancelado", "timeout"):
            motivo = ("cancelada pelo operador" if act == "cancelar"
                      else "cancelada (geração interrompida)" if act == "cancelado"
                      else "aprovação expirou (5 min)")
            record(cfg, {"objetivo": objetivo, "tipo": tipo, "status": "cancelada",
                         "tentativas": 0, "dur_s": round(time.time() - t0, 1),
                         "veredito": "—", "problema": motivo,
                         "skills": [s["name"] for s in sks],
                         "aprovacao": "cancelada"}, tid)
            final = f"⛔ task {tid} {motivo}."
            ev({"type": "note", "message": f"⛔ {final}"})
            ev({"type": "done", "message": final})
            return final
        if act == "editar" and edit:
            objetivo = str(edit.get("objetivo") or objetivo)[:300]
            passos = [str(p)[:160] for p in (edit.get("passos") or passos)[:4]]
            aprovacao = "editada"
            ev({"type": "note",
                "message": "✏️ plano editado pelo operador — seguindo o plano editado"})
        else:
            aprovacao = "aprovada"
            ev({"type": "note", "message": "✅ plano aprovado pelo operador"})

    ev({"type": "brain", "stage": "⚡ executor",
        "data": {"prompt_injetado": _plano_txt()[:700]}})

    # o executor emite o próprio "done"; o pipeline o ENGOLE e emite o done
    # FINAL só depois da revisão/entrega (a GUI recebe a resposta com selo 🔍)
    caixa = {"done": ""}

    def _ev_exec(e: dict) -> None:
        if e.get("type") == "done":
            caixa["done"] = e.get("message") or ""
            return
        ev(e)

    def _run_executor(msgs: list[dict]) -> str:
        """Roda o executor com o MODELO DO PAPEL (v3.7) — aplica o override
        e SEMPRE restaura (try/finally), em qualquer saída."""
        aplicou = False
        try:
            _exec_model = model_for(cfg, "executor")
            if _exec_model != str(cfg.model):
                agent.model_override = _exec_model   # type: ignore[attr-defined]
                aplicou = True
            return agent.run(msgs, on_event=_ev_exec, cancel=cancel)
        finally:
            if aplicou:
                try:
                    agent.model_override = None      # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass

    def _ciclo(msgs: list[dict], max_t: int) -> tuple[str, str, str, int]:
        resultado, verd, prob, tent = "", "ok", "", 0
        for tentativa in range(1, max_t + 1):
            if _cancelado():
                break
            tent = tentativa
            resultado = _run_executor(msgs)
            if _cancelado():
                break
            ver = review(cfg, objetivo, criterios, resultado)
            verd, prob = ver.get("veredito", "ok"), ver.get("problema", "")
            if verd == "ok":
                if tentativa > 1:
                    ev({"type": "note",
                        "message": f"🔍 revisor: aprovada na {tentativa}ª tentativa ✔"})
                break
            if tentativa < max_t:
                ev({"type": "note",
                    "message": f"🔍 revisor: reprovou ({prob[:120]}) — refazendo "
                               f"(tentativa {tentativa + 1}/{max_t})"})
                activity.log(cfg, "chat",
                             f"🔍 revisor reprovou (tentativa {tentativa}) — refazendo")
                lista = ("\n".join(f"{i + 1}. {p}" for i, p in enumerate(passos))
                         if passos else
                         "1. Execute a ação que falta com a ferramenta adequada.")
                msgs = [
                    msgs[0],
                    {"role": "assistant", "content": resultado[:2500]},
                    {"role": "user", "content":
                        f"O REVISOR SÊNIOR reprovou: {prob}\n\n"
                        "EXECUTE AGORA, sem perguntar nada a ninguém:\n"
                        f"{lista}\n"
                        "Depois responda com a EVIDÊNCIA REAL (saídas/conteúdos "
                        "colados na resposta).\n\n"
                        f"PEDIDO ORIGINAL: {message}"},
                ]
            else:
                ev({"type": "note",
                    "message": f"⚠ revisor ainda reprovou após {tentativa} tentativas "
                               f"— entregando com ressalva: {prob[:120]}"})
        return resultado, verd, prob, tent

    mensagens = history[-6:] + [{"role": "user",
                                 "content": f"{message}\n\n{_plano_txt()}"}]
    resultado, veredito, problema, tentativas = _ciclo(mensagens, max_tentativas)
    execucoes = tentativas

    # ── 🔒 portão 2: entrega editável (só criação aprovada) ──
    entregue = "direta"
    selo = ("\n\n─\n🔍 *revisada pelo revisor — veredito: aprovada*"
            if veredito == "ok" else
            f"\n\n─\n⚠ *revisão: reprovada* — {problema[:200]}")
    if (exige_aprovacao and aprovacao in ("aprovada", "editada")
            and veredito == "ok" and not _cancelado()):
        texto_entrega = (caixa["done"] or resultado) + selo
        ev({"type": "approval_request", "id": f"{tid}-e", "kind": "entrega",
            "texto": texto_entrega,
            "msg": "📦 entrega final — revise, edite se quiser, e confirme"})
        act2, edit2 = request_approval(
            f"{tid}-e", timeout=APPROVAL_TIMEOUT_S,
            check=lambda: cancel is not None and cancel.is_set())
        if act2 == "editar" and edit2 and str(edit2.get("texto", "")).strip():
            texto = str(edit2["texto"]).rstrip()
            final = texto + "\n\n─\n✏️ *entrega editada pelo operador · 🔍 revisada antes*"
            entregue = "editada"
        elif act2 == "refazer" and execucoes < 3:
            ev({"type": "note",
                "message": "🔁 refazendo a pedido do operador (entrega reprovada)"})
            msgs2 = [mensagens[0],
                     {"role": "assistant", "content": (caixa["done"] or resultado)[:2500]},
                     {"role": "user", "content":
                         "O OPERADOR reprovou a ENTREGA. Refaça a tarefa original "
                         "com mais capricho e complete de verdade."}]
            resultado, veredito, problema, tent2 = _ciclo(msgs2, 1)
            execucoes += tent2
            selo2 = ("\n\n─\n🔍 *revisada — aprovada após refazer a pedido do operador*"
                     if veredito == "ok" else
                     f"\n\n─\n⚠ *revisão: reprovada* — {problema[:200]}")
            final = (caixa["done"] or resultado) + selo2
            entregue = "refeita"
        elif act2 in ("cancelar", "cancelado"):
            record(cfg, {"objetivo": objetivo, "tipo": tipo, "status": "cancelada",
                         "tentativas": execucoes, "dur_s": round(time.time() - t0, 1),
                         "veredito": veredito, "problema": "cancelada na entrega",
                         "skills": [s["name"] for s in sks],
                         "aprovacao": f"{aprovacao}+cancelada"}, tid)
            final = f"⛔ task {tid} cancelada na entrega — nenhum resultado entregue."
            ev({"type": "note", "message": final})
            ev({"type": "done", "message": final})
            return final
        elif act2 == "timeout":
            final = texto_entrega + "\n\n─\n⚠ *entrega sem confirmação (tempo esgotado)*"
            entregue = "sem_confirmacao"
        else:                                   # entregar
            final = texto_entrega
            entregue = "entregue"
    else:
        final = (caixa["done"] or resultado) + selo

    dur = round(time.time() - t0, 1)
    status = ("aprovada" if veredito == "ok" and not _cancelado() else
              "reprovada" if not _cancelado() else "cancelada")
    record(cfg, {"objetivo": objetivo, "tipo": tipo, "status": status,
                 "tentativas": execucoes, "dur_s": dur,
                 "veredito": veredito, "problema": problema[:200],
                 "skills": [s["name"] for s in sks],
                 "aprovacao": (aprovacao if not exige_aprovacao else
                               f"{aprovacao}·{entregue}")}, tid)
    activity.log(cfg, "chat",
                 f"🎯 task {tid} {status} · {execucoes} execução(ões) · {dur}s")
    ev({"type": "brain", "stage": "🔍 revisor",
        "data": {"veredito": veredito, "problema": problema,
                 "chamadas": TRACE[-1:]}})
    ev({"type": "done", "message": final})   # o done verdadeiro, pós-tudo
    return final
