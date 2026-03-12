"""
Cronos - Módulo Fetcher v2.0
Busca feeds RSS, parseia artigos e faz scraping de conteúdo limpo.

Scraper hierárquico (melhor -> fallback):
  1. trafilatura  -- extrator de conteúdo editorial, o mais preciso
  2. readability  -- extrator DOM clássico
  3. BeautifulSoup -- remove boilerplate manualmente
  4. regex puro   -- último recurso

Similaridade para POV:
  - 60% cosine TF-IDF nos textos
  - 40% Jaccard sobre keywords IA (quando disponíveis)
"""

import feedparser
import httpx
import hashlib
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from typing import Optional

# Extratores opcionais -- usa o melhor disponível
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

try:
    from readability import Document as ReadabilityDocument
    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .database import (get_sources, save_articles, get_connection,
                        get_setting, get_source_date_limit)

BASE_DIR  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"
LOG_DIR   = BASE_DIR / "data" / "logs"

LOG_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "cronos.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("cronos.fetcher")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}

TIMEOUT = 20

# Limiar de chars para considerar conteúdo completo
PARTIAL_THRESHOLD = 600


# ============================================================
# Utilitários gerais
# ============================================================

def chunk_article_text(text: str, chunk_size: int = 20000) -> list:
    """Fatia textos longos em pedaços respeitando parágrafos."""
    if not text:
        return []
    chunks, current = [], ""
    for p in text.split("\n\n"):
        if len(current) + len(p) < chunk_size:
            current += p + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            current = p + "\n\n"
    if current:
        chunks.append(current.strip())
    return chunks


def _parse_date(entry) -> Optional[str]:
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None) or entry.get(field)
        if val:
            try:
                parsed = getattr(entry, f"{field}_parsed", None)
                if parsed:
                    return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
                return parsedate_to_datetime(val).isoformat()
            except Exception:
                pass
    return datetime.utcnow().isoformat()


def _extract_thumbnail(entry) -> Optional[str]:
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("href") or enc.get("url")
    if hasattr(entry, "media_content") and entry.media_content:
        for m in entry.media_content:
            if "image" in m.get("type", ""):
                return m.get("url")
    return None


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_meaningful(text: str) -> bool:
    """
    Verifica se o texto contém conteúdo editorial real.
    Critérios: comprimento mínimo E densidade alfanumérica razoável
    (evita aceitar HTML cheio de tags como 'conteúdo').
    """
    if not text or len(text) < PARTIAL_THRESHOLD:
        return False
    alnum = sum(1 for c in text if c.isalnum())
    return alnum / len(text) > 0.38


# ============================================================
# Scraper hierárquico
# ============================================================

def _scrape_trafilatura(raw_html: str, url: str) -> str:
    if not HAS_TRAFILATURA:
        return ""
    try:
        result = trafilatura.extract(
            raw_html, url=url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,
        )
        return result or ""
    except Exception as e:
        logger.debug(f"trafilatura erro: {e}")
        return ""


def _scrape_readability(raw_html: str) -> str:
    if not HAS_READABILITY:
        return ""
    try:
        doc = ReadabilityDocument(raw_html)
        return _clean_html(doc.summary())
    except Exception as e:
        logger.debug(f"readability erro: {e}")
        return ""


def _scrape_bs4(raw_html: str) -> str:
    if not HAS_BS4:
        return ""
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "form", "noscript", "iframe"]):
            tag.decompose()
        paragraphs = []
        for p in soup.find_all(["p", "article", "section"]):
            text = p.get_text(" ", strip=True)
            if len(text) > 60:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)
    except Exception as e:
        logger.debug(f"bs4 erro: {e}")
        return ""


def _scrape_regex(raw_html: str) -> str:
    raw = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.DOTALL)
    raw = re.sub(r"<style[^>]*>.*?</style>",   "", raw,      flags=re.DOTALL)
    return _clean_html(raw)


def fetch_article_content(url: str) -> tuple:
    """
    Busca conteúdo completo via scraping hierárquico.
    Retorna (html_para_exibição, texto_puro).
    """
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT,
                         follow_redirects=True)
        resp.raise_for_status()
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        raw_html  = resp.content.decode(encoding, errors="replace")

        # 1. trafilatura
        text = _scrape_trafilatura(raw_html, url)
        if _is_meaningful(text):
            logger.debug(f"trafilatura OK [{len(text)}c] {url}")
            html = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", " ") + "</p>"
            return html, text

        # 2. readability
        text = _scrape_readability(raw_html)
        if _is_meaningful(text):
            logger.debug(f"readability OK [{len(text)}c] {url}")
            return f"<p>{text}</p>", text

        # 3. bs4
        text = _scrape_bs4(raw_html)
        if _is_meaningful(text):
            logger.debug(f"bs4 OK [{len(text)}c] {url}")
            return f"<p>{text}</p>", text

        # 4. regex fallback
        text = _scrape_regex(raw_html)
        logger.debug(f"regex fallback [{len(text)}c] {url}")
        return f"<p>{text}</p>", text

    except httpx.TimeoutException:
        logger.warning(f"Timeout scraping {url}")
        return "", ""
    except Exception as e:
        logger.error(f"Erro scraping {url}: {e}")
        return "", ""


# ============================================================
# Fetch RSS
# ============================================================

def fetch_source(source: dict,
                 date_from: Optional[datetime] = None,
                 date_to:   Optional[datetime] = None) -> list:
    """
    Busca feed RSS e, quando o texto do feed for curto,
    tenta scraping completo do artigo.
    content_partial é determinado pelo conteúdo REAL obtido.
    """
    url       = source["url"]
    source_id = source["id"]
    articles  = []

    cutoff = get_source_date_limit(source_id) if (date_from is None and date_to is None) else date_from

    try:
        logger.info(f"Fetching RSS: {source['name']} ({url})")
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        if feed.bozo and not feed.entries:
            logger.warning(f"Feed bozo: {source['name']}")
            return []

        for entry in feed.entries[:50]:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue

            title = _clean_html(entry.get("title", "")).strip()
            if not title:
                continue

            # Texto do feed (geralmente truncado)
            feed_text = ""
            if hasattr(entry, "content") and entry.content:
                feed_text = _clean_html(entry.content[0].get("value", ""))
            if not feed_text:
                feed_text = _clean_html(getattr(entry, "summary", "")
                                         or getattr(entry, "description", ""))
            feed_text = feed_text[:2000]

            pub_iso = _parse_date(entry)

            # Filtro de data mínima
            if cutoff is not None and pub_iso:
                try:
                    pub_dt   = datetime.fromisoformat(pub_iso.replace("Z", "+00:00"))
                    pub_dt   = pub_dt if pub_dt.tzinfo else pub_dt.replace(tzinfo=timezone.utc)
                    cut_aw   = cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=timezone.utc)
                    if pub_dt < cut_aw:
                        continue
                except Exception:
                    pass

            # Filtro de data máxima
            if date_to is not None and pub_iso:
                try:
                    pub_dt  = datetime.fromisoformat(pub_iso.replace("Z", "+00:00"))
                    pub_dt  = pub_dt if pub_dt.tzinfo else pub_dt.replace(tzinfo=timezone.utc)
                    dto_aw  = date_to if date_to.tzinfo else date_to.replace(tzinfo=timezone.utc)
                    if pub_dt > dto_aw:
                        continue
                except Exception:
                    pass

            # Tenta scraping quando o feed não entrega conteúdo completo
            content_clean = ""
            if not _is_meaningful(feed_text):
                try:
                    _, scraped = fetch_article_content(link)
                    if _is_meaningful(scraped):
                        content_clean = scraped
                except Exception:
                    pass

            best   = content_clean or feed_text
            is_partial = not _is_meaningful(best)

            articles.append({
                "source_id":       source_id,
                "title":           title,
                "url":             link,
                "summary":         feed_text,
                "content_clean":   content_clean,
                "author":          entry.get("author", ""),
                "published_at":    pub_iso,
                "language":        source.get("language", "pt"),
                "category":        source.get("category", "geral"),
                "thumbnail_url":   _extract_thumbnail(entry),
                "content_partial": 1 if is_partial else 0,
            })

        conn = get_connection()
        conn.execute(
            "UPDATE sources SET last_fetched=?, fetch_errors=0 WHERE id=?",
            (datetime.utcnow().isoformat(), source_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"Fetched {len(articles)} artigos de {source['name']}")

    except httpx.TimeoutException:
        logger.error(f"Timeout: {source['name']}")
        _increment_error(source_id)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP {e.response.status_code}: {source['name']}")
        _increment_error(source_id)
    except Exception as e:
        logger.error(f"Erro: {source['name']}: {e}")
        _increment_error(source_id)

    return articles


def _increment_error(source_id: int):
    conn = get_connection()
    conn.execute("UPDATE sources SET fetch_errors=fetch_errors+1 WHERE id=?", (source_id,))
    conn.commit()
    conn.close()


def fetch_all_sources(progress_callback=None) -> int:
    sources = get_sources(active_only=True)
    total   = 0
    for i, source in enumerate(sources):
        arts = fetch_source(source)
        if arts:
            save_articles(arts)
            total += len(arts)
        if progress_callback:
            progress_callback(i + 1, len(sources), source["name"])
    logger.info(f"Fetch completo: {total} artigos novos")
    return total


def add_custom_source(name: str, url: str, category="geral") -> dict:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.entries:
            lang = "pt"
            if feed.feed.get("language"):
                lang = feed.feed.language[:2].lower()
            from .database import add_source
            sid = add_source(name, url, category, lang)
            return {"success": True, "id": sid, "entries": len(feed.entries)}
        return {"success": False, "error": "URL não parece ser um feed RSS válido"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def cache_thumbnail(url: str) -> Optional[str]:
    if not url:
        return None
    try:
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


# ============================================================
# Similaridade TF-IDF ponderada (para Pontos de Vista)
# ============================================================

_STOPWORDS = {
    "de","do","da","dos","das","em","no","na","nos","nas","para","por",
    "com","que","um","uma","uns","umas","o","a","os","as","e","é","se",
    "ao","à","pelo","pela","pelos","pelas","como","mais","mas","ou","seu",
    "sua","seus","suas","este","esta","isso","isto","ele","ela","eles","elas",
    "foi","são","ser","ter","tem","teve","será","está","estar","entre","sobre",
    "after","and","are","as","at","be","been","but","by","for","from",
    "had","has","have","he","her","him","his","how","in","is","it","its",
    "not","of","on","or","our","out","so","than","that","the","their",
    "them","they","this","to","was","we","were","what","when","which",
    "who","will","with","you",
}


def _tokenize(text: str) -> list:
    tokens = re.findall(r"\b[a-záàâãéêíóôõúüçñ\w]{3,}\b", text.lower(), re.UNICODE)
    return [t for t in tokens if t not in _STOPWORDS]


def _tf(tokens: list) -> dict:
    if not tokens:
        return {}
    counts: dict = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {t: c / total for t, c in counts.items()}


def _cosine(tf_a: dict, tf_b: dict) -> float:
    vocab  = set(tf_a) | set(tf_b)
    dot    = sum(tf_a.get(t, 0.0) * tf_b.get(t, 0.0) for t in vocab)
    norm_a = math.sqrt(sum(v * v for v in tf_a.values())) or 1e-9
    norm_b = math.sqrt(sum(v * v for v in tf_b.values())) or 1e-9
    return dot / (norm_a * norm_b)


def compute_similarity(text_a: str, text_b: str,
                        kws_a: Optional[list] = None,
                        kws_b: Optional[list] = None) -> float:
    """
    Score de similaridade ponderado 0.0–1.0:
      60% cosine TF sobre título+texto
      40% Jaccard sobre keywords IA (se disponíveis nos dois)
    """
    tf_a    = _tf(_tokenize(text_a))
    tf_b    = _tf(_tokenize(text_b))
    cosine  = _cosine(tf_a, tf_b)

    if kws_a and kws_b:
        set_a    = {k.lower().strip() for k in kws_a if k.strip()}
        set_b    = {k.lower().strip() for k in kws_b if k.strip()}
        union    = len(set_a | set_b) or 1
        jaccard  = len(set_a & set_b) / union
        return 0.60 * cosine + 0.40 * jaccard
    return cosine


def find_similar_articles(target: dict, candidates: list,
                           min_score: float = 0.12,
                           max_results: int = 15) -> list:
    """
    Encontra artigos similares usando score ponderado TF-IDF + keywords.
    Retorna lista de (score, article) ordenada por score decrescente.
    """
    t_text = " ".join(filter(None, [
        target.get("title", ""),
        target.get("content_clean", ""),
        target.get("summary", ""),
    ]))
    t_kws = ([k.strip() for k in target["ai_keywords"].split(",")]
              if target.get("ai_keywords") else None)

    results = []
    for art in candidates:
        if art.get("id") == target.get("id"):
            continue
        if art.get("source_name") == target.get("source_name"):
            continue

        a_text = " ".join(filter(None, [
            art.get("title", ""),
            art.get("content_clean", ""),
            art.get("summary", ""),
        ]))
        a_kws = ([k.strip() for k in art["ai_keywords"].split(",")]
                  if art.get("ai_keywords") else None)

        score = compute_similarity(t_text, a_text, t_kws, a_kws)
        if score >= min_score:
            results.append((score, art))

    results.sort(key=lambda x: -x[0])
    return results[:max_results]
