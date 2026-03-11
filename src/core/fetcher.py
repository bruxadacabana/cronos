"""
Cronos - Módulo Fetcher
Busca feeds RSS, parseia artigos e faz scraping de conteúdo limpo.
"""

import feedparser
import httpx
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from typing import Optional

try:
    from readability import Document
    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False

from .database import get_sources, save_articles, get_connection, get_setting

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"
LOG_DIR = BASE_DIR / "data" / "logs"

LOG_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "cronos.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("cronos.fetcher")

# Novo Cabeçalho simulando um navegador real (Disfarce contra bloqueios)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1"
}

TIMEOUT = 15


def chunk_article_text(text: str, chunk_size: int = 20000) -> list[str]:
    """
    Fatia textos gigantes em pedaços menores para a IA não se perder no contexto.
    Tenta cortar em quebras de linha duplas (parágrafos) para não cortar frases no meio.
    """
    if not text:
        return []
    
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = ""
    
    for p in paragraphs:
        if len(current_chunk) + len(p) < chunk_size:
            current_chunk += p + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = p + "\n\n"
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks


def _parse_date(entry) -> Optional[str]:
    """Tenta extrair data de publicação do entry RSS."""
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None) or entry.get(field)
        if val:
            try:
                if hasattr(entry, f"{field}_parsed") and getattr(entry, f"{field}_parsed"):
                    t = getattr(entry, f"{field}_parsed")
                    dt = datetime(*t[:6], tzinfo=timezone.utc)
                    return dt.isoformat()
                dt = parsedate_to_datetime(val)
                return dt.isoformat()
            except Exception:
                pass
    return datetime.utcnow().isoformat()


def _extract_thumbnail(entry) -> Optional[str]:
    """Tenta extrair URL de imagem do entry RSS."""
    # media:thumbnail
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    # enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("href") or enc.get("url")
    # media:content
    if hasattr(entry, "media_content") and entry.media_content:
        for m in entry.media_content:
            if "image" in m.get("type", ""):
                return m.get("url")
    return None


def _clean_html(html: str) -> str:
    """Remove tags HTML de forma simples."""
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def fetch_source(source: dict) -> list:
    """
    Busca e parseia um feed RSS de uma fonte.
    Retorna lista de artigos prontos para salvar.
    """
    url = source["url"]
    source_id = source["id"]
    articles = []

    try:
        logger.info(f"Fetching: {source['name']} ({url})")
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)

        if feed.bozo and not feed.entries:
            logger.warning(f"Feed bozo error for {source['name']}: {feed.bozo_exception}")
            return []

        for entry in feed.entries[:50]:  # máximo 50 por fetch
            link = entry.get("link") or entry.get("id")
            if not link:
                continue

            title = _clean_html(entry.get("title", "")).strip()
            if not title:
                continue

            summary = ""
            if hasattr(entry, "summary"):
                summary = _clean_html(entry.summary)[:1000]
            elif hasattr(entry, "description"):
                summary = _clean_html(entry.description)[:1000]

            articles.append({
                "source_id": source_id,
                "title": title,
                "url": link,
                "summary": summary,
                "author": entry.get("author", ""),
                "published_at": _parse_date(entry),
                "language": source.get("language", "pt"),
                "category": source.get("category", "geral"),
                "thumbnail_url": _extract_thumbnail(entry),
            })

        # Atualiza last_fetched
        conn = get_connection()
        conn.execute(
            "UPDATE sources SET last_fetched=?, fetch_errors=0 WHERE id=?",
            (datetime.utcnow().isoformat(), source_id)
        )
        conn.commit()
        conn.close()

        logger.info(f"Fetched {len(articles)} articles from {source['name']}")

    except httpx.TimeoutException:
        logger.error(f"Timeout fetching {source['name']}")
        _increment_error(source_id)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code} for {source['name']}")
        _increment_error(source_id)
    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")
        _increment_error(source_id)

    return articles


def _increment_error(source_id: int):
    conn = get_connection()
    conn.execute("UPDATE sources SET fetch_errors=fetch_errors+1 WHERE id=?", (source_id,))
    conn.commit()
    conn.close()


def fetch_all_sources(progress_callback=None) -> int:
    """Busca todas as fontes ativas. Retorna total de artigos novos."""
    sources = get_sources(active_only=True)
    total = 0

    for i, source in enumerate(sources):
        articles = fetch_source(source)
        if articles:
            save_articles(articles)
            total += len(articles)
        if progress_callback:
            progress_callback(i + 1, len(sources), source["name"])

    logger.info(f"Fetch completo: {total} artigos novos")
    return total


def fetch_article_content(url: str) -> tuple[str, str]:
    """
    Busca conteúdo completo de um artigo via scraping.
    Retorna (html_limpo, texto_puro).
    Usa readability se disponível.
    """
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()

        if HAS_READABILITY:
            doc = Document(resp.text)
            html_clean = doc.summary()
            text_clean = _clean_html(html_clean)
            return html_clean, text_clean
        else:
            # Fallback básico: remove scripts, styles
            html = resp.text
            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
            text = _clean_html(html)
            return html, text

    except Exception as e:
        logger.error(f"Error fetching content from {url}: {e}")
        return "", ""


def add_custom_source(name: str, url: str, category="geral") -> dict:
    """
    Adiciona uma fonte personalizada (RSS ou URL de página).
    Valida se é um feed RSS válido.
    """
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)

        if feed.entries:
            # É um RSS válido
            lang = "pt"
            if feed.feed.get("language"):
                lang = feed.feed.language[:2].lower()

            from .database import add_source
            source_id = add_source(name, url, category, lang)
            return {"success": True, "id": source_id, "entries": len(feed.entries)}
        else:
            return {"success": False, "error": "URL não parece ser um feed RSS válido ou está vazio"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def cache_thumbnail(url: str) -> Optional[str]:
    """Baixa e cacheia thumbnail de uma notícia. Retorna caminho local."""
    if not url:
        return None
    try:
        # Gera nome único baseado na URL
        name = hashlib.md5(url.encode()).hexdigest() + ".jpg"
        path = CACHE_DIR / "thumbnails" / name
        path.parent.mkdir(exist_ok=True)

        if path.exists():
            return str(path)

        resp = httpx.get(url, timeout=10, follow_redirects=True)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            path.write_bytes(resp.content)
            return str(path)
    except Exception:
        pass
    return None