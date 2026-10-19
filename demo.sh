#!/usr/bin/env bash
# ============================================================
#  demo.sh — sobe a GUI do Hermes Agent para demonstração
#
#  Este script é auto-suficiente: cria o ambiente Python se
#  necessário, instala as dependências e sobe o servidor.
#
#  Uso:  ./demo.sh            (porta 8080, modo demonstração)
#        PORT=9000 ./demo.sh
#        HERMES_MOCK=0 ./demo.sh   (Ollama real, se instalado)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

export HERMES_DATA_DIR="${HERMES_DATA_DIR:-$PWD/data}"
export HERMES_MOCK="${HERMES_MOCK:-1}"
PORT="${PORT:-8080}"

if [ ! -x .venv/bin/python ]; then
  echo "[demo] criando ambiente Python…"
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q flask requests pyyaml rich
  echo "[demo] dependências instaladas"
fi

echo "[demo] subindo a GUI em 0.0.0.0:$PORT (dados: $HERMES_DATA_DIR)"
exec ./.venv/bin/python -m hermes server --host 0.0.0.0 --port "$PORT"
