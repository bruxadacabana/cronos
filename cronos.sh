#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# Cria venv
if [ ! -f "$PYTHON" ]; then
    echo "╔══════════════════════════════════════╗"
    echo "║  Cronos — Primeira execução          ║"
    echo "║  Criando ambiente virtual...         ║"
    echo "╚══════════════════════════════════════╝"
    python3 -m venv "$VENV"
    if [ $? -ne 0 ]; then
        echo "❌ Erro: python3 -m venv falhou."
        echo "   Arch/CachyOS: sudo pacman -S python"
        exit 1
    fi
fi

# Instala dependências
if ! "$PYTHON" -c "import PyQt6" 2>/dev/null; then
    echo "📦 Instalando dependências..."
    "$PIP" install --quiet --upgrade pip
    "$PIP" install --quiet -r "$SCRIPT_DIR/requirements.txt"
fi

# Baixa fontes se necessário
if [ ! -f "$SCRIPT_DIR/src/assets/fonts/SpecialElite-Regular.ttf" ]; then
    bash "$SCRIPT_DIR/install_fonts.sh"
fi

exec "$PYTHON" "$SCRIPT_DIR/cronos.py"
