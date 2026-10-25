# -*- coding: utf-8 -*-
"""🎙️ Multimodal local — v4.6.0 (PR #9, E5).

`betterme audio|video transcrever <arquivo>`: ffmpeg extrai o áudio →
whisper.cpp LOCAL transcreve (com timestamps) → a transcrição ENTRA na
biblioteca RAG (fonte citada, busca textual).

Tudo LOCAL (local-first): nenhum byte de áudio/vídeo sai da máquina —
sem APIs de nuvem, sem custos, sem upload. Modelos ficam em
`<data_dir>/models/` (padrão ggml-base.bin).

Degradação HONESTA: sem ffmpeg ou sem whisper.cpp instalados → mensagem
clara de como instalar (nunca quebra, nunca mente).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# [00:00:00.000 --> 00:00:04.000]  texto  (saída do whisper.cpp)
_SEG = re.compile(
    r"\[(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*-->\s*"
    r"(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\]\s*(.*)")

def _msg_ffmpeg() -> str:
    from .plataforma import hint
    return ("ffmpeg não encontrado — instale: " + hint("ffmpeg")
            + " (ou aponte o caminho com --ffmpeg)")
_MSG_WHISPER = ("whisper.cpp não encontrado — baixe/compile o binário "
                "(github.com/ggerganov/whisper.cpp) e aponte com "
                "--whisper; modelo ggml-*.bin em <data>/models/")


def _which(bin_ou_caminho: str | None) -> str | None:
    if not bin_ou_caminho:
        return None
    p = Path(bin_ou_caminho)
    if p.is_absolute():
        return str(p) if p.exists() else None
    return shutil.which(bin_ou_caminho)


def modelo_path(cfg, nome: str = "") -> Path:
    """Modelo whisper.cpp em <data_dir>/models/ (default ggml-base.bin)."""
    d = Path(cfg.data_dir) / "models"
    return d / (nome or "ggml-base.bin")


def transcrever(cfg, caminho, ffmpeg_bin: str | None = None,
                whisper_bin: str | None = None,
                modelo: str = "") -> dict:
    """Pipeline local: vídeo/áudio → wav 16 kHz mono → texto com
    timestamps → biblioteca RAG. Devolve {ok, msg, ...}."""
    src = Path(caminho)
    if not src.is_file():
        return {"ok": False, "msg": f"arquivo não encontrado: {src}"}
    ffmpeg = _which(ffmpeg_bin)
    if not ffmpeg:
        return {"ok": False, "msg": _msg_ffmpeg()}
    whisper = _which(whisper_bin)
    if not whisper:
        return {"ok": False, "msg": _MSG_WHISPER}
    work = Path(cfg.data_dir) / "multimodal"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / (src.stem + ".wav")
    # 1) extração de áudio (16 kHz mono — formato que o whisper.cpp espera)
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-i", str(src), "-ac", "1", "-ar",
             "16000", "-vn", str(wav)],
            capture_output=True, text=True, timeout=600)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "msg": f"ffmpeg falhou: {exc}"}
    if r.returncode != 0 or not wav.is_file():
        return {"ok": False,
                "msg": f"ffmpeg não gerou o áudio: {r.stderr[-200:]!r}"}
    # 2) transcrição local (whisper.cpp) — nada sai da máquina
    try:
        w = subprocess.run(
            [whisper, "-m", str(modelo_path(cfg, modelo)),
             "-f", str(wav)],
            capture_output=True, text=True, timeout=1800)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "msg": f"whisper falhou: {exc}"}
    segmentos = [(ini, fim, txt.strip())
                 for ini, fim, txt in _SEG.findall(w.stdout or "")]
    if not segmentos:
        return {"ok": False,
                "msg": ("whisper não retornou segmentos (modelo em "
                        f"{modelo_path(cfg, modelo)}? saída: "
                        f"{(w.stdout or w.stderr or '')[:120]!r})")}
    # 3) transcrição com timestamps → biblioteca RAG (fonte citada)
    linhas = [f"[{ini}] {txt}" for ini, _fim, txt in segmentos]
    texto_plano = " ".join(txt for _i, _f, txt in segmentos)
    try:
        from . import knowledge
        dest = knowledge.biblioteca_dir(cfg) / f"{src.stem}-transcricao.txt"
        dest.write_text(
            f"TRANSCRIÇÃO LOCAL de {src.name} "
            f"(whisper.cpp, {len(segmentos)} segmentos)\n\n"
            + "\n".join(linhas) + "\n", encoding="utf-8")
        rag = knowledge.indexar(cfg)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "msg": f"falha ao indexar no RAG: {exc}"}
    try:
        from . import activity
        activity.log(cfg, "multimodal",
                     f"🎙 transcreveu {src.name} · {len(segmentos)} "
                     f"segmentos · indexado no RAG ({rag.get('blocos')} "
                     f"blocos)")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "msg": "ok", "segmentos": len(segmentos),
            "texto": texto_plano, "linhas": linhas,
            "arquivo": str(dest), "rag": rag}


# ------------------------------------------------------------- CLI
def cmd(args, cfg) -> None:
    """`betterme audio|video transcrever <arquivo>`."""
    arquivo = getattr(args, "arquivo", "")
    r = transcrever(cfg, arquivo,
                    ffmpeg_bin=getattr(args, "ffmpeg", None),
                    whisper_bin=getattr(args, "whisper", None),
                    modelo=getattr(args, "modelo", "") or "")
    if not r.get("ok"):
        print(f"✖ {r['msg']}")
        raise SystemExit(1)
    print(f"🎙 transcrição LOCAL concluída — {r['segmentos']} segmento(s):")
    for lin in r["linhas"][:10]:
        print(f"  {lin}")
    if len(r["linhas"]) > 10:
        print(f"  … e mais {len(r['linhas']) - 10}")
    print(f"📚 indexado no RAG: {r['arquivo']} "
          f"({r['rag'].get('blocos')} blocos na biblioteca)")
