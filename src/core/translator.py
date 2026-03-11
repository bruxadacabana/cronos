"""
Cronos - Módulo de Tradução Rápida (via deep-translator)
"""
import logging
from typing import Optional
from .database import get_translation, save_translation

logger = logging.getLogger("cronos.translator")

LANGUAGES = {
    "pt": "Português", "en": "English", "es": "Español",
    "fr": "Français", "de": "Deutsch", "it": "Italiano",
    "ja": "日本語", "zh": "中文", "ar": "العربية",
    "ru": "Русский", "ko": "한국어", "nl": "Nederlands",
    "pl": "Polski", "tr": "Türkçe", "uk": "Українська",
}

def translate_article(article_id: int, title: str, content: str,
                       summary: str, target_lang: str) -> dict:
    """Traduz usando a API do Google Translate nos bastidores."""
    cached = get_translation(article_id, target_lang)
    if cached:
        return cached

    result = {"article_id": article_id, "target_language": target_lang}

    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=target_lang)

        if title:
            result["title_translated"] = translator.translate(title)
        if summary:
            result["summary_translated"] = translator.translate(summary[:4999])
        if content:
            # Quebra o texto para respeitar o limite de 5000 letras do Google
            chunks = [content[i:i+4900] for i in range(0, len(content), 4900)]
            translated_chunks = [translator.translate(chunk) for chunk in chunks]
            result["content_translated"] = "\n".join(filter(None, translated_chunks))

        save_translation(article_id, target_lang,
                         result.get("title_translated"),
                         result.get("content_translated"),
                         result.get("summary_translated"))
        return result

    except ImportError:
        logger.error("deep-translator não instalado.")
        return result
    except Exception as e:
        logger.error(f"Erro na tradução: {e}")
        return result

def get_supported_languages() -> dict:
    return LANGUAGES