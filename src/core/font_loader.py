"""
Cronos - Font Loader
Baixa e registra Special Elite e IM Fell English na primeira execucao.
Fontes ficam em src/assets/fonts/ (dentro da pasta do app).
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger("cronos.fonts")

BASE_DIR  = Path(__file__).resolve().parent.parent.parent
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

# Headers TTF/OTF validos
_TTF_MAGIC = [
    b"\x00\x01\x00\x00",  # TrueType
    b"OTTO",               # OpenType CFF
    b"true",               # Apple TrueType
    b"ttcf",               # TrueType Collection
]


def _is_valid_ttf(path: Path) -> bool:
    """Verifica se o arquivo e realmente uma fonte TTF/OTF pelo header binario."""
    try:
        header = path.read_bytes()[:4]
        return any(header == magic for magic in _TTF_MAGIC)
    except Exception:
        return False


def download_fonts() -> bool:
    """Baixa as fontes ausentes ou invalidas. Retorna True se todas ok."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    missing = [
        name for name in FONT_URLS
        if not (FONTS_DIR / name).exists() or not _is_valid_ttf(FONTS_DIR / name)
    ]

    if not missing:
        return True

    try:
        import httpx
        for name in missing:
            url  = FONT_URLS[name]
            path = FONTS_DIR / name
            try:
                resp = httpx.get(url, timeout=15, follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 4000:
                    path.write_bytes(resp.content)
                    if _is_valid_ttf(path):
                        logger.info(f"Fonte baixada: {name} ({len(resp.content)//1024}KB)")
                    else:
                        path.unlink(missing_ok=True)
                        logger.warning(f"Arquivo invalido apos download: {name}")
                else:
                    logger.warning(f"Falha ao baixar {name}: status {resp.status_code}")
            except Exception as e:
                logger.warning(f"Erro ao baixar {name}: {e}")
    except ImportError:
        logger.warning("httpx nao disponivel para download de fontes")

    return any(
        (FONTS_DIR / n).exists() and _is_valid_ttf(FONTS_DIR / n)
        for n in FONT_URLS
    )


def register_fonts() -> dict:
    """
    Registra todas as fontes TTF validas no QFontDatabase.
    Retorna dict {nome_familia: True}.
    """
    try:
        from PyQt6.QtGui import QFontDatabase
    except ImportError:
        return {}

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    registered = {}

    for ttf in FONTS_DIR.glob("*.ttf"):
        if not _is_valid_ttf(ttf):
            logger.warning(f"Ignorando fonte invalida: {ttf.name}")
            continue
        fid = QFontDatabase.addApplicationFont(str(ttf))
        if fid >= 0:
            for fam in QFontDatabase.applicationFontFamilies(fid):
                registered[fam] = True
                logger.info(f"Fonte registrada: {fam} ({ttf.name})")
        else:
            logger.warning(f"Falha ao registrar: {ttf.name}")

    return registered


def get_ui_font(size=13):
    """Retorna QFont para UI (Special Elite ou fallback)."""
    from PyQt6.QtGui import QFont
    for name in ["Special Elite", "Courier New", "Courier", "monospace"]:
        f = QFont(name, size)
        if f.exactMatch() or name in ["Courier New", "monospace"]:
            return f
    return QFont("monospace", size)


def get_body_font(size=15):
    """Retorna QFont para corpo de texto (IM Fell English ou fallback)."""
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
    """
    try:
        import sys
        src_dir = str(Path(__file__).resolve().parent.parent.parent)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from assets.textures import get_texture_path
        tex   = get_texture_path(theme).replace("\\", "/")
        extra = f"""
QWidget#centralWidget {{
    background-image: url("{tex}");
    background-repeat: repeat;
}}
"""
        app.setStyleSheet(app.styleSheet() + extra)
    except Exception:
        pass
