"""
Cronos - Módulo de Tradução
Cadeia de backends gratuitos sem necessidade de chave de API:

  1. deep-translator (Google Translate scraping) — se instalado
  2. MyMemory API        — gratuito, sem chave, 1000 palavras/dia por IP
  3. Lingva              — instância pública open-source do Google Translate
  4. ArgosTranslate      — 100% offline, sem internet — se instalado

Nenhum Ollama, nenhuma chave paga.
"""
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Optional

from .database import get_translation, save_translation

logger = logging.getLogger("cronos.translator")

LANGUAGES = {
    "pt": "Português", "en": "English", "es": "Español",
    "fr": "Français",  "de": "Deutsch", "it": "Italiano",
    "ja": "日本語",     "zh": "中文",    "ar": "العربية",
    "ru": "Русский",   "ko": "한국어",   "nl": "Nederlands",
    "pl": "Polski",    "tr": "Türkçe",  "uk": "Українська",
}

# Instâncias públicas do Lingva (várias para redundância)
LINGVA_INSTANCES = [
    "https://lingva.ml",
    "https://lingva.thedaviddelta.com",
    "https://translate.projectsegfau.lt",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Cronos/1.0; news reader)",
    "Accept": "application/json",
}


# ── Backend 1: deep-translator (Google Translate) ────────────────────────────

def _via_deep_translator(text: str, target: str) -> Optional[str]:
    from deep_translator import GoogleTranslator
    t = GoogleTranslator(source="auto", target=target)
    # Respeita limite de 5000 chars por chamada
    if len(text) <= 4900:
        return t.translate(text)
    chunks = [text[i:i+4900] for i in range(0, len(text), 4900)]
    parts = [t.translate(c) for c in chunks if c.strip()]
    return "\n".join(filter(None, parts))


# ── Backend 2: MyMemory API ───────────────────────────────────────────────────

def _via_mymemory(text: str, target: str, source: str = "auto") -> Optional[str]:
    """
    MyMemory: gratuito, sem chave, limite ~1000 palavras/dia por IP.
    Docs: https://mymemory.translated.net/doc/spec.php
    """
    # Detecta idioma de origem automático via "autodetect"
    lang_pair = f"autodetect|{target}" if source == "auto" else f"{source}|{target}"

    # Limite de 500 chars por request na versão sem chave
    chunk_size = 480
    parts = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i+chunk_size].strip()
        if not chunk:
            continue
        params = urllib.parse.urlencode({"q": chunk, "langpair": lang_pair})
        url = f"https://api.mymemory.translated.net/get?{params}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated and translated.upper() != "QUERY LENGTH LIMIT EXCEEDED":
                parts.append(translated)
            else:
                return None   # Limite atingido
        except Exception as e:
            logger.debug(f"MyMemory chunk erro: {e}")
            return None
    return "\n".join(parts) if parts else None


# ── Backend 3: Lingva (instâncias públicas) ───────────────────────────────────

def _via_lingva(text: str, target: str, source: str = "auto") -> Optional[str]:
    """
    Lingva Translate: frontend open-source para Google Translate.
    Várias instâncias públicas disponíveis.
    """
    src = source if source != "auto" else "auto"
    # Lingva tem limite de URL — divide em partes de 1000 chars
    chunk_size = 900
    parts = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i+chunk_size].strip()
        if not chunk:
            continue
        encoded = urllib.parse.quote(chunk, safe="")
        for base in LINGVA_INSTANCES:
            url = f"{base}/api/v1/{src}/{target}/{encoded}"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                translated = data.get("translation", "")
                if translated:
                    parts.append(translated)
                    break
            except Exception as e:
                logger.debug(f"Lingva {base} erro: {e}")
                continue
        else:
            return None   # Todas instâncias falharam
    return "\n".join(parts) if parts else None


# ── Backend 4: ArgosTranslate (offline) ──────────────────────────────────────

def _via_argos(text: str, target: str, source: str = "auto") -> Optional[str]:
    """
    ArgosTranslate: tradução 100% offline.
    Requer: pip install argostranslate
    E download do pacote de idioma via argostranslate.package
    """
    import argostranslate.package
    import argostranslate.translate

    src = source if source != "auto" else "en"   # Argos precisa de idioma explícito
    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == src), None)
    to_lang   = next((l for l in installed if l.code == target), None)

    if not from_lang or not to_lang:
        raise RuntimeError(f"Pacote {src}→{target} não instalado no ArgosTranslate")

    translation = from_lang.get_translation(to_lang)
    if not translation:
        raise RuntimeError(f"Tradução {src}→{target} não disponível")

    return translation.translate(text)


# ── Função principal ──────────────────────────────────────────────────────────

def _translate_text(text: str, target: str) -> tuple[str, str]:
    """
    Tenta os backends em ordem. Retorna (texto_traduzido, backend_usado).
    Lança exceção se todos falharem.
    """
    if not text or not text.strip():
        return "", "none"

    # 1. deep-translator (Google Translate)
    try:
        result = _via_deep_translator(text, target)
        if result:
            return result, "Google Translate"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"deep-translator falhou: {e}")

    # 2. MyMemory
    try:
        result = _via_mymemory(text, target)
        if result:
            return result, "MyMemory"
    except Exception as e:
        logger.debug(f"MyMemory falhou: {e}")

    # 3. Lingva
    try:
        result = _via_lingva(text, target)
        if result:
            return result, "Lingva"
    except Exception as e:
        logger.debug(f"Lingva falhou: {e}")

    # 4. ArgosTranslate (offline)
    try:
        result = _via_argos(text, target)
        if result:
            return result, "ArgosTranslate (offline)"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"ArgosTranslate falhou: {e}")

    raise RuntimeError(
        "Nenhum serviço de tradução disponível.\n\n"
        "Opções para ativar a tradução:\n"
        "• Online (recomendado): pip install deep-translator\n"
        "• Offline: pip install argostranslate"
    )


def translate_article(article_id: int, title: str, content: str,
                      summary: str, target_lang: str) -> dict:
    """Traduz um artigo completo, com cache no banco de dados."""
    cached = get_translation(article_id, target_lang)
    if cached:
        return {**cached, "from_cache": True}

    result = {"article_id": article_id, "target_language": target_lang}

    try:
        if title:
            t, backend = _translate_text(title, target_lang)
            result["title_translated"] = t
            result["backend"] = backend

        if content:
            # Limita conteúdo para não exceder limites de rate
            c, _ = _translate_text(content[:8000], target_lang)
            result["content_translated"] = c

        if summary:
            s, _ = _translate_text(summary[:1000], target_lang)
            result["summary_translated"] = s

        logger.info(
            f"Artigo {article_id} traduzido para {target_lang} "
            f"via {result.get('backend','?')}"
        )

        save_translation(
            article_id, target_lang,
            result.get("title_translated"),
            result.get("content_translated"),
            result.get("summary_translated"),
        )

    except RuntimeError as e:
        result["error"] = str(e)
        logger.warning(f"Tradução falhou para artigo {article_id}: {e}")
    except Exception as e:
        result["error"] = f"Erro inesperado: {e}"
        logger.error(f"Tradução erro inesperado artigo {article_id}: {e}")

    return result


def get_supported_languages() -> dict:
    return LANGUAGES
