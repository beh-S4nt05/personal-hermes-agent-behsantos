"""Configuração central do Hermes Agent.

Prioridade: defaults <- data_dir/config.yaml <- flags da CLI.
O diretório de dados padrão é ~/.hermes (mude com HERMES_DATA_DIR ou --data-dir).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

APP_NAME = "hermes-agent"
VERSION = "2.2.3"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    # Ollama
    "ollama_url": "http://127.0.0.1:11434",
    "model": "hermes3:8b",
    "num_ctx": 8192,
    "temperature": 0.4,
    # Sobe o servidor Ollama automaticamente quando o agente precisar dele
    "auto_start_ollama": False,
    # Acesso à web (ferramentas web_search / web_fetch do agente e da GUI)
    "web_access": True,
    # Ditado por voz (Whisper local — requer: pip install faster-whisper)
    "stt_model": "base",          # tiny | base | small | medium | large-v3
    "stt_language": "pt",         # idioma do ditado (vazio = auto-detectar)
    "stt_autosend": True,         # envia a mensagem ao agente após ditar
    # Claude Code (2º agente): fala com o MESMO Ollama do Hermes (variáveis
    # ANTHROPIC_* aplicadas automaticamente ao rodar a CLI `claude`)
    "claude_use_ollama": True,
    "claude_model": "",            # modelo p/ o Claude Code (vazio = padrão dele)
    # Servidor web (GUI)
    "host": "127.0.0.1",
    "port": 8080,
    "auth_token": "",            # vazio = sem senha (use apenas em localhost!)
    # Agente
    "max_steps": 8,              # máx. de ciclos modelo -> ferramenta por tarefa
    "num_predict": 0,            # máx. tokens por resposta (0 = sem limite)
    "keep_alive": "30m",         # mantém o modelo na RAM entre mensagens (evita cold start)
    "cmd_timeout": 60,           # timeout (s) de cada comando shell
    "sandbox": True,             # restringe leitura/escrita de arquivos ao workspace
    "confirm_dangerous": True,   # pede confirmação no terminal para comandos arriscados
    "system_prompt_extra": "",   # instruções extras anexadas ao prompt de sistema
    # Conectores MCP (lista de {name, command, args, env} ou {name, url})
    "mcp_servers": [],
    "mcp_timeout": 120,          # timeout (s) de inicialização/chamadas MCP
    # Skills
    "skills_disabled": [],       # nomes de skills desabilitadas pela GUI
}

_INT_KEYS = {"max_steps", "cmd_timeout", "port", "num_ctx", "num_predict"}
_FLOAT_KEYS = {"temperature"}
_BOOL_KEYS = {"sandbox", "confirm_dangerous", "auto_start_ollama", "claude_use_ollama", "web_access", "stt_autosend"}
_STR_KEYS = {"ollama_url", "model", "host", "auth_token", "system_prompt_extra", "claude_model", "stt_model", "stt_language", "keep_alive"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _coerce(key: str, value):
    if value is None:
        return DEFAULTS[key]
    try:
        if key in _INT_KEYS:
            return int(value)
        if key in _FLOAT_KEYS:
            return float(value)
        if key in _BOOL_KEYS:
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on", "sim")
            return bool(value)
    except (TypeError, ValueError):
        return DEFAULTS[key]
    if key in _STR_KEYS:
        # nunca salva com espaços em branco nas pontas (causa de "invalid model name")
        value = str(value).strip()
        if key == "model" and not value:
            return DEFAULTS[key]  # modelo vazio é inválido no Ollama — volta ao padrão
        return value
    return value


class Config:
    """Acesso por atributos: cfg.model, cfg.max_steps, ..."""

    def __init__(self, data_dir: str | None = None, mock: bool | None = None):
        base = data_dir or os.environ.get("HERMES_DATA_DIR") or str(Path.home() / ".hermes")
        self.data_dir = Path(base).expanduser().resolve()
        self.mock = _env_flag("HERMES_MOCK") if mock is None else bool(mock)
        self.path = self.data_dir / "config.yaml"
        self._d = dict(DEFAULTS)
        self._load_file()

    # ------------------------------------------------------------------ io
    def _load_file(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in DEFAULTS:
                        self._d[k] = _coerce(k, v)
        except Exception as exc:  # arquivo corrompido não deve derrubar o agente
            print(f"[hermes] aviso: não consegui ler {self.path}: {exc}")

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            text = yaml.safe_dump(self._d, allow_unicode=True, sort_keys=True)
        except AttributeError as exc:
            raise RuntimeError(
                "PyYAML está quebrado neste ambiente (instalação incompleta — comum "
                "quando o projeto fica em disco NTFS). Conserte com: "
                "pip install --force-reinstall --no-cache-dir PyYAML"
            ) from exc
        self.path.write_text(text, encoding="utf-8")

    def update(self, changes: dict) -> None:
        for k, v in changes.items():
            if k in DEFAULTS:
                self._d[k] = _coerce(k, v)
        self.save()

    def as_dict(self) -> dict:
        return dict(self._d)

    # ------------------------------------------------------------ diretórios
    def ensure_dirs(self) -> None:
        for sub in ("workspace", "logs", "tasks/done", "conversations"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    @property
    def workdir(self) -> Path:
        wd = self.data_dir / "workspace"
        wd.mkdir(parents=True, exist_ok=True)
        return wd

    @property
    def logfile(self) -> Path:
        return self.data_dir / "logs" / "agent.log"

    @property
    def heartbeat_path(self) -> Path:
        return self.data_dir / "heartbeat.json"

    @property
    def spool_dir(self) -> Path:
        return self.data_dir / "tasks"

    @property
    def done_dir(self) -> Path:
        return self.data_dir / "tasks" / "done"

    @property
    def conversations_dir(self) -> Path:
        return self.data_dir / "conversations"

    @property
    def ollama_pidfile(self) -> Path:
        return self.data_dir / "ollama.pid"

    @property
    def skills_dirs(self) -> list[Path]:
        """Diretórios de skills: embutidas do projeto + do usuário."""
        return [PROJECT_ROOT / "skills", self.data_dir / "skills"]

    # ------------------------------------------------------------- dunder
    def __getattr__(self, key: str):
        d = self.__dict__.get("_d")
        if d is not None and key in d:
            return d[key]
        raise AttributeError(key)

    def __setattr__(self, key: str, value):
        d = self.__dict__.get("_d")
        if d is not None and key in DEFAULTS:
            d[key] = _coerce(key, value)
        else:
            super().__setattr__(key, value)
