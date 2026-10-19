"""Ditado por voz: transcrição local com Whisper (implementação faster-whisper).

- Opcional: `pip install faster-whisper` (~200 MB de dependências; roda na CPU
  com int8 — sem PyTorch, sem API paga).
- O modelo é baixado do Hugging Face no PRIMEIRO uso (ex.: 'base' ≈ 140 MB)
  e fica em cache; depois, tudo é 100% local.
- Endpoint: POST /api/stt (multipart campo 'audio') → {ok, text}.
"""

from __future__ import annotations

import io
import threading

_LOCK = threading.RLock()
_MODELS: dict[str, object] = {}

STT_MODELS = ("tiny", "base", "small", "medium", "large-v3")
STT_INSTALL_HINT = (
    "Transcrição de voz não está instalada. Ative com:\n"
    "  ./.venv/bin/pip install faster-whisper \"av<19\"\n"
    "(≈200 MB; o modelo 'base' ≈140 MB é baixado só no primeiro uso)"
)


def stt_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model(name: str):
    """Carrega (e cacheia) o modelo Whisper — download no primeiro uso."""
    with _LOCK:
        if name not in _MODELS:
            from faster_whisper import WhisperModel
            _MODELS[name] = WhisperModel(name, device="cpu", compute_type="int8")
        return _MODELS[name]


def transcribe(cfg, data: bytes) -> dict:
    """Transcreve o áudio (bytes webm/ogg/wav/mp3…) e devolve {ok, text}."""
    if not data:
        return {"ok": False, "msg": "nenhum áudio recebido"}
    if not stt_available():
        return {"ok": False, "msg": STT_INSTALL_HINT}

    name = str(getattr(cfg, "stt_model", "base") or "base")
    if name not in STT_MODELS:
        name = "base"
    lang = str(getattr(cfg, "stt_language", "pt") or "").strip() or None

    with _LOCK:  # uma transcrição por vez (CPU)
        model = _get_model(name)
        segments, info = model.transcribe(
            io.BytesIO(data), language=lang, beam_size=5, vad_filter=True,
        )
        text = " ".join(s.text.strip() for s in segments).strip()

    return {"ok": True, "text": text,
            "language": getattr(info, "language", lang) or lang,
            "model": name}
