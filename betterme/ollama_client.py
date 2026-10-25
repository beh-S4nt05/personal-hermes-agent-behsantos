"""Cliente para a API REST do Ollama (+ cliente simulado para demonstração).

Quando o Betterme roda sem Ollama instalado (modo demonstração / BETTERME_MOCK=1),
um MockOllamaClient assume o lugar: ele responde em português, dispara chamadas
reais de ferramenta (sys_info, list_dir, run_command) e deixa claro que é uma
simulação — perfeito para testar a GUI e o loop do agente sem baixar modelos.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Callable, Iterator

import requests

MOCK_BANNER = "[modo demonstração — Ollama simulado, sem modelo real]"


class OllamaError(Exception):
    """Erro de comunicação/execução no Ollama."""


class OllamaClient:
    """Cliente fino e sem dependências externas além do `requests`."""

    simulated = False

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ----------------------------------------------------------- status
    def is_running(self) -> bool:
        try:
            requests.get(f"{self.base_url}/api/version", timeout=3).raise_for_status()
            return True
        except requests.RequestException:
            return False

    def version(self) -> str | None:
        try:
            r = requests.get(f"{self.base_url}/api/version", timeout=3)
            r.raise_for_status()
            return r.json().get("version")
        except Exception:
            return None

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return [m.get("name", "?") for m in r.json().get("models", [])]
        except Exception:
            return []

    # -------------------------------------------------- info do servidor
    def model_details(self) -> list[dict]:
        """Modelos instalados com tamanho e data (API /api/tags completa)."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception:
            return []

    def ps(self) -> list[dict]:
        """Modelos carregados em memória/VRAM neste momento (API /api/ps)."""
        try:
            r = requests.get(f"{self.base_url}/api/ps", timeout=5)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception:
            return []

    def delete_model(self, model: str) -> None:
        r = requests.delete(f"{self.base_url}/api/delete", json={"model": model}, timeout=30)
        if r.status_code >= 400:
            raise OllamaError(f"falha ao remover {model}: HTTP {r.status_code} {r.text[:150]}")

    def test_generation(self, model: str) -> dict:
        """Geração mínima para validar o caminho completo (mede a latência)."""
        t0 = time.time()
        r = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": model,
                "prompt": "Responda apenas com a palavra: ok",
                "stream": False,
                "options": {"num_predict": 4, "temperature": 0},
            },
            timeout=300,
        )
        if r.status_code >= 400:
            raise OllamaError(f"teste de geração falhou: HTTP {r.status_code} {r.text[:150]}")
        data = r.json()
        return {"latency_s": round(time.time() - t0, 2),
                "response": (data.get("response") or "")[:80]}

    # ------------------------------------------------------------- chat
    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        options: dict | None = None,
        cancel=None,
        keep_alive: str | int | None = None,
    ) -> Iterator[dict]:
        """Gera chunks no formato da API /api/chat (stream=true).

        - `cancel` (threading.Event): interrompe a geração a qualquer momento.
        - Falhas transitórias de conexão são retentadas (2x) com backoff.
        - Queda no meio do stream vira erro claro (resposta parcial preservada).
        """
        payload: dict = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if options:
            payload["options"] = options
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive  # ex.: "30m" evita descarregar

        r = None
        for attempt in range(3):
            if cancel is not None and cancel.is_set():
                return
            try:
                r = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    stream=True,
                    timeout=(15, self.timeout),
                )
                break
            except requests.RequestException as exc:
                # retenta apenas se o servidor segue de pé (falha transitória)
                if attempt < 2 and self.is_running():
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise OllamaError(
                    f"não consegui falar com o Ollama em {self.base_url} "
                    f"({exc.__class__.__name__}: {exc}). Verifique: betterme ollama status"
                ) from exc
        if r is None or r.status_code != 200:
            detail = (r.text[:400] if r is not None else "sem resposta")
            raise OllamaError(f"Ollama respondeu {getattr(r, 'status_code', '???')}: {detail}")

        try:
            for line in r.iter_lines():
                if cancel is not None and cancel.is_set():
                    return
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise OllamaError(str(chunk["error"]))
                yield chunk
                if chunk.get("done"):
                    return
        except requests.RequestException as exc:
            raise OllamaError(
                f"a conexão com o Ollama caiu no meio da resposta "
                f"({exc.__class__.__name__}) — o texto acima pode estar incompleto"
            ) from exc

    def pull(self, model: str, on_progress: Callable[[dict], None] | None = None,
             cancel=None) -> None:
        """Baixa um modelo via /api/pull reportando progresso (cancelável)."""
        try:
            r = requests.post(
                f"{self.base_url}/api/pull",
                json={"model": model, "stream": True},
                stream=True,
                timeout=(10, 60 * 60 * 4),
            )
            r.raise_for_status()
            try:
                for line in r.iter_lines():
                    if cancel is not None and cancel.is_set():
                        raise OllamaError(f"download de {model} cancelado pelo operador")
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise OllamaError(data["error"])
                    if on_progress:
                        on_progress(data)
            finally:
                r.close()
        except requests.RequestException as exc:
            raise OllamaError(f"falha ao baixar {model}: {exc}") from exc


# ----------------------------------------------------------------------------
# Modo demonstração (mock)
# ----------------------------------------------------------------------------

_GENERIC = [
    (
        "Olá! Sou o **Betterme**, agente Linux — mas neste momento estou no "
        f"{MOCK_BANNER}.\n\n"
        "Ainda assim, meu loop de ferramentas é real: posso inspecionar o sistema, "
        "listar arquivos do workspace e executar comandos. Experimente pedir "
        "«informações do sistema», «listar arquivos do workspace» ou «que horas são?»."
    ),
    (
        f"Estou respondendo em modo simulado {MOCK_BANNER}, então esta resposta é "
        "gerada localmente sem LLM.\n\n"
        "Quando o Ollama estiver ligado com um modelo Betterme (`betterme ollama status`), "
        "as respostas virão de verdade do modelo. Minhas ferramentas (comandos shell, "
        "arquivos, diagnóstico) já funcionam agora — teste: «mostre informações do sistema»."
    ),
]


class MockOllamaClient:
    """Simula o Ollama para demonstração da GUI e do loop do agente."""

    simulated = True

    def is_running(self) -> bool:
        return True

    def version(self) -> str:
        return "simulado"

    def list_models(self) -> list[str]:
        return ["hermes3:8b", "hermes3:3b"]

    # ------------------------------------------------------------- chat
    def chat_stream(self, model, messages, tools=None, options=None, cancel=None,
                    keep_alive=None):
        msg = self._fake_message(messages, tools)
        if msg.get("tool_calls"):
            yield {"message": msg, "done": True, "done_reason": "stop"}
            return
        content = msg.get("content", "")
        words = content.split(" ")
        if content:  # simula o tempo de o modelo "pensar" (deixa o loading visível)
            time.sleep(float(os.environ.get("BETTERME_MOCK_DELAY", "1.2")))
        for i, w in enumerate(words):
            if cancel is not None and cancel.is_set():
                return
            piece = w + (" " if i < len(words) - 1 else "")
            yield {"message": {"role": "assistant", "content": piece}, "done": False}
            time.sleep(0.012)
        yield {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}

    def pull(self, model, on_progress=None, cancel=None):
        """Download simulado com barra visível (e cancelável) na demo."""
        total, step = 12_000_000_000, 1_000_000_000
        for i in range(1, 13):
            if cancel is not None and cancel.is_set():
                if on_progress:
                    on_progress({"status": "cancelando…"})
                return
            if on_progress:
                on_progress({"status": "baixando (simulado)", "total": total,
                             "completed": min(i * step, total)})
            time.sleep(0.35)

    # --------------------------------------------------------- roteiro
    def _fake_message(self, messages: list[dict], tools=None) -> dict:
        last = messages[-1] if messages else {}

        # Depois que a ferramenta rodou, devolve um resumo honesto do resultado.
        if last.get("role") == "tool":
            name = last.get("name", "ferramenta")
            out = str(last.get("content", "")).strip()
            if len(out) > 900:
                out = out[:900] + "\n…"
            return {
                "role": "assistant",
                "content": (
                    f"Pronto! Executei a ferramenta `{name}` e este foi o resultado real "
                    f"desta máquina:\n\n```\n{out}\n```\n\n"
                    f"*(resposta de demonstração {MOCK_BANNER}; com o Ollama ligado, o "
                    "modelo Betterme analisaria o resultado acima.)*"
                ),
            }

        tool_names = [t["function"]["name"] for t in (tools or [])]
        conv = [m for m in messages if m.get("role") in ("user", "assistant")]
        text = " ".join(str(m.get("content", "")) for m in conv[-4:]).lower()

        # Conector MCP do Figma: pedidos de design/protótipo/telas
        figma_create = next((n for n in tool_names if "create_design" in n), None)
        if figma_create and re.search(
            r"figma|design|prot[óo]tipo|mockup|wireframe|interface|tela|ui\b|app\b|aplicativo",
            text,
        ):
            pedido = str(conv[-1].get("content", "")) if conv else "aplicativo"
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": figma_create,
                        "arguments": {
                            "name": " ".join(pedido.split()[:4]) or "Novo App",
                            "description": pedido[:200],
                            "screens": ["home", "detalhe", "configuracoes"],
                        },
                    }
                }],
            }

        if tool_names:
            if re.search(r"sistema|mem[óo]ria|disco|uptime|kernel|cpu|vers[ãa]o|info|diagn[óo]stico|df\b", text):
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "sys_info", "arguments": {}}}],
                }
            if re.search(r"listar|arquivos|diret[óo]rio|pasta|ls\b|workspace", text):
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "list_dir", "arguments": {"path": "."}}}],
                }
            if re.search(r"que horas|hora atual|data de hoje|dia de hoje|date\b|rel[óo]gio", text):
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "run_command", "arguments": {"command": "date"}}}],
                }
            if re.search(r"execut|comando|rodar|shell|bash", text):
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "run_command", "arguments": {"command": "echo Betterme Agent diz olá; uname -s"}}}],
                }

        return {"role": "assistant", "content": random.choice(_GENERIC)}


_AVISO_AUTO_FEITO = False      # avisa 1x por processo


def timeout_resposta(cfg) -> int:
    """v6.4.0 (DRY): timeout das respostas LONGAS do modelo local
    (revisão de diff, juiz da arena, gateway) — 5× o timeout de comando
    + 120 s de folga. Política única, antes triplicada em código."""
    return int(getattr(cfg, "cmd_timeout", 60) or 60) * 5 + 120


def get_client(cfg):
    """Fábrica: devolve o cliente mock quando cfg.mock for verdadeiro.
    v3.17.0: com llm_provider externo configurado, devolve externo com
    FALLBACK local (inferência externa; ferramentas continuam locais)."""
    if cfg.mock:
        return MockOllamaClient()
    local = OllamaClient(cfg.ollama_url,
                        timeout=timeout_resposta(cfg))
    provedor = str(getattr(cfg, "llm_provider", "local") or "local")
    # v6.3.0: ROTEADOR AUTOMÁTICO — nenhuma config externa + chave
    # guardada = o cérebro USA o provedor rápido (fallback local na
    # falha). 'betterme provider off' desliga (auto_provider=False).
    if (provedor == "local"
            and getattr(cfg, "auto_provider", True)):
        try:
            from .llm_providers import melhor_provedor
            auto = melhor_provedor(cfg)
            if auto:
                provedor = auto
                global _AVISO_AUTO_FEITO
                if not _AVISO_AUTO_FEITO:
                    _AVISO_AUTO_FEITO = True
                    try:
                        from . import activity
                        activity.log(
                            cfg, "cerebro",
                            f"🧠 roteador automático: usando {auto} "
                            "(chave detectada; fallback local na falha; "
                            "'betterme provider off' volta ao 100% local)")
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
    if provedor != "local":
        try:
            from .llm_providers import REGISTRY, ExternalClient, FallbackClient
            if provedor in REGISTRY:
                ext = ExternalClient(cfg, provedor,
                                     str(getattr(cfg, "llm_model", "")
                                         or REGISTRY[provedor]["model"]))
                return FallbackClient(ext, local)
        except Exception:  # noqa: BLE001
            pass
    return local
