"""Especialistas — v4.0.0 (M6), o coração da nova filosofia (ADR-001).

Um especialista = skill certa + contexto limpo do caso + veredito
estruturado COM EVIDÊNCIA. O cérebro (pipeline 🎯→⚡→🔍) decide quando
invocar; o especialista PROPÕE, nunca escreve no disco (single-writer).

8 regras duras implementadas aqui:
  R2 stateless/escopado · R3 veredito com evidência validada NO DISCO ·
  R6 privacidade: caso vai DLP-mascarado a provedores externos (D2) ·
  R7 pool de provedores GRATUITOS com fallback local · R8 exame de
  competência com cache; reprovado = degrada (nunca quebra) ·
  auditoria de cada invocação.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# ------------------------------------------------------------- catálogo
ESPECIALISTAS: dict[str, dict] = {
    "revisor": {
        "skill": "code-review",
        "missao": "revisar o trabalho descrito no caso quanto a "
                  "conformidade com o objetivo e qualidade técnica",
        "pergunta_exame": "revise: função soma(a,b) retornou a-b para "
                          "a=2,b=1 — o resultado deveria ser 3",
    },
    "debugger": {
        "skill": "debug-sistematico",
        "missao": "diagnosticar a causa raiz do sintoma descrito no caso, "
                  "em 4 fases (reproduzir, isolar, hipótese única, verificar)",
        "pergunta_exame": "o teste testa_soma falha com AssertionError na "
                          "linha 88 depois que o finally apaga a pasta — "
                          "qual a causa raiz provável?",
    },
    "pesquisador": {
        "skill": "pesquisa-web",
        "missao": "sintetizar informações de múltiplas fontes citadas no "
                  "caso em uma recomendação com fontes",
        "pergunta_exame": "resuma as vantagens e riscos citados de usar "
                          "TF-IDF em vez de embeddings no caso descrito",
    },
    "seguranca": {
        "skill": "",                     # kit inline (checklist próprio)
        "missao": "auditar o caso quanto a segredos expostos, injeção, "
                  "autenticação e configuração arriscada",
        "pergunta_exame": "o log do caso contém 'Authorization: Bearer "
                          "eyJhbGciOi' — isso é aceitável?",
    },
}

KIT_SEGURANCA = """\
# Especialista segurança — checklist
1. Segredos: chaves/tokens/senhas expostos no caso? (padrões gsk_, sk-,
   AIza, gh[pousr]_, AKIA, Bearer, BEGIN PRIVATE KEY, senha hardcoded)
2. Injeção: instruções suspeitas embutidas em dados lidos de fora?
3. Autenticação/autorização: verificado quem pede antes de agir?
4. Configuração: permissões de arquivo, network exposta, eval/exec?
5. Dados pessoais: CPF/e-mail/nome de terceiro em artefato público?
Veredito sempre com: achado, gravidade e correção proposta."""

_CAMPOS = ("diagnostico", "acao_proposta", "evidencia", "confianca")


# ------------------------------------------------------------- contrato
def validar(veredito: dict) -> tuple[bool, str]:
    """Schema + confiança mínima (R3)."""
    if not isinstance(veredito, dict):
        return False, "veredito não é objeto"
    v = veredito.get("veredito")
    if not isinstance(v, dict):
        return False, "falta o objeto 'veredito'"
    for c in _CAMPOS:
        if c not in v:
            return False, f"falta o campo '{c}'"
    if not str(v.get("diagnostico", "")).strip():
        return False, "diagnóstico vazio"
    if not str(v.get("acao_proposta", "")).strip():
        return False, "ação proposta vazia"
    ev = v.get("evidencia")
    if not isinstance(ev, list) or not ev:
        return False, "sem evidência — veredito sem valor (regra 3)"
    for e in ev:
        if not isinstance(e, dict) or not str(e.get("trecho", "")).strip():
            return False, "evidência sem trecho citado"
    try:
        conf = float(v.get("confianca", 0))
    except (TypeError, ValueError):
        return False, "confiança não é número"
    if conf < 0.5:
        return False, f"confiança {conf} < 0.5"
    return True, "ok"


def checar_evidencia(veredito: dict, raiz: Path | None = None) \
        -> tuple[bool, str]:
    """Risco #7 do pre-mortem: o arquivo:linha citado EXISTE e contém o
    trecho (checagem determinística local e barata)."""
    raiz = Path(raiz) if raiz else Path.cwd()
    for e in (veredito.get("veredito") or {}).get("evidencia") or []:
        arq = str(e.get("arquivo", "")).strip()
        trecho = str(e.get("trecho", "")).strip()
        if not arq:                       # evidência sem arquivo (ex.: web)
            continue
        p = Path(arq) if Path(arq).is_absolute() else raiz / arq
        if not p.is_file():
            return False, f"arquivo citado não existe: {arq}"
        try:
            linhas = p.read_text(encoding="utf-8",
                                 errors="replace").splitlines()
        except OSError as exc:
            return False, f"ilegível: {arq} ({exc})"
        lin = int(e.get("linha") or 0)
        if lin and (lin < 1 or lin > len(linhas)):
            return False, f"linha {lin} fora do arquivo {arq}"
        janela = "\n".join(linhas[max(0, lin - 2):lin + 1]) if lin \
            else "\n".join(linhas)
        if trecho and trecho[:80] not in janela:
            return False, (f"trecho citado não está em {arq}"
                           f"{':' + str(lin) if lin else ''}")
    return True, "ok"


# ------------------------------------------------------------- prompts
def _skill_body(cfg, nome: str) -> str:
    kit = ESPECIALISTAS[nome]
    if kit["skill"]:
        for d in getattr(cfg, "skills_dirs", []):
            p = Path(d) / kit["skill"] / "SKILL.md"
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8")[:4000]
                except OSError:
                    pass
    return KIT_SEGURANCA if nome == "seguranca" else ""


def _system_prompt(cfg, nome: str) -> str:
    kit = ESPECIALISTAS[nome]
    return (
        "Você é um ESPECIALISTA do Hermes, invocado pelo cérebro do agente "
        "para um caso pontual. Missão: " + kit["missao"] + ".\n\n"
        "Responda SOMENTE com um objeto JSON válido, sem texto fora dele:\n"
        '{"especialista": "' + nome + '", "caso": "<resumo em 1 linha>",\n'
        ' "veredito": {"diagnostico": "...", "acao_proposta": "...",\n'
        '  "evidencia": [{"arquivo": "caminho", "linha": 0, '
        '"trecho": "trecho real citado"}], "confianca": 0.0}}\n\n'
        "Regras: cite como evidência SOMENTE o que está no caso (arquivo, "
        "linha, trecho, saída). Sem evidência real, declare confianca < 0.5 "
        "e um diagnóstico honesto. Ação proposta = o que o cérebro deve "
        "fazer — você NUNCA executa.\n\n" + _skill_body(cfg, nome)
    )[:6000]


def _extrair_json(texto: str) -> dict | None:
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


# ------------------------------------------------------------- pool (R7)
class Pool:
    """Provedores gratuitos com chave (+ anônimos) e fallback local.
    Token bucket por provedor (groq 30 RPM)."""

    def __init__(self, cfg, _extra: list | None = None):
        self.cfg = cfg
        self._calls: dict[str, list[float]] = {}
        self._extra = _extra or []        # [(nome, cliente)] p/ testes

    def _limite_rpm(self, nome: str) -> int:
        try:
            from .llm_providers import REGISTRY
            rpm = REGISTRY.get(nome, {}).get("rpm")
            return int(rpm) if rpm else 240
        except Exception:  # noqa: BLE001
            return 240

    def _pode(self, nome: str) -> bool:
        agora = time.time()
        janela = [t for t in self._calls.get(nome, []) if agora - t < 60]
        self._calls[nome] = janela
        return len(janela) < self._limite_rpm(nome)

    def candidatos(self) -> list[tuple[str, object]]:
        if self._extra:
            return list(self._extra)
        out: list[tuple[str, object]] = []
        try:
            from .llm_providers import REGISTRY, api_key, ExternalClient
            for nome in REGISTRY:
                if REGISTRY[nome].get("sem_chave") or api_key(self.cfg, nome):
                    out.append((nome, ExternalClient(self.cfg, nome)))
        except Exception:  # noqa: BLE001
            pass
        return out

    def invocar(self, messages: list[dict]):
        """Devolve (nome_provedor, texto) — tenta externos e cai no local."""
        for nome, cli in self.candidatos():
            if not self._pode(nome):
                continue
            try:
                self._calls.setdefault(nome, []).append(time.time())
                partes = []
                for ch in cli.chat_stream("", messages):
                    t = (ch.get("message") or {}).get("content") or ""
                    if t:
                        partes.append(t)
                texto = "".join(partes).strip()
                if texto:
                    return nome, texto
            except Exception:  # noqa: BLE001
                continue
        # fallback local (mock em testes, Ollama na máquina do operador)
        from .ollama_client import get_client
        local = get_client(self.cfg)
        partes = []
        for ch in local.chat_stream("", messages):
            t = (ch.get("message") or {}).get("content") or ""
            if t:
                partes.append(t)
        return "local", "".join(partes).strip()


# ------------------------------------------------------------- invocar
def invocar(cfg, nome: str, caso: str, _pool=None, raiz: Path | None = None,
            pular_exame: bool = False) -> dict:
    """Cérebro → especialista. Devolve dict auditável:
    {ok, veredito, provedor, latencia_s, motivo}."""
    t0 = time.time()
    resultado = {"especialista": nome, "ok": False, "veredito": None,
                 "provedor": None, "latencia_s": 0.0, "motivo": ""}
    if nome not in ESPECIALISTAS:
        resultado["motivo"] = (f"especialista desconhecido: {nome!r} — "
                               f"disponíveis: {', '.join(ESPECIALISTAS)}")
        return resultado
    # R8: exame de competência (a menos que bypass explícito)
    if not pular_exame:
        ex = exame(cfg, nome)
        if not ex.get("aprovado"):
            resultado["motivo"] = (f"exame de competência reprovado "
                                   f"({ex.get('motivo', '')}) — especialista "
                                   f"desativado; pipeline segue sem ele")
            _auditar(cfg, resultado)
            return resultado
    pool = _pool or Pool(cfg)
    mensagens = [{"role": "system", "content": _system_prompt(cfg, nome)}]
    # R6/D2: provedores externos NUNCA recebem código/segredos do caso
    caso_ext = None
    try:
        from .varredura import mascarar
        caso_ext = mascarar(caso)
    except Exception:  # noqa: BLE001
        caso_ext = caso

    provedor, texto = pool.invocar(mensagens + [
        {"role": "user", "content": "CASO:\n" + caso_ext}])
    resultado["provedor"] = provedor
    resultado["latencia_s"] = round(time.time() - t0, 2)
    v = _extrair_json(texto or "")
    if v is None:
        resultado["motivo"] = ("veredito inválido (sem JSON) — descartado")
        _auditar(cfg, resultado)
        return resultado
    ok, motivo = validar(v)
    if not ok:
        resultado["motivo"] = f"veredito reprovado: {motivo}"
        _auditar(cfg, resultado)
        return resultado
    ok2, motivo2 = checar_evidencia(v, raiz)
    if not ok2:
        resultado["motivo"] = f"evidência não confere: {motivo2}"
        _auditar(cfg, resultado)
        return resultado
    resultado.update({"ok": True, "veredito": v, "motivo": "ok"})
    _auditar(cfg, resultado)
    return resultado


def _auditar(cfg, resultado: dict) -> None:
    try:
        from . import activity
        activity.log(cfg, "especialista",
                     f"{resultado.get('especialista')} · "
                     f"{resultado.get('provedor')} · "
                     f"{'✔' if resultado.get('ok') else '✖'} "
                     f"{resultado.get('motivo', '')[:90]}",
                     detail=f"latencia_s={resultado.get('latencia_s')}")
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------- exames R8
def _arquivo_exames(cfg) -> Path:
    return Path(cfg.data_dir) / "especialistas-exames.json"


_EXAME_REQUISITO = {          # palavra que PRECISA aparecer no veredito
    "revisor": "soma",
    "debugger": "finally",
    "pesquisador": "",
    "seguranca": "",
}


def exame(cfg, nome: str, _pool=None, forcar: bool = False) -> dict:
    """Casos-ouro com resposta conhecida; resultado em cache (risco #14)."""
    arq = _arquivo_exames(cfg)
    cache: dict = {}
    try:
        cache = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    chave = f"{nome}"
    if not forcar and cache.get(chave, {}).get("aprovado"):
        return cache[chave]
    caso = ESPECIALISTAS[nome]["pergunta_exame"]
    r = invocar(cfg, nome, caso, _pool=_pool, pular_exame=True)
    aprovado = bool(r.get("ok"))
    if aprovado and _EXAME_REQUISITO.get(nome):
        blob = json.dumps(r.get("veredito") or {}, ensure_ascii=False).lower()
        aprovado = _EXAME_REQUISITO[nome].lower() in blob
    entry = {"aprovado": aprovado, "motivo": r.get("motivo", ""),
             "provedor": r.get("provedor"), "ts": time.time()}
    cache[chave] = entry
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    except OSError:
        pass
    return entry


def disponiveis(cfg) -> list[dict]:
    """Estado de cada especialista (exame incluso) para CLI/GUI."""
    out = []
    for nome, kit in ESPECIALISTAS.items():
        try:
            ex = exame(cfg, nome)
        except Exception:  # noqa: BLE001
            ex = {"aprovado": False, "motivo": "erro no exame"}
        out.append({"nome": nome, "missao": kit["missao"],
                    "skill": kit["skill"] or "(kit interno)",
                    "exame": ex})
    return out
