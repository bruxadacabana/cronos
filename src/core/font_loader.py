"""
Cronos - Font Loader
Baixa e registra Special Elite e IM Fell English na primeira execução.
Fontes ficam em src/assets/fonts/ (dentro da pasta do app).
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger("cronos.fonts")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FONTS_DIR = BASE_DIR / "src" / "assets" / "fonts"

FONT_URLS = {
    "SpecialElite-Regular.ttf": (
        "https://fonts.gstatic.com/s/specialelite/v18/XLYgIZbkc46tvqgoxjTotC3SnKmD.ttf"
    ),
    "IMFellEnglish-Regular.ttf": (
        "https://fonts.gstatic.com/s/imfellenglish/v16/"
        "Ktk1ALSLW8zDe0rthJysWrnLsAz3F6mZVY9Y5w.ttf"
    ),
    "IMFellEnglish-Italic.ttf": (
        "https://fonts.gstatic.com/s/imfellenglish/v16/"
        "Ktk3ALSLW8zDe0rthJysWp5OlmgMXw.ttf"
    ),
}



def _is_valid_ttf(path) -> bool:
    """Verifica se o arquivo é um TTF/OTF real (não um HTML de erro)."""
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        return header in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf",
                          b"\x00\x02\x00\x00")
    except Exception:
        return False

def download_fonts() -> bool:
    """Baixa as fontes se ainda não existirem. Retorna True se ok."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in FONT_URLS
               if not (FONTS_DIR / name).exists()
               or not _is_valid_ttf(FONTS_DIR / name)]
    if not missing:
        return True

    try:
        import httpx
        for name in missing:
            url = FONT_URLS[name]
            path = FONTS_DIR / name
            try:
                resp = httpx.get(url, timeout=10, follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    path.write_bytes(resp.content)
                    logger.info(f"Fonte baixada: {name} ({len(resp.content)//1024}KB)")
                else:
                    logger.warning(f"Falha ao baixar {name}: status {resp.status_code}")
            except Exception as e:
                logger.warning(f"Erro ao baixar {name}: {e}")
    except ImportError:
        logger.warning("httpx não disponível para download de fontes")

    # Verifica se pelo menos baixou algo
    ok = any(_is_valid_ttf(FONTS_DIR / n) for n in FONT_URLS)
    return ok


def register_fonts() -> dict:
    """
    Registra todas as fontes TTF disponíveis no QFontDatabase.
    Retorna dict {nome_familia: disponível}.
    """
    try:
        from PyQt6.QtGui import QFontDatabase
    except ImportError:
        return {}

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    registered = {}

    for ttf in FONTS_DIR.glob("*.ttf"):
        if _is_valid_ttf(ttf):
            fid = QFontDatabase.addApplicationFont(str(ttf))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                for fam in families:
                    registered[fam] = True
                    logger.info(f"Fonte registrada: {fam} ({ttf.name})")
            else:
                logger.warning(f"Falha ao registrar: {ttf.name}")

    return registered


def get_ui_font(size=13):
    """Retorna QFont para UI (Special Elite ou fallback serif)."""
    from PyQt6.QtGui import QFont
    for name in ["Special Elite", "Courier New", "Courier", "monospace"]:
        f = QFont(name, size)
        if f.exactMatch() or name in ["Courier New", "monospace"]:
            return f
    return QFont("monospace", size)


def get_body_font(size=15):
    """Retorna QFont para corpo de texto (IM Fell English ou fallback serif)."""
    from PyQt6.QtGui import QFont
    for name in ["IM Fell English", "Georgia", "Times New Roman",
                 "Liberation Serif", "DejaVu Serif", "serif"]:
        f = QFont(name, size)
        if f.exactMatch() or name in ["Georgia", "Liberation Serif",
                                       "DejaVu Serif", "serif"]:
            return f
    return QFont("serif", size)


def apply_paper_texture(app, theme: str):
    """
    Aplica textura de papel ao QSS existente do app.
    theme: 'day' | 'night'
    Usa PNG embutido como base64 para garantir funcionamento no Windows.
    """
    try:
        import sys, os
        # Adicionar src/ ao path se necessário
        src_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from assets.textures import get_texture_path
        tex = get_texture_path(theme).replace("\\", "/")
        # Injeta no QSS atual — sobrescreve só o background do widget raiz
        extra = f"""
QWidget#centralWidget {{
    background-image: url("{tex}");
    background-repeat: repeat;
}}
QWidget#feedContainer, QWidget#readerContainer {{
    background-image: url("{tex}");
    background-repeat: repeat;
}}
"""
        current = app.styleSheet()
        app.setStyleSheet(current + extra)
    except Exception as e:
        pass  # Falha silenciosa — textura é cosmética
