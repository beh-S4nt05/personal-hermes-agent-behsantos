# -*- coding: utf-8 -*-
"""🔌 Provedores LLM externos — SOMENTE tiers gratuitos permanentes (v3.17.0).

Baseado no catálogo comunitário awesome-free-llm-apis (mantido/sincronizado
diariamente). Todos os endpoints aqui são compatíveis com a API OpenAI
(/v1/chat/completions), então UM único cliente cobre todos.

REGRA DE PRIVACIDADE DO OPERADOR (dura, não configurável):
- A MEMÓRIA do agente (fatos pessoais) NUNCA é enviada a provedores
  externos — a injeção de memória no prompt só acontece no Ollama local.
- Chaves de API moram em ~/.betterme/secrets/<provedor>.key (chmod 600) ou
  em variável de ambiente — JAMAIS em config.yaml, logs ou auditoria.
- O Betterme continua executando TUDO localmente (ferramentas, arquivos,
  comandos); apenas a INFerência do LLM pode ir a um provedor gratuito.
- Fallback: provedor externo falhou/sem internet → Ollama local na hora.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from .ollama_client import OllamaError

# ─────────────────────────────── registro (sem custo, sem cartão) ──
REGISTRY: dict[str, dict] = {
    "groq": {
        "base": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY", "model": "llama-3.1-8b-instant",
        "rpm": 30, "rpd": 14400,
        "nota": "o mesmo 8B do local, dezenas de vezes mais rápido",
    },
    "gemini": {
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY", "model": "gemini-2.5-flash",
        "rpm": 15, "rpd": 1500,
        "nota": "1M de contexto; tier grátis pode treinar (opt-out no site)",
    },
    "mistral": {
        "base": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY", "model": "mistral-small-latest",
        "rpm": 1, "rpd": None,
        "nota": "modo gratuito por padrão (créditos mensais)",
    },
    "openrouter": {
        "base": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "rpm": 20, "rpd": 50,
        "nota": "dezenas de modelos :free num registro só",
    },
    "llm7": {
        "base": "https://api.llm7.io/v1",
        "key_env": "LLM7_API_KEY", "model": "gpt-oss:20b",
        "sem_chave": True, "rpm": None, "rpd": None,
        "nota": "funciona SEM chave (anônimo) — cota diária mínima "
                "(1 chat completo do agente ≈2,6k tokens já estoura): "
                "use só para provar que funciona; para uso real, groq",
    },
    "zai": {
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "key_env": "ZAI_API_KEY", "model": "glm-4.7-flash",
        "rpm": 1, "rpd": None,
        "nota": "GLM-4.7-Flash reasoning; 1 requisição concorrente",
    },
    "cohere": {
        "base": "https://api.cohere.com/v2",
        "key_env": "COHERE_API_KEY", "model": "command-r7b",
        "rpm": 20, "rpd": None,
        "nota": "1.000 chamadas/mês; uso não comercial",
    },
    "omniroute": {
        # v6.5.0: gateway LOCAL (open-source, MIT) que roteia p/ pools
        # grátis — vários keyless. Sobe com `betterme omniroute start`.
        "base": "http://127.0.0.1:20128/v1",
        "key_env": "OMNIROUTE_API_KEY", "model": "auto",
        "gateway_local": True, "rpm": None, "rpd": None,
        "nota": "gateway local omniroute — pools grátis keyless "
                "(Pollinations/Cloudflare/…); betterme omniroute "
                "setup|start · chave local opcional (omniroute apikey)",
    },
}


def _secrets_dir(cfg) -> Path:
    d = Path(cfg.data_dir) / "secrets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def api_key(cfg, provedor: str) -> str:
    """Chave do provedor: env var → secrets/<p>.key. Vazia se não houver."""
    info = REGISTRY.get(provedor) or {}
    if info.get("sem_chave"):
        return os.environ.get(info.get("key_env") or "", "") or "anon"
    env = os.environ.get(info.get("key_env") or "")
    if env:
        return env
    try:
        arq = _secrets_dir(cfg) / f"{provedor}.key"
        return arq.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def salvar_key(cfg, provedor: str, key: str) -> Path:
    """Grava a chave em secrets/<p>.key (600). Nunca em config.yaml."""
    arq = _secrets_dir(cfg) / f"{provedor}.key"
    arq.write_text(key.strip() + "\n", encoding="utf-8")
    arq.chmod(0o600)
    return arq


# v6.3.0: roteador automático de cérebro — chave guardada = USADA.
# Prioridade = rapidez/estabilidade; llm7 (anônimo, cota mínima) fica
# só para uso manual explícito.
_AUTO_PRIORIDADE = ["groq", "mistral", "gemini", "openrouter",
                    "cohere", "zai", "omniroute"]


def melhor_provedor(cfg) -> str | None:
    """Melhor provedor COM CHAVE em secrets/ (None = nenhum).
    v6.5.0: omniroute (gateway local) entra se estiver RODANDO —
    chave opcional (pools keyless); fica por último (direto > gateway)."""
    for nome in _AUTO_PRIORIDADE:
        try:
            if nome == "omniroute":
                from . import omniroute as _om
                if _om.rodando(cfg):
                    return nome
                continue
            if api_key(cfg, nome):
                return nome
        except Exception:  # noqa: BLE001
            continue
    return None


def _norm_args(a):
    """arguments pode vir como string JSON (OpenAI) — normaliza p/ dict."""
    if isinstance(a, str):
        try:
            return json.loads(a)
        except ValueError:
            return {"_bruto": a}
    return a or {}


def dlp_messages(messages: list[dict]) -> list[dict]:
    """v6.4.2 (BLUEPRINT §5.4): TODO payload que sai da máquina passa
    pelo DLP mascarar() — em nível de TRANSPORTE, defesa em
    profundidade (quem já mascara não é afetado: é idempotente).
    Código, segredos, CPF e e-mails viram [CÓDIGO LOCAL]/[REDACTED]."""
    try:
        from .varredura import mascarar
    except Exception:  # noqa: BLE001
        return messages
    out = []
    for m in messages:
        try:
            conteudo = str(m.get("content") or "")
            limpo = mascarar(conteudo)
            if limpo != conteudo:
                m = {**m, "content": limpo}
        except Exception:  # noqa: BLE001
            pass
        out.append(m)
    return out


def payload_sensivel(messages: list[dict]) -> bool:
    """v6.4.2: o pedido contém código/segredo que o DLP censuraria?
    (D2: análise de código é SEMPRE local — o externo nem tenta.)"""
    try:
        from .varredura import mascarar
    except Exception:  # noqa: BLE001
        return False
    for m in messages:
        c = str(m.get("content") or "")
        if mascarar(c) != c:
            return True
    return False


class ExternalClient:
    """Cliente OpenAI-compatível (streaming SSE). Mesma interface de uso
    do OllamaClient: chat_stream/is_running/list_models."""

    is_external = True          # ← o Agent usa isto para NÃO enviar memória
    simulated = False

    def __init__(self, cfg, provedor: str, model: str = "",
                 _transport=None):
        info = REGISTRY.get(provedor)
        if not info:
            raise ValueError(f"provedor desconhecido: {provedor!r}")
        self.cfg = cfg
        self.provedor = provedor
        self.base = info["base"]
        self.model = model or info.get("model") or ""
        self._key = api_key(cfg, provedor)
        self._transport = _transport      # injetável nos testes

    # ------------------------------------------------------------ HTTP/SSE
    def _stream(self, payload: dict):
        headers = {"Content-Type": "application/json"}
        if self._key and self._key != "anon":
            headers["Authorization"] = f"Bearer {self._key}"
        if self._transport is not None:
            yield from self._transport(self.base + "/chat/completions",
                                       payload, headers)
            return
        r = requests.post(self.base + "/chat/completions", json=payload,
                          headers=headers, stream=True, timeout=180)
        if r.status_code != 200:
            trecho = (r.text or "")[:200]
            raise OllamaError(f"{self.provedor} HTTP {r.status_code}: {trecho}")
        yield from r.iter_lines(decode_unicode=True)

    def chat_stream(self, model, messages, tools=None, options=None,
                    cancel=None, keep_alive=None):
        # v3.17.1: o Agent passa cfg.model (nome de modelo OLLAMA, ex.
        # "hermes3:8b"); para provedores externos o modelo é SEMPRE o do
        # provedor (registro ou llm_model) — nomes Ollama não existem lá
        # e causavam HTTP 400 → fallback silencioso em TODO chat.
        payload = {"model": self.model or model,
                   "messages": dlp_messages(messages),   # D2 no transporte
                   "stream": True}
        if tools:
            payload["tools"] = tools
        opts = dict(options or {})
        if opts.get("num_predict"):
            payload["max_tokens"] = int(opts.pop("num_predict"))
        payload["temperature"] = opts.get("temperature", 0.4)
        conteudo, calls_idx = "", {}
        for raw in self._stream(payload):
            if cancel is not None and cancel.is_set():
                return
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            escolhas = obj.get("choices") or []
            if not escolhas:
                continue
            delta = escolhas[0].get("delta") or {}
            tok = delta.get("content") or ""
            if tok:
                conteudo += tok
                yield {"message": {"content": tok}}
            for tc in delta.get("tool_calls") or []:
                idx = int(tc.get("index") or 0)
                acc = calls_idx.setdefault(idx, {"id": tc.get("id") or "",
                                                 "type": "function",
                                                 "function": {"name": "",
                                                              "arguments": ""}})
                fn = tc.get("function") or {}
                if fn.get("name"):
                    acc["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    acc["function"]["arguments"] += fn["arguments"]
        # tool_calls completos no fim (argumentos normalizados p/ dict)
        if calls_idx:
            calls = [calls_idx[i] for i in sorted(calls_idx)]
            for c in calls:
                c["function"]["arguments"] = _norm_args(
                    c["function"].get("arguments"))
            yield {"message": {"content": "", "tool_calls": calls}}

    def _get(self, caminho: str):
        headers = {}
        if self._key and self._key != "anon":
            headers["Authorization"] = f"Bearer {self._key}"
        return requests.get(self.base + caminho, headers=headers, timeout=30)

    def is_running(self) -> bool:
        try:
            return self._get("/models").status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def list_models(self) -> list[str]:
        try:
            dados = self._get("/models").json()
            return sorted(str(m.get("id")) for m in dados.get("data", []))
        except Exception:  # noqa: BLE001
            return []


class FallbackClient:
    """Externo primeiro, local se o externo falhar ANTES de token algum.
    A execução (ferramentas) é sempre local — só a inferência muda."""

    is_external = True          # memória fica fora enquanto puder ser externo
    simulated = False

    def __init__(self, externo: ExternalClient, local):
        self.externo = externo
        self.local = local
        self.cfg = externo.cfg
        self.usou_fallback = False

    def _nota(self, motivo: str) -> None:
        try:
            from . import activity
            activity.log(self.cfg, "llm",
                         f"↩ provedor externo falhou ({motivo[:90]}) — "
                         "usando Ollama local")
        except Exception:  # noqa: BLE001
            pass

    def chat_stream(self, model, messages, tools=None, options=None,
                    cancel=None, keep_alive=None):
        # v6.4.2 (D2 — BLUEPRINT §5.2): código/segredo no pedido NUNCA
        # vai ao pool grátis — análise de código é LOCAL. O externo nem
        # é tentado (e o transporte ainda mascara, defesa em profundidade)
        if payload_sensivel(messages):
            self.usou_fallback = True
            self._nota("D2: código/segredo no pedido — cérebro local")
            yield from self.local.chat_stream(
                model, messages, tools=tools, options=options,
                cancel=cancel, keep_alive=keep_alive)
            return
        # v6.4.2: UM único stream — antes eram duas chamadas ao externo
        # (next() numa, yield from noutra = 2 requisições/tokens 2×)
        stream = self.externo.chat_stream(
            model, messages, tools=tools, options=options,
            cancel=cancel, keep_alive=keep_alive)
        try:
            primeiro = next(stream)
        except StopIteration:
            return
        except OllamaError as exc:
            self.usou_fallback = True
            self._nota(str(exc))
            yield from self.local.chat_stream(
                model, messages, tools=tools, options=options,
                cancel=cancel, keep_alive=keep_alive)
            return
        except Exception as exc:  # noqa: BLE001
            self.usou_fallback = True
            self._nota(f"{exc.__class__.__name__}: {exc}")
            yield from self.local.chat_stream(
                model, messages, tools=tools, options=options,
                cancel=cancel, keep_alive=keep_alive)
            return
        yield primeiro
        yield from stream

    def is_running(self) -> bool:
        return self.externo.is_running() or self.local.is_running()

    def list_models(self) -> list[str]:
        m = self.externo.list_models()
        return m if m else self.local.list_models()


def testar(cfg, provedor: str, model: str = "",
            _transport=None) -> dict:
    """Ping + 1 completion mínimo real (relatório para o operador).
    v6.5.0: _transport injetável (testes sem rede)."""
    t0 = time.time()
    try:
        cli = ExternalClient(cfg, provedor, model, _transport=_transport)
    except ValueError as exc:
        return {"ok": False, "msg": str(exc)}
    key = api_key(cfg, provedor)
    gateway = bool(REGISTRY.get(provedor, {}).get("gateway_local"))
    if not key and not gateway:      # omniroute keyless é válido
        return {"ok": False,
                "msg": f"sem chave para {provedor} — rode: betterme provider "
                       f"set {provedor} (ou exporte {REGISTRY[provedor].get('key_env')})"}
    if _transport is None and not cli.is_running():
        return {"ok": False, "msg": f"{provedor} não respondeu ao ping"}
    pedaco = []
    try:
        for ch in cli.chat_stream(cli.model, [{"role": "user",
                                               "content":
                                               "responda apenas: ok"}]):
            t = (ch.get("message") or {}).get("content")
            if t:
                pedaco.append(t)
    except Exception as exc:  # noqa: BLE001 — erro vira relatório, não crash
        return {"ok": False,
                "msg": f"{provedor} falhou: {str(exc)[:140]}"}
    dt = round(time.time() - t0, 1)
    texto = "".join(pedaco).strip()
    if not texto:
        return {"ok": False, "msg": f"{provedor} não gerou resposta"}
    return {"ok": True, "msg": f"{provedor} · {cli.model} · respondeu "
                               f"{texto[:30]!r} em {dt}s"}


def testar_todos(cfg) -> list[dict]:
    """v6.5.0: testa TODOS os provedores usáveis — os com chave salva,
    o llm7 (anônimo) e o omniroute (se rodando) — 1 completion real
    cada. Relatório honesto p/ o operador saber o que está 100%."""
    out = []
    for nome in REGISTRY:
        try:
            if nome == "omniroute":
                from . import omniroute as _om
                if _om.rodando(cfg):
                    r = testar(cfg, nome)
                    out.append({"nome": nome, **r})
                continue
            if nome == "llm7" or api_key(cfg, nome):
                r = testar(cfg, nome)
                out.append({"nome": nome, **r})
        except Exception as exc:  # noqa: BLE001
            out.append({"nome": nome, "ok": False,
                        "msg": f"falhou: {exc.__class__.__name__}"})
    return out


# v6.5.0: onde conseguir cada chave (onboarding em 1 comando)
GUIAS = {
    "groq": ("console.groq.com/keys",
             "conta grátis (sem cartão) → API Keys → Create API Key — "
             "14.400 req/dia, o 8B dezenas de vezes mais rápido"),
    "mistral": ("console.mistral.ai/api-keys",
                "conta grátis → API Keys — ~1B tokens/mês no tier free"),
    "gemini": ("aistudio.google.com/apikey",
               "conta Google → Get API Key — 1M de contexto, 1.500 req/dia"),
    "openrouter": ("openrouter.ai/keys",
                   "conta grátis → Keys — dezenas de modelos :free"),
    "cohere": ("dashboard.cohere.com/api-keys",
               "conta grátis → API Keys — 1.000 chamadas/mês"),
    "zai": ("open.bigmodel.cn/usercenter/apikeys",
            "conta → API Keys — GLM-4.7-Flash grátis"),
    "llm7": ("api.llm7.io",
             "funciona SEM chave (anônimo) — cota diária mínima"),
    "omniroute": ("(local)",
                  "betterme omniroute setup && betterme omniroute start "
                  "— pools keyless, sem conta nenhuma"),
}
