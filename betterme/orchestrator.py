"""Orquestrador + Revisor (v3.3) — pipeline plan → execute → review.

Fluxo de uma mensagem do chat (agente Betterme) — v3.4 acrescenta
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
    "Você é o ORQUESTRADOR do Betterme: engenheiro de sistemas SÊNIOR, 30 anos "
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
    "Você é o REVISOR SÊNIOR do Betterme: um veterano exigente, 30 anos de "
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
    m = str(getattr(cfg, f"{role}_model", "") or "").strip()
    if m:
        return m
    if role == "reviewer":                    # revisor vazio → do orquestrador
        m = str(getattr(cfg, "orchestrator_model", "") or "").strip()
        if m:
            return m
    return str(cfg.model)


def _fast(cfg, system: str, user: str, ntok: int = 200,
          stage: str = "chamada", model: str = "") -> str:
    """Chamada rápida e curta ao modelo (orquestrador/revisor). Nunca lança;
    em modo mock devolve '' (o chamador cai na heurística/fallback)."""
    if getattr(cfg, "mock", False):
        return ""
    try:
        from .ollama_client import get_client
        client = get_client(cfg)
        out = []
        for chunk in client.chat_stream(
                model or model_for(cfg, "orchestrator"),
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

# v3.13.3: tarefas de CÓDIGO ganham critério de execução — o revisor
# passa a cobrar a SAÍDA REAL do código rodado (rastro > opinião do modelo)
_CODIGO_RE = re.compile(
    r"\b(c[óo]digo|script|fun[çc][ãa]o|funcao|classe|programa|implement\w*|"
    r"python|\.py\b|\bvba\b|algoritmo|m[óo]dulo|api|classe|"
    r"projeto|aplicativo|calculadora)\b",
    re.IGNORECASE)


def _extra_criterios(message: str) -> list[str]:
    """Critérios estruturais por CLASSE de tarefa (v3.13.3): código
    só entrega com saída de execução real colada na resposta."""
    if _CODIGO_RE.search(message or ""):
        return ["o código foi ESCRITO em arquivo e EXECUTADO, com a SAÍDA "
                "REAL da execução colada na resposta (não só o código)"]
    return []


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


# v3.13 💾: cache de planos — pedido REPETIDO não gasta tokens de
# planejamento. Invalidado quando o operador ensina algo novo (edição
# de plano/entrega ou reprovação): preferência nova, plano novo.
_PLAN_CACHE: dict[tuple[str, str], dict] = {}
_PLAN_CACHE_MAX = 200


def _plan_key(cfg, message: str) -> tuple[str, str]:
    import re as _re
    norm = _re.sub(r"\s+", " ", str(message or "").strip().lower())[:200]
    return (str(cfg.data_dir), norm)


def _cache_invalidate(cfg) -> None:
    prefix = str(cfg.data_dir)
    for k in [k for k in _PLAN_CACHE if k[0] == prefix]:
        _PLAN_CACHE.pop(k, None)


def plan(cfg, message: str, history: list[dict] | None = None) -> dict:
    """🎯 Orquestrador: decide a rota e monta o plano. Nunca lança —
    qualquer falha cai na heurística (o chat nunca quebra)."""
    if not getattr(cfg, "orchestrator_on", True):
        return {"rota": "responder"}
    chave = _plan_key(cfg, message)
    hit = _PLAN_CACHE.get(chave)
    if hit is not None:                     # v3.13: repetiu → 0 tokens
        return dict(hit)
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
        xp = experience(cfg)
        if xp:
            partes.append(xp)
        partes.append("MENSAGEM ATUAL: " + (message or ""))
        texto = _fast(cfg, _PLANO_JSON, "\n".join(partes), ntok=220,
                      stage="🎯 orquestrador", model=model_for(cfg, "orchestrator"))
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
            _PLAN_CACHE[chave] = dict(obj)
            if len(_PLAN_CACHE) > _PLAN_CACHE_MAX:
                _PLAN_CACHE.pop(next(iter(_PLAN_CACHE)))
            return obj
    except Exception:  # noqa: BLE001
        pass
    _PLAN_CACHE[chave] = _heuristic(message)
    return _PLAN_CACHE[chave]


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
                      stage="🔍 revisor", model=model_for(cfg, "reviewer"))
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
        # v3.13: o operador ensinou algo (editou/reprovou) → planos
        # em cache podem estar velhos; preferência nova, plano novo
        if (entry.get("entrega_editada") or entry.get("plano_editado")
                or entry.get("status") == "reprovada"):
            _cache_invalidate(cfg)
        return tid
    except OSError:
        return tid or "?"


def experience(cfg, limit: int = 6) -> str:
    """v3.10 🧠: o orquestrador APRENDE — as últimas tasks (resultados,
    reprovações e EDIÇÕES do operador) viram contexto do planejamento.
    As edições do operador são as preferências dele; repetir erro que já
    foi corrigido é falta de experiência."""
    try:
        tasks = list_tasks(cfg, limit=limit)
    except Exception:  # noqa: BLE001
        return ""
    if not tasks:
        return ""
    fortes, fracas = [], []
    for tk in tasks:
        if not isinstance(tk, dict):
            continue
        linha = (f"- {tk.get('id', '?')} · {tk.get('status', '?')} · "
                 f"{tk.get('tentativas', '?')} exec · {str(tk.get('objetivo', ''))[:100]}")
        sk = tk.get("skills") or []
        if sk:
            linha += f" (skills: {', '.join(sk)})"
        prob = str(tk.get("problema") or "")[:80]
        if tk.get("status") == "reprovada" and prob:
            linha += f" — problema: {prob}"
        if tk.get("plano_editado"):
            linha += " · o operador EDITOU o plano antes de executar"
        if tk.get("entrega_editada"):
            linha += (f" · o operador EDITOU a entrega para: "
                      f"“{str(tk['entrega_editada'])[:120]}”")
        # v3.11.5: sinal FORTE (edição/reprovação) vem primeiro —
        # bloco enxuto: 4 sinais, 800 chars. Prompt menor = mais rápido
        # e o planejador (8B) não se distrai com histórico grande.
        forte = bool(tk.get("entrega_editada") or tk.get("plano_editado")
                     or tk.get("status") == "reprovada")
        (fortes if forte else fracas).append(linha)
    linhas = (fortes + fracas)[:4]
    return ("[EXPERIÊNCIA DO ORQUESTRADOR — sinais recentes do operador]\n"
            + "\n".join(linhas)[:560]
            + "\nAs edições são PREFERÊNCIAS dele — planeje de acordo; "
              "evite o que já foi reprovado.")[:800]


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


def _goals_path(cfg) -> Path:
    return cfg.data_dir / "session_goals.json"


# ──────────── v3.15.0 (PR#1): detecção da pasta do projeto no pedido ────────────

_PROJETO_RE = re.compile(
    r"(?:^|[\s'\"(\[])(~/[^\s'\"()\[\]]+|/[A-Za-z][^\s'\"()\[\]]*)")


def _detectar_projetos(message: str) -> list[Path]:
    """Referências de pasta no pedido (absolutas ou ~/...), em ordem.

    Ignora URLs (nada precede a barra), frações/datas (24/09) e âncoras
    de markdown. O operador declara o projeto assim: 'crie X em
    /media/Arquivos/projetos/app' ou '~/projetos/app'."""
    achados: list[Path] = []
    for m in _PROJETO_RE.finditer(message or ""):
        cand = m.group(1).rstrip(".,;:!?")
        if cand.startswith("~"):
            cand = str(Path.home() / cand[2:])
        if len(cand) < 4 or not re.search(r"[A-Za-z]", cand):
            continue
        p = Path(cand)
        if p.exists() and p.is_file():
            p = p.parent            # referência a arquivo → pasta dele
        if p not in achados:
            achados.append(p)
    return achados


def _ambiente_txt(projeto: Path) -> str:
    """v3.15.0 (PR#1): ambiente do projeto injetado no executor — o padrão
    do Claude Code (cwd, data, SO, git, memória do projeto), enxuto."""
    import platform
    import subprocess
    linhas = ["[AMBIENTE DA TAREFA]",
              f"Pasta do projeto (cwd): {projeto}",
              f"Data: {time.strftime('%Y-%m-%d')} · SO: {platform.platform()}"]
    if (projeto / ".git").exists():
        try:
            r = subprocess.run(["git", "-C", str(projeto), "status", "--short"],
                               capture_output=True, text=True, timeout=6,
                               check=False)
            b = subprocess.run(["git", "-C", str(projeto), "branch",
                                "--show-current"], capture_output=True,
                               text=True, timeout=6, check=False)
            alter = "\n".join((r.stdout or "").strip().splitlines()[:5])
            git = f"Git: branch {(b.stdout or '').strip() or '?'}"
            linhas.append(git + (f" · alterações:\n{alter}" if alter
                                 else " (árvore limpa)"))
        except Exception:  # noqa: BLE001
            pass
    hm = projeto / "betterme.md"
    if hm.exists():
        try:
            conteudo = hm.read_text(encoding="utf-8").strip()[:1500]
            if conteudo:
                linhas.append("Memória do projeto (betterme.md — convenções do "
                              "operador):\n" + conteudo)
        except OSError:
            pass
    linhas.append("Paths relativos resolvem DENTRO da pasta do projeto.")
    return "\n".join(linhas)


def load_goals(cfg) -> None:
    """v3.11: goals de sessão voltam do disco ao subir o servidor."""
    try:
        dados = json.loads(_goals_path(cfg).read_text(encoding="utf-8"))
        if isinstance(dados, dict):
            SESSION_GOALS.update({str(k): str(v)[:500]
                                  for k, v in dados.items()})
    except (OSError, ValueError):
        pass


def set_goal(session_id: str, texto: str, cfg=None) -> None:
    sid = (session_id or "default").strip() or "default"
    if texto and texto.strip():
        SESSION_GOALS[sid] = texto.strip()[:500]
    else:
        SESSION_GOALS.pop(sid, None)
    if cfg is not None:                     # v3.11: sobrevive a restart
        try:
            _goals_path(cfg).parent.mkdir(parents=True, exist_ok=True)
            tmp = _goals_path(cfg).with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(SESSION_GOALS, ensure_ascii=False, indent=1),
                encoding="utf-8")
            tmp.replace(_goals_path(cfg))  # v3.14.2: atômico, crash não corrompe
        except OSError:
            pass


def get_goal(session_id: str, cfg=None) -> str:
    sid = (session_id or "default").strip() or "default"
    if sid not in SESSION_GOALS and cfg is not None:
        load_goals(cfg)                     # v3.11: RAM fria → disco
    return SESSION_GOALS.get(sid, "")


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


def _skill_criterios(skills: list[dict]) -> list[str]:
    """v3.15.0 (PR#3): DELEGAÇÃO — a seção '## Verificação' da skill que
    casou vira critérios que o 🔍 revisor vai cobrar na entrega."""
    if not skills:
        return []
    try:
        md = Path(skills[0]["skill_md"]).read_text(encoding="utf-8",
                                                   errors="replace")
    except OSError:
        return []
    itens, capturando = [], False
    for ln in md.splitlines():
        if ln.strip().startswith("## "):
            capturando = "verifica" in ln.strip().lower()
            continue
        if capturando and ln.strip().startswith(("-", "*")):
            item = ln.strip().lstrip("-* ").strip()
            if item:
                itens.append(f"[skill {skills[0]['name']}] {item[:140]}")
    return itens[:3]


def _skill_conteudo(cfg, skills: list[dict]) -> str:
    """Conteúdo das SKILLs selecionadas (para injetar no executor)."""
    try:
        from .skills import SkillLoader
        loader = SkillLoader(cfg)
        partes = []
        for s in skills[:2]:
            try:
                md = loader.read_skill_md(s["skill_md"])[:2400]
                partes.append(f"[✦ SKILL {s['name']} — MANUAL DA TAREFA: siga "
                          f"estas instruções à risca]\n{md}")
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


def _pending_path(cfg) -> Path:
    return cfg.data_dir / "pending_approvals.json"


def _pending_save(cfg, dados: dict) -> None:
    try:
        p = _pending_path(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(p)  # v3.14.2: atômico, crash não corrompe
    except OSError:
        pass


def _pending_load(cfg) -> dict:
    try:
        dados = json.loads(_pending_path(cfg).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def list_pending(cfg) -> list[dict]:
    """v3.11: pendências que sobreviveram a um restart (🔒/📦)."""
    return sorted(_pending_load(cfg).values(), key=lambda x: x.get("ts", ""))


def peek_pending(cfg, tid: str) -> dict | None:
    return _pending_load(cfg).get(tid)


def pop_pending(cfg, tid: str) -> dict | None:
    with _AP_LOCK:
        dados = _pending_load(cfg)
        item = dados.pop(tid, None)
        if item is not None:
            _pending_save(cfg, dados)
    return item


def request_approval(tid: str, timeout: float = 300.0,
                     check=None, cfg=None, meta: dict | None = None
                     ) -> tuple[str, dict | None]:
    """Bloqueia até o operador decidir (ou esgotar o tempo). Devolve
    (ação, edição): aprovar|editar|cancelar|refazer|entregar · None em
    timeout/cancelamento externo.

    v3.11: com cfg+meta a pendência vai para o DISCO e sobrevive a
    restart — sai do arquivo só quando o operador DECIDE (aprovar/
    editar/cancelar/refazer/entregar). Timeout/cancelamento deixa o
    registro: o operador ainda pode agir sobre ele depois."""
    evt = _threading.Event()
    with _AP_LOCK:
        _APPROVALS[tid] = {"event": evt, "action": None, "edit": None}
        if cfg is not None and meta:
            dados = _pending_load(cfg)
            dados[tid] = {**meta, "id": tid,
                          "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            _pending_save(cfg, dados)
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
        if item and decidiu and cfg is not None:
            dados = _pending_load(cfg)
            if dados.pop(tid, None) is not None:
                _pending_save(cfg, dados)
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

# ──────────── v3.15.1: projeto sem caminho → PERGUNTA ao operador ────────────
# Contrato: iniciar projeto sempre passa pela pasta (informada no pedido OU
# em resposta à pergunta). A pendência vive em memória, por sessão, com TTL.

_PEND_PROJ_LOCK = _threading.Lock()
_PEND_PROJETO: dict[str, dict] = {}
_PEND_PROJ_TTL = 600.0          # 10 min para responder o caminho
_MISSAO_RE = re.compile(
    r"(?i)^\s*(missão|missao|modo\s+miss[ãa]o)\s*[:\-—]\s*")
_CANCELA_RE = re.compile(
    r"(?i)^\s*(cancela\w*|esquece|deixa|parar?|não\b|nao\b|nop\w*)\b")

# "quero INICIAR um projeto/app..." — sinal de início de projeto mesmo se o
# plano vacilar entre leitura/criação (robustez contra o classificador)
_INICIAR_PROJ_RE = re.compile(
    r"(?i)\b(iniciar|in[íi]cio|come[cç]ar|montar|construir|desenvolver)\b"
    r"[^\n]{0,60}\b(projeto|app|aplicativo|sistema|website|servi[çc]o|api)\b"
    r"|\b(projeto|app|aplicativo|sistema|website|servi[çc]o|api)\b"
    r"[^\n]{0,40}\b(iniciar|come[cç]ar)\b")


def _pergunta_caminho(message: str, goal: str, session_id: str) -> str:
    with _PEND_PROJ_LOCK:
        _PEND_PROJETO[session_id or "default"] = {
            "message": message, "t": time.time()}
    return (
        "📁 Para iniciar este projeto preciso do caminho da pasta — pode ser "
        "em qualquer ponto do diretório (ex.: /media/Arquivos/projetos/2026/"
        "meu-app ou ~/projetos/meu-app). A pasta será **buscada e criada** "
        "se ainda não existir, e todo o trabalho (arquivos, execução, git) "
        "acontecerá lá.\n\nResponda com o caminho para eu começar "
        "(ou diga *cancela* para desistir).")


def _pedir_caminho(ev, message: str, goal: str, session_id: str) -> str:
    """Emite os eventos e devolve a pergunta (uso nos 2 caminhos de rota)."""
    ev({"type": "note",
        "message": "📁 projeto sem pasta definida — perguntando o "
                   "caminho ao operador"})
    pergunta = _pergunta_caminho(message, goal, session_id)
    ev({"type": "done", "message": pergunta})
    return pergunta


def _quer_projeto_sem_caminho(cfg, message: str, resume_plan) -> bool:
    """v3.15.1: task de código/projeto para INICIAR, sem pasta no pedido."""
    return bool(getattr(cfg, "ask_project_path", True)
                and not resume_plan
                and _extra_criterios(message)
                and not _detectar_projetos(message))


def run_pipeline(agent, cfg, message: str, history: list[dict],
                 on_event=None, cancel=None, max_tentativas: int = 2,
                 goal: str = "", session_id: str = "",
                 resume_plan: dict | None = None,
                 resume_tid: str | None = None,
                 extra_criterios: list[str] | None = None,
                 resultado_meta: dict | None = None) -> str:
    """Conversa → 🎯 plano → [🔒 aprovação p/ criação] → ⚡ execução →
    🔍 revisão → [🔒 entrega editável p/ criação] → done.

    Emite eventos `note` (etapas, visíveis sempre) e `brain` (por baixo
    dos panos — a GUI mostra quando o operador liga 🔬).
    """
    _ev_base = on_event or (lambda _e: None)
    _n_tools = [0]              # v4.0.0 (M6.5): p/ loop de aprendizado

    def ev(e):                  # conta tool_start + repassa ao caller
        if e.get("type") == "tool_start":
            _n_tools[0] += 1
        _ev_base(e)

    from . import activity

    def _cancelado() -> bool:
        return cancel is not None and cancel.is_set()

    # ── v3.16.0: MODO MISSÃO — 1 tarefa → subtasks encadeadas → validação
    # → retry com task reescrita → relatório. Gatilho: "missão: <objetivo>".
    if _MISSAO_RE.match(message) and not resume_plan:
        with _PEND_PROJ_LOCK:            # consome pendência de caminho
            _PEND_PROJETO.pop(session_id or "default", None)
        from .mission import run_mission
        return run_mission(agent, cfg, message, history, on_event=on_event,
                           cancel=cancel, goal=goal, session_id=session_id)

    TRACE.clear()
    goal_txt = (f"\n[🎯 OBJETIVO DA SESSÃO definido pelo operador: {goal}]"
                if goal else "")

    # ── v3.15.1: o operador respondeu o CAMINHO do projeto pendente? ──
    forcar_executar, pend_msg = False, ""
    if session_id:
        with _PEND_PROJ_LOCK:
            pend = _PEND_PROJETO.get(session_id)
            if pend and time.time() - pend["t"] > _PEND_PROJ_TTL:
                _PEND_PROJETO.pop(session_id, None)
                pend = None
        if pend:
            caminho = _detectar_projetos(message)
            if caminho:
                with _PEND_PROJ_LOCK:
                    _PEND_PROJETO.pop(session_id, None)
                ev({"type": "note",
                    "message": "📁 pasta recebida — retomando o projeto"})
                pend_msg = pend["message"]
                forcar_executar = True   # a decisão do operador prevalece
                message = (pend["message"]
                           + f"\n\n[Pasta do projeto definida pelo operador: "
                             f"{caminho[0]}]")
                if _MISSAO_RE.match(message):
                    # v3.16.0: missão retomada com o caminho — volta ao
                    # modo missão (não vira task única)
                    from .mission import run_mission
                    return run_mission(agent, cfg, message, history,
                                       on_event=on_event, cancel=cancel,
                                       goal=goal, session_id=session_id)
            elif _CANCELA_RE.match(message):
                with _PEND_PROJ_LOCK:
                    _PEND_PROJETO.pop(session_id, None)
                ev({"type": "note",
                    "message": "⛔ projeto cancelado pelo operador"})
                final = "⛔ projeto cancelado — quando quiser, é só pedir de novo."
                ev({"type": "done", "message": final})
                return final
            else:
                # assunto mudou: pendência expira na hora (sem pegadinha)
                with _PEND_PROJ_LOCK:
                    _PEND_PROJETO.pop(session_id, None)

    if resume_plan:                    # v3.11: retomada pós-restart
        plano = dict(resume_plan)
        plano["rota"] = "executar"     # o plano já foi aprovado
    else:
        plano = plan(cfg, message, history)
    if forcar_executar and plano.get("rota") != "executar":
        # v3.15.1: o operador INFORMOU a pasta do projeto — executar, e o
        # planner não re-decide (robustez contra classificação vacilante)
        plano = {"rota": "executar", "tipo": "criacao",
                 "objetivo": (pend_msg or message)[:300],
                 "passos": [], "criterios": []}
    ev({"type": "brain", "stage": "🎯 orquestrador",
        "data": {"decisao": plano, "chamadas": list(TRACE)}})

    # rota direta: conversa comum — custo zero adicional
    if plano.get("rota") != "executar":
        # v3.15.1: "quero iniciar um projeto..." sem pasta não é conversa —
        # o planner pode vacilar, o sinal de início prevalece
        if (_quer_projeto_sem_caminho(cfg, message, resume_plan)
                and not _cancelado()
                and _INICIAR_PROJ_RE.search(message)):
            return _pedir_caminho(ev, message, goal, session_id)
        return agent.run(history + [{"role": "user",
                                     "content": message + goal_txt}],
                         on_event=on_event, cancel=cancel)

    objetivo = str(plano.get("objetivo") or message)[:300]
    passos = [str(p)[:160] for p in (plano.get("passos") or [])[:4]]
    criterios = [str(c)[:160] for c in (plano.get("criterios") or [])[:3]]
    criterios += _extra_criterios(message)      # v3.13.3: rastro obrigatório
    sks_antecipadas = skills_for(cfg, message + " " + objetivo)
    criterios += _skill_criterios(sks_antecipadas)  # v3.15.0: skill delega
    if extra_criterios:   # v3.16.0: critérios da SUBTASK da missão
        criterios += [str(c)[:160] for c in extra_criterios[:4]]
    tipo = plano.get("tipo") if plano.get("tipo") in ("leitura", "criacao") else "leitura"

    # ── v3.15.1: projeto de criação SEM caminho → pergunta e espera ──
    if (_quer_projeto_sem_caminho(cfg, message, resume_plan)
            and not _cancelado()
            and (tipo == "criacao" or _INICIAR_PROJ_RE.search(message))):
        return _pedir_caminho(ev, message, goal, session_id)

    # ✦ skills ativas relevantes → instruções injetadas no executor
    sks = skills_for(cfg, message + " " + objetivo)
    skills_txt = ""
    if sks:
        ev({"type": "note",
            "message": "✦ skills aplicadas: " + ", ".join(s["name"] for s in sks)})
        ev({"type": "brain", "stage": "✦ skills",
            "data": {"aplicadas": sks}})
        skills_txt = "\n\n" + _skill_conteudo(cfg, sks)

    tid = resume_tid or _next_id(cfg)
    t0 = time.time()
    ev({"type": "note",
        "message": f"🎯 orquestrador: task {tid} criada ({tipo}) — {objetivo}"})
    if resume_plan:
        ev({"type": "note",
            "message": f"🔁 task {tid} RETOMADA após restart — plano já aprovado pelo operador"})
    activity.log(cfg, "chat", f"🎯 task {tid} ({tipo}) — {objetivo[:80]}")

    # ── v3.15.0 (PR#1): pasta do projeto declarada no pedido ──
    from .tools import ToolError, task_scope, validar_escopo_projeto
    projeto = None
    cands_proj = _detectar_projetos(message)
    for cand in cands_proj:
        try:
            projeto = validar_escopo_projeto(cand, cfg)
            break
        except ToolError:
            continue
    if cands_proj and projeto is None:
        ev({"type": "note",
            "message": "⚠ pasta declarada no pedido não pôde ser usada "
                       "(sistema/configuração do Betterme) — executando no "
                       "workspace padrão"})
    projeto_txt = ("\n" + _ambiente_txt(projeto)) if projeto is not None else ""

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
        return pt + goal_txt + skills_txt + projeto_txt

    # ── 🔒 portão 1: aprovação do PLANO (só tarefas de criação) ──
    aprovacao = "auto"
    edit_snip, plano_editado = "", False   # v3.10: sinais de experiência
    # v4.0.0 (M5): AUTÔNOMO pula o gate soft de criação (hard gates ficam)
    from .autonomy import pula_gate_criacao, pre_entrega_varredura
    exige_aprovacao = (tipo == "criacao"
                       and getattr(cfg, "creation_approval", True)
                       and not pula_gate_criacao(cfg))
    if resume_plan:                    # v3.11: já aprovado antes do restart
        aprovacao = "retomada"
        plano_editado = bool(resume_plan.get("_editada"))
        exige_aprovacao = False
    if exige_aprovacao and not _cancelado():
        ev({"type": "approval_request", "id": tid, "kind": "plano",
            "objetivo": objetivo, "passos": passos,
            "skills": [s["name"] for s in sks],
            "msg": "🔒 tarefa de CRIAÇÃO — aprove o plano antes de executar"})
        act, edit = request_approval(
            tid, timeout=APPROVAL_TIMEOUT_S,
            check=lambda: cancel is not None and cancel.is_set(),
            cfg=cfg,
            meta={"kind": "plano", "task_id": tid, "objetivo": objetivo,
                  "tipo": tipo, "passos": passos, "criterios": criterios,
                  "message": message, "session_id": session_id,
                  "goal": goal})
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
            plano_editado = True          # v3.10: a edição vira experiência
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
        # v3.15.0 (PR#2): tarefa longa (projeto/código) ganha fôlego —
        # 8 passes e 40 ferramentas no lugar de 4/12 — SEMPRE restaurado.
        longa = (projeto is not None) or bool(_extra_criterios(message))
        try:
            _exec_model = model_for(cfg, "executor")
            if _exec_model != str(cfg.model):
                agent.model_override = _exec_model   # type: ignore[attr-defined]
                aplicou = True
            if longa:
                agent.tool_budget_override = 40      # type: ignore[attr-defined]
                agent.steps_override = 8             # type: ignore[attr-defined]
            return agent.run(msgs, on_event=_ev_exec, cancel=cancel)
        finally:
            if aplicou:
                try:
                    agent.model_override = None      # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
            if longa:
                try:
                    agent.tool_budget_override = None  # type: ignore[attr-defined]
                    agent.steps_override = None        # type: ignore[attr-defined]
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
                        "colados na resposta), INTERPRETANDO em texto o que os "
                        "números significam. Recusa (\u201cnão vou repetir\u201d, "
                        "\u201cpronto para ajudar\u201d) ou saída crua de comando "
                        "sem interpretação NÃO são resposta — são falha de "
                        "entrega.\n\n"
                        f"PEDIDO ORIGINAL: {message}"},
                ]
            else:
                ev({"type": "note",
                    "message": f"⚠ revisor ainda reprovou após {tentativa} tentativas "
                               f"— entregando com ressalva: {prob[:120]}"})
        return resultado, verd, prob, tent

    mensagens = history[-6:] + [{"role": "user",
                                 "content": f"{message}\n\n{_plano_txt()}"}]
    if projeto is not None:
        # v3.15.0 (PR#1): executa DENTRO da pasta do projeto — cwd dos
        # comandos, leitura/escrita liberadas só nela, caminho criado se
        # ainda não existir. Fora dela, nada muda.
        try:
            with task_scope(projeto, cfg):
                ev({"type": "note",
                    "message": f"📁 workspace da task: {projeto} — pasta "
                               "percorrida/criada pelo Betterme"})
                resultado, veredito, problema, tentativas = _ciclo(
                    mensagens, max_tentativas)
        except ToolError as exc:
            ev({"type": "note", "message": f"⚠ {exc} — workspace padrão"})
            resultado, veredito, problema, tentativas = _ciclo(
                mensagens, max_tentativas)
    else:
        resultado, veredito, problema, tentativas = _ciclo(mensagens, max_tentativas)
    execucoes = tentativas

    # ── 🔒 portão 2: entrega editável (só criação aprovada) ──
    entregue = "direta"
    if not getattr(cfg, "reviewer_on", True):
        selo = ""            # revisor desligado: sem selo de revisão
    elif veredito == "ok":
        selo = "\n\n─\n🔍 *revisada pelo revisor — veredito: aprovada*"
    else:
        selo = f"\n\n─\n⚠ *revisão: reprovada* — {problema[:200]}"
    from .autonomy import pula_gate_entrega
    if (exige_aprovacao and aprovacao in ("aprovada", "editada")
            and veredito == "ok" and not _cancelado()
            and not pula_gate_entrega(cfg)):
        texto_entrega = (caixa["done"] or resultado) + selo
        ev({"type": "approval_request", "id": f"{tid}-e", "kind": "entrega",
            "texto": texto_entrega,
            "msg": "📦 entrega final — revise, edite se quiser, e confirme"})
        act2, edit2 = request_approval(
            f"{tid}-e", timeout=APPROVAL_TIMEOUT_S,
            check=lambda: cancel is not None and cancel.is_set(),
            cfg=cfg,
            meta={"kind": "entrega", "task_id": tid, "texto": texto_entrega,
                  "objetivo": objetivo, "tipo": tipo, "message": message,
                  "session_id": session_id, "goal": goal,
                  "tentativas": execucoes})
        if act2 == "editar" and edit2 and str(edit2.get("texto", "")).strip():
            texto = str(edit2["texto"]).rstrip()
            final = texto + "\n\n─\n✏️ *entrega editada pelo operador · 🔍 revisada antes*"
            entregue = "editada"
            edit_snip = texto[:200]      # v3.10: a edição vira experiência
        elif act2 == "refazer" and execucoes < 3:
            ev({"type": "note",
                "message": "🔁 refazendo a pedido do operador (entrega reprovada)"})
            msgs2 = [mensagens[0],
                     {"role": "assistant", "content": (caixa["done"] or resultado)[:2500]},
                     {"role": "user", "content":
                         "O OPERADOR reprovou a ENTREGA. Refaça a tarefa original "
                         "com mais capricho e complete de verdade. Use os dados JÁ "
                         "COLETADOS na conversa (não repita chamadas de ferramenta) "
                         "e escreva a resposta final COMPLETA com eles."}]
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

    # v4.0.0 (M5): AUTÔNOMO entrega sem gate soft — em compensação, o
    # projeto criado passa pela varredura PRÉ-ENTREGA (risco #10)
    if tipo == "criacao" and projeto is not None:
        try:
            from .autonomy import nivel as _nivel_aut
            if _nivel_aut(cfg) == "autonomo":
                final += pre_entrega_varredura(cfg, projeto)
        except Exception:  # noqa: BLE001
            pass

    dur = round(time.time() - t0, 1)
    status = ("aprovada" if veredito == "ok" and not _cancelado() else
              "reprovada" if not _cancelado() else "cancelada")
    if resultado_meta is not None:      # v3.16.0: missão lê o veredito
        resultado_meta.update({"veredito": veredito, "problema": problema,
                               "tentativas": execucoes, "status": status,
                               "dur_s": dur})
    entry = {"objetivo": objetivo, "tipo": tipo, "status": status,
             "tentativas": execucoes, "dur_s": dur,
             "veredito": veredito, "problema": problema[:200],
             "skills": [s["name"] for s in sks],
             "aprovacao": (aprovacao if not exige_aprovacao else
                           f"{aprovacao}·{entregue}")}
    if plano_editado:
        entry["plano_editado"] = True
    if edit_snip:
        entry["entrega_editada"] = edit_snip
    record(cfg, entry, tid)
    # v4.0.0 (M6.5): loop de aprendizado — rascunho em staging, aprovação
    # SEMPRE do operador (nem AUTÔNOMO auto-aprova o próprio aprendizado)
    try:
        from .learning import observar
        dica = observar(cfg, objetivo, status, final, _n_tools[0])
        if dica:
            final += "\n\n" + dica
    except Exception:  # noqa: BLE001
        pass
    activity.log(cfg, "chat",
                 f"🎯 task {tid} {status} · {execucoes} execução(ões) · {dur}s")
    ev({"type": "brain", "stage": "🔍 revisor",
        "data": {"veredito": veredito, "problema": problema,
                 "chamadas": TRACE[-1:]}})
    ev({"type": "done", "message": final})   # o done verdadeiro, pós-tudo
    return final
