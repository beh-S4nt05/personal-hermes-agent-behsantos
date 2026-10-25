"""Contratos do Betterme — vocabulário canônico do app (fonte única).

Princípios aplicados (v6.4.0):
- Single Source of Truth: cada valor compartilhado entre módulos vive
  AQUI; módulos importam — nada de string mágica repetida.
- Postel's Law (robustez): conservador no que EMITE (sempre o valor
  canônico), tolerante no que ACEITA (acentos/caixa normalizados).
- Formatos PERSISTIDOS são congelados: chaves de config.yaml, fatos de
  memória, tarefas agendadas, auditoria e rascunhos NÃO mudam —
  mudá-los quebraria dados existentes do operador.
- Chaves de veredito/JSON seguem SEM ACENTO de propósito (convenção de
  API: ASCII estável para parsing, regex e teclado de qualquer idioma).
"""
from __future__ import annotations

import unicodedata

__all__ = [
    "NIVEIS_AUTONOMIA", "NIVEL_CAUTELOSO", "NIVEL_PADRAO", "NIVEL_AUTONOMO",
    "TIPOS_TASK", "TIPO_LEITURA", "TIPO_CRIACAO",
    "NOMES_ESPECIALISTAS", "CHECKS_DOCTOR",
    "MARCA_CODIGO_BLOCO", "MARCA_CODIGO_LINHA",
    "sem_acento", "nivel_valido", "especialista_de", "acao_de",
]

# ── autonomia (decisão D3): os 3 níveis canônicos
NIVEL_CAUTELOSO = "cauteloso"
NIVEL_PADRAO = "padrao"
NIVEL_AUTONOMO = "autonomo"
NIVEIS_AUTONOMIA = (NIVEL_CAUTELOSO, NIVEL_PADRAO, NIVEL_AUTONOMO)

# ── classificação de task (pipeline 🎯): leitura × criação
TIPO_LEITURA = "leitura"
TIPO_CRIACAO = "criacao"
TIPOS_TASK = (TIPO_LEITURA, TIPO_CRIACAO)

# ── especialistas (ADR-001): nomes canônicos (sem acento por contrato)
NOMES_ESPECIALISTAS = ("revisor", "debugger", "pesquisador", "seguranca")

# ── doctor: ids dos checks, na ordem canônica da GUI/CLI
CHECK_DISPOSITIVO = "dispositivo"
CHECK_CEREBRO = "cerebro"
CHECK_OLLAMA = "ollama"
CHECK_MODEL = "model"
CHECK_STT = "stt"
CHECK_CLAUDE = "claude"
CHECK_FLUXOS = "fluxos"
CHECK_SECURITY = "security"
CHECKS_DOCTOR = (CHECK_DISPOSITIVO, CHECK_CEREBRO, CHECK_OLLAMA, CHECK_MODEL,
                 CHECK_STT, CHECK_CLAUDE, CHECK_FLUXOS, CHECK_SECURITY)

# ── DLP (varredura): marcas que substituem código no pool externo (D2)
MARCA_CODIGO_BLOCO = "[CÓDIGO LOCAL — não é enviado]"
MARCA_CODIGO_LINHA = "[CÓDIGO LOCAL]"


# ═══════════════════════ normalizadores (Postel's Law) ═══════════════════════
def sem_acento(txt: str) -> str:
    """minúsculas sem acentos ('Autônomo' → 'autonomo')."""
    norm = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    return "".join(c for c in norm if not unicodedata.combining(c))


def nivel_valido(txt: str) -> str | None:
    """Nível canônico de autonomia — aceita 'Autônomo', 'PADRÃO'…
    None se não for um nível válido."""
    v = sem_acento(txt)
    return v if v in NIVEIS_AUTONOMIA else None


def especialista_de(txt: str) -> str | None:
    """Nome canônico de especialista — aceita 'Segurança', 'REVISOR'…
    None se não existir."""
    v = sem_acento(txt)
    return v if v in NOMES_ESPECIALISTAS else None


def acao_de(args, padrao: str = "status") -> str:
    """Ação de um subcomando CLI: leitura tolerante e uniforme
    (falta o atributo ou vazio → padrão; sempre strip+lower)."""
    return str(getattr(args, "acao", None) or padrao).strip().lower()
