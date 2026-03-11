#!/bin/bash
# Cronos - Instalador de Fontes
FONTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/src/assets/fonts"
mkdir -p "$FONTS_DIR"

echo "📦 Baixando fontes Special Elite e IM Fell English..."

# Special Elite
if [ ! -f "$FONTS_DIR/SpecialElite-Regular.ttf" ]; then
    curl -sL "https://fonts.gstatic.com/s/specialelite/v18/XLYgIZbkc46tvqgoxjTotC3vqfKD.ttf" \
         -o "$FONTS_DIR/SpecialElite-Regular.ttf" && echo "  ✓ Special Elite" || echo "  ✗ Falha Special Elite"
fi

# IM Fell English Regular
if [ ! -f "$FONTS_DIR/IMFellEnglish-Regular.ttf" ]; then
    curl -sL "https://fonts.gstatic.com/s/imfellenglish/v16/Ktk1ALQR71mqNQD8YAlNH01bEOXTbQ.ttf" \
         -o "$FONTS_DIR/IMFellEnglish-Regular.ttf" && echo "  ✓ IM Fell English Regular" || echo "  ✗ Falha IM Fell English"
fi

# IM Fell English Italic
if [ ! -f "$FONTS_DIR/IMFellEnglish-Italic.ttf" ]; then
    curl -sL "https://fonts.gstatic.com/s/imfellenglish/v16/Ktk3ALQR71mqNQD8YAlNH01bEOXTvv2EDw.ttf" \
         -o "$FONTS_DIR/IMFellEnglish-Italic.ttf" && echo "  ✓ IM Fell English Italic" || echo "  ✗ Falha IM Fell English Italic"
fi

echo "✓ Fontes instaladas em $FONTS_DIR"
