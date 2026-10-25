#!/usr/bin/env bash
# ============================================================================
#  Betterme Agent — instalador (Debian/Ubuntu/Fedora/Arch e derivados)
#
#  O que faz:
#    1. Instala dependências do sistema (python3, pip, venv, curl)
#    2. Instala o Ollama (se não houver)
#    3. Baixa o modelo Betterme (hermes3:8b por padrão)
#    4. Cria o ambiente Python do Betterme e instala a CLI `betterme`
#    5. (opcional) Instala serviços systemd para GUI + agente
#
#  Uso:
#    ./install.sh [--model hermes3:8b] [--with-systemd] [--skip-model]
#
set -euo pipefail

MODEL="hermes3:8b"
WITH_SYSTEMD="no"
SKIP_MODEL="no"
PORT="8080"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)        MODEL="${2:?}"; shift 2 ;;
    --with-systemd) WITH_SYSTEMD="yes"; shift ;;
    --skip-model)   SKIP_MODEL="yes"; shift ;;
    --port)         PORT="${2:?}"; shift 2 ;;
    -h|--help)      grep '^#' "$0" | sed 's/^# \{0,2\}//'; exit 0 ;;
    *) echo "opção desconhecida: $1 (use --help)"; exit 1 ;;
  esac
done

say()  { printf '\033[96m◈ %s\033[0m\n' "$*"; }
ok()   { printf '\033[92m✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[93m⚠ %s\033[0m\n' "$*"; }

cd "$(dirname "$0")"
HERMES_DIR="$(pwd)"
say "Betterme Agent — instalação em $HERMES_DIR"

# ---------------------------------------------------------------- 1. básico
say "[1/5] dependências do sistema…"
if command -v apt-get >/dev/null; then
  sudo apt-get update -y && sudo apt-get install -y python3 python3-pip python3-venv curl
elif command -v dnf >/dev/null; then
  sudo dnf install -y python3 python3-pip curl
elif command -v pacman >/dev/null; then
  sudo pacman -Sy --noconfirm python python-pip curl
else
  warn "gerenciador de pacotes desconhecido — assumindo python3/pip/curl já presentes"
fi

# ---------------------------------------------------------------- 2. ollama
say "[2/5] servidor Ollama…"
if command -v ollama >/dev/null; then
  ok "Ollama já instalado ($(ollama --version 2>/dev/null | head -1 || echo ok))"
else
  curl -fsSL https://ollama.com/install.sh | sh
  ok "Ollama instalado"
fi

# sobe o serviço (systemd quando existir; senão fica por conta do usuário)
if command -v systemctl >/dev/null && systemctl cat ollama >/dev/null 2>&1; then
  sudo systemctl enable --now ollama 2>/dev/null || true
  ok "serviço systemd 'ollama' ativado"
fi
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:11434/api/version >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf http://127.0.0.1:11434/api/version >/dev/null 2>&1 \
  && ok "Ollama respondendo em http://127.0.0.1:11434" \
  || warn "Ollama ainda não responde — inicie com: ollama serve (ou systemctl start ollama)"

# ---------------------------------------------------------------- 3. modelo
if [[ "$SKIP_MODEL" == "no" ]]; then
  say "[3/5] baixando modelo $MODEL (isso pode demorar)…"
  ollama pull "$MODEL"
  ok "modelo $MODEL disponível"
else
  say "[3/5] download de modelo pulado (--skip-model)"
fi

# --------------------------------------------------------------- 4. python
say "[4/5] ambiente Python do Betterme…"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -e .
ok "CLI instalada: $HERMES_DIR/.venv/bin/betterme"

# link global prático
if [[ -w /usr/local/bin ]]; then
  ln -sf "$HERMES_DIR/.venv/bin/betterme" /usr/local/bin/betterme && ok "atalho global: betterme"
else
  sudo ln -sf "$HERMES_DIR/.venv/bin/betterme" /usr/local/bin/betterme && ok "atalho global: betterme"
fi

# ------------------------------------------------------------ 5. systemd
if [[ "$WITH_SYSTEMD" == "yes" ]]; then
  say "[5/5] serviços systemd…"
  if command -v systemctl >/dev/null; then
    sudo tee /etc/systemd/system/betterme-server.service >/dev/null <<EOF
[Unit]
Description=Betterme Agent — GUI web de controle
After=network.target ollama.service

[Service]
Type=simple
WorkingDirectory=$HERMES_DIR
ExecStart=$HERMES_DIR/.venv/bin/betterme server --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    sudo tee /etc/systemd/system/betterme-agent.service >/dev/null <<EOF
[Unit]
Description=Betterme Agent — daemon do agente (fila de tarefas)
After=network.target ollama.service betterme-server.service

[Service]
Type=simple
WorkingDirectory=$HERMES_DIR
ExecStart=$HERMES_DIR/.venv/bin/betterme daemon
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now betterme-server betterme-agent
    ok "serviços betterme-server e betterme-agent ativos (inicializam junto do sistema)"
  else
    warn "systemd não disponível — rode manualmente: betterme server"
  fi
else
  say "[5/5] systemd pulado (use --with-systemd para instalar como serviço)"
fi

echo
ok "════ INSTALAÇÃO CONCLUÍDA ════"
cat <<EOF

  Próximos passos:

    betterme status              # conferir agente + Ollama
    betterme chat                # conversar no terminal
    betterme server --host 0.0.0.0 --port $PORT --token SUA-SENHA
                              # GUI web de controle (ligar/desligar)

  Dica: em máquina com pouca RAM (≤ 8 GB) prefira o modelo leve:
    ollama pull hermes3:3b && betterme config set model hermes3:3b

EOF
