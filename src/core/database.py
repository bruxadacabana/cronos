"""
Cronos - Módulo de Banco de Dados v1.2
Todos os dados em /data/cronos.db
Configurações isoladas em /data/settings.json
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "cronos.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
SOURCES_PATH  = DATA_DIR / "sources.json"

def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "logs").mkdir(exist_ok=True)
    (DATA_DIR / "cache").mkdir(exist_ok=True)
    (DATA_DIR / "social").mkdir(exist_ok=True)

def get_connection():
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _add_col(c, table, col, definition):
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    except Exception:
        pass

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
        category TEXT DEFAULT 'geral', language TEXT DEFAULT 'pt',
        country TEXT DEFAULT 'BR', active INTEGER DEFAULT 1,
        economic_axis REAL DEFAULT 0.0, authority_axis REAL DEFAULT 0.0,
        political_confirmed INTEGER DEFAULT 0,
        last_fetched TEXT, fetch_errors INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER REFERENCES sources(id),
        title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
        summary TEXT, content TEXT, content_clean TEXT,
        author TEXT, published_at TEXT,
        fetched_at TEXT DEFAULT (datetime('now')),
        language TEXT DEFAULT 'pt', category TEXT DEFAULT 'geral',
        thumbnail_url TEXT, thumbnail_cached TEXT,
        is_read INTEGER DEFAULT 0, is_favorite INTEGER DEFAULT 0,
        economic_axis REAL, authority_axis REAL,
        emotional_tone TEXT, clickbait_score REAL,
        ai_summary TEXT, ai_category TEXT,
        ai_keywords TEXT, ai_implications TEXT, ai_5ws TEXT,
        analysis_done INTEGER DEFAULT 0, analysis_queued INTEGER DEFAULT 0)""")

    c.execute("""CREATE TABLE IF NOT EXISTS translations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER REFERENCES articles(id),
        target_language TEXT NOT NULL,
        title_translated TEXT, content_translated TEXT, summary_translated TEXT,
        translated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(article_id, target_language))""")

    c.execute("""CREATE TABLE IF NOT EXISTS alert_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL, value TEXT NOT NULL, active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER REFERENCES articles(id),
        alert_rule_id INTEGER REFERENCES alert_rules(id),
        is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS trending_clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL, keywords TEXT, article_ids TEXT,
        source_count INTEGER DEFAULT 0,
        detected_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS social_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL, post_id TEXT, author TEXT,
        content TEXT NOT NULL, url TEXT, score INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0, published_at TEXT,
        fetched_at TEXT DEFAULT (datetime('now')),
        category TEXT, emotional_tone TEXT, keywords TEXT,
        analysis_done INTEGER DEFAULT 0,
        UNIQUE(platform, post_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS archive_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        note TEXT DEFAULT '',
        saved_at TEXT DEFAULT (datetime('now')),
        UNIQUE(article_id, tag))""")

    # Migrações seguras
    for col, dfn in [("economic_axis","REAL DEFAULT 0.0"),("authority_axis","REAL DEFAULT 0.0"),("political_confirmed","INTEGER DEFAULT 0")]:
        _add_col(c, "sources", col, dfn)
    for col, dfn in [("economic_axis","REAL"),("authority_axis","REAL"),("ai_keywords","TEXT"),("ai_implications","TEXT"),("ai_5ws","TEXT"),("analysis_queued","INTEGER DEFAULT 0"),("content_partial","INTEGER DEFAULT 0")]:
        _add_col(c, "articles", col, dfn)

    conn.commit()
    conn.close()
    _insert_defaults()

def _load_sources_json() -> list:
    """Carrega fontes do sources.json. Cria arquivo padrão se não existir."""
    if not SOURCES_PATH.exists():
        _create_default_sources_json()
    try:
        with open(SOURCES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _create_default_sources_json():
    """Cria sources.json com fontes padrão."""
    sources = [
        {"name": "G1 / Globo",         "url": "https://g1.globo.com/rss/g1/",                                    "category": "brasil",         "language": "pt", "country": "BR", "economic_axis":  0.2, "authority_axis":  0.1},
        {"name": "Folha de S.Paulo",    "url": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml",          "category": "brasil",         "language": "pt", "country": "BR", "economic_axis":  0.1, "authority_axis": -0.1},
        {"name": "UOL Notícias",        "url": "https://rss.uol.com.br/feed/noticias.xml",                        "category": "brasil",         "language": "pt", "country": "BR", "economic_axis":  0.0, "authority_axis":  0.0},
        {"name": "Agência Brasil",      "url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",   "category": "brasil",         "language": "pt", "country": "BR", "economic_axis": -0.2, "authority_axis":  0.2},
        {"name": "Brasil de Fato",      "url": "https://www.brasildefato.com.br/rss",                             "category": "brasil",         "language": "pt", "country": "BR", "economic_axis": -0.7, "authority_axis": -0.2},
        {"name": "BBC News",            "url": "http://feeds.bbci.co.uk/news/rss.xml",                            "category": "internacional",  "language": "en", "country": "GB", "economic_axis":  0.0, "authority_axis":  0.0},
        {"name": "Reuters",             "url": "https://feeds.reuters.com/reuters/topNews",                        "category": "internacional",  "language": "en", "country": "US", "economic_axis":  0.1, "authority_axis":  0.0},
        {"name": "Associated Press",    "url": "https://rsshub.app/apnews/topics/apf-topnews",                    "category": "internacional",  "language": "en", "country": "US", "economic_axis":  0.0, "authority_axis":  0.0},
        {"name": "Al Jazeera",          "url": "https://www.aljazeera.com/xml/rss/all.xml",                       "category": "internacional",  "language": "en", "country": "QA", "economic_axis": -0.1, "authority_axis":  0.1},
        {"name": "The Guardian",        "url": "https://www.theguardian.com/world/rss",                           "category": "internacional",  "language": "en", "country": "GB", "economic_axis": -0.3, "authority_axis": -0.3},
        {"name": "Fox News",            "url": "https://moxie.foxnews.com/google-publisher/world.xml",            "category": "internacional",  "language": "en", "country": "US", "economic_axis":  0.7, "authority_axis":  0.4},
        {"name": "Hacker News",         "url": "https://hnrss.org/frontpage",                                     "category": "tecnologia",     "language": "en", "country": "US", "economic_axis":  0.2, "authority_axis": -0.4},
        {"name": "Ars Technica",        "url": "https://feeds.arstechnica.com/arstechnica/index",                 "category": "tecnologia",     "language": "en", "country": "US", "economic_axis": -0.1, "authority_axis": -0.2},
        {"name": "The Verge",           "url": "https://www.theverge.com/rss/index.xml",                          "category": "tecnologia",     "language": "en", "country": "US", "economic_axis":  0.0, "authority_axis": -0.1},
        {"name": "TechCrunch",          "url": "https://techcrunch.com/feed/",                                    "category": "tecnologia",     "language": "en", "country": "US", "economic_axis":  0.3, "authority_axis": -0.1},
        {"name": "MIT Tech Review",     "url": "https://www.technologyreview.com/feed/",                          "category": "tecnologia",     "language": "en", "country": "US", "economic_axis":  0.0, "authority_axis": -0.1},
        {"name": "NASA News",           "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",                  "category": "ciencia",        "language": "en", "country": "US", "economic_axis":  0.0, "authority_axis":  0.1},
        {"name": "Scientific American", "url": "http://rss.sciam.com/ScientificAmerican-Global",                  "category": "ciencia",        "language": "en", "country": "US", "economic_axis": -0.1, "authority_axis": -0.1},
        {"name": "Nature",              "url": "https://www.nature.com/nature.rss",                               "category": "ciencia",        "language": "en", "country": "GB", "economic_axis":  0.0, "authority_axis":  0.0},
        {"name": "Infobae",             "url": "https://www.infobae.com/feeds/rss/",                              "category": "america-latina", "language": "es", "country": "AR", "economic_axis":  0.5, "authority_axis":  0.2},
        {"name": "El País",             "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada","category": "america-latina", "language": "es", "country": "ES", "economic_axis": -0.2, "authority_axis": -0.1},
        {"name": "DW Brasil",           "url": "https://rss.dw.com/rdf/rss-br-todas",                            "category": "internacional",  "language": "pt", "country": "DE", "economic_axis":  0.0, "authority_axis":  0.0},
        {"name": "France 24 PT",        "url": "https://www.france24.com/pt/rss",                                 "category": "internacional",  "language": "pt", "country": "FR", "economic_axis": -0.1, "authority_axis":  0.0},
        {"name": "Bloomberg",           "url": "https://feeds.bloomberg.com/markets/news.rss",                    "category": "economia",       "language": "en", "country": "US", "economic_axis":  0.5, "authority_axis":  0.1},
        {"name": "Financial Times",     "url": "https://www.ft.com/rss/home",                                     "category": "economia",       "language": "en", "country": "GB", "economic_axis":  0.3, "authority_axis":  0.0},
    ]
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)

def save_source_to_json(source: dict):
    """Adiciona ou atualiza uma fonte no sources.json."""
    sources = _load_sources_json()
    for i, s in enumerate(sources):
        if s["url"] == source["url"]:
            sources[i] = source
            break
    else:
        sources.append(source)
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)

def remove_source_from_json(url: str):
    """Remove uma fonte do sources.json pelo URL."""
    sources = _load_sources_json()
    sources = [s for s in sources if s["url"] != url]
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)

def update_source_json(url: str, **kwargs):
    """Atualiza campos de uma fonte no sources.json."""
    sources = _load_sources_json()
    for s in sources:
        if s["url"] == url:
            s.update(kwargs)
            break
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)

def _insert_defaults():
    # Carrega ou cria as configurações no JSON
    defaults_settings = {
        "theme":"day","theme_auto":"1","theme_day_start":"07:00","theme_night_start":"19:00",
        "fetch_interval":"30","fetch_on_startup":"1",
        "ollama_url":"http://localhost:11434","ollama_model":"llama3","ollama_enabled":"1",
        "translate_fallback":"1","default_language":"pt","reader_font_size":"16",
        "notifications_enabled":"1","ollama_android_url":"","dashboard_realtime":"1","first_run":"1",
        "reddit_enabled":"1","reddit_client_id":"","reddit_client_secret":"",
        "reddit_subreddits":"worldnews,brasil,technology,science",
        "bluesky_enabled":"1","mastodon_enabled":"1","mastodon_instance":"mastodon.social",
        "youtube_enabled":"0","youtube_api_key":"",
        "twitter_enabled":"0","twitter_username":"","twitter_password":"",
        "auto_analyze":"1","analyze_on_startup":"1",
    }
    
    current_settings = get_all_settings()
    changed = False
    for k, v in defaults_settings.items():
        if k not in current_settings:
            current_settings[k] = v
            changed = True
            
    if changed:
        _save_settings_json(current_settings)

    # Insere fontes do sources.json no banco (primeira execução)
    conn = get_connection()
    c = conn.cursor()
    for s in _load_sources_json():
        c.execute(
            "INSERT OR IGNORE INTO sources (name,url,category,language,country,economic_axis,authority_axis) VALUES (?,?,?,?,?,?,?)",
            (s["name"], s["url"], s.get("category","geral"), s.get("language","pt"),
             s.get("country","??"), s.get("economic_axis",0.0), s.get("authority_axis",0.0))
        )
    conn.commit()
    conn.close()

# ── Gerenciamento do Arquivo JSON de Configurações ──────────────────────────

def _load_settings_json() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_settings_json(data: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_setting(key, default=None):
    data = _load_settings_json()
    return data.get(key, default)

def set_setting(key, value):
    data = _load_settings_json()
    data[key] = str(value)
    _save_settings_json(data)

def get_all_settings():
    return _load_settings_json()

# ── Funções Originais do Banco de Dados (SQLite) ─────────────────────────────

def get_sources(active_only=True):
    conn = get_connection()
    q = "SELECT * FROM sources" + (" WHERE active=1" if active_only else "") + " ORDER BY category,name"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_source(name, url, category="geral", language="pt", country="??"):
    conn = get_connection()
    c = conn.execute("INSERT OR IGNORE INTO sources (name,url,category,language,country) VALUES (?,?,?,?,?)", (name,url,category,language,country))
    conn.commit()
    rid = c.lastrowid
    conn.close()
    return rid

def update_source_political(source_id, economic_axis, authority_axis, confirmed=False):
    conn = get_connection()
    conn.execute("UPDATE sources SET economic_axis=?,authority_axis=?,political_confirmed=? WHERE id=?", (economic_axis,authority_axis,int(confirmed),source_id))
    conn.commit()
    conn.close()

def save_articles(articles):
    conn = get_connection()
    new_ids = []
    for a in articles:
        try:
            c = conn.execute("INSERT OR IGNORE INTO articles (source_id,title,url,summary,author,published_at,language,category,thumbnail_url,content_partial) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (a.get("source_id"),a.get("title"),a.get("url"),a.get("summary"),a.get("author"),a.get("published_at"),a.get("language","pt"),a.get("category","geral"),a.get("thumbnail_url"),a.get("content_partial",0)))
            if c.lastrowid and c.rowcount > 0:
                new_ids.append(c.lastrowid)
        except Exception:
            pass
    conn.commit()
    conn.close()
    return new_ids

def get_articles(limit=100, offset=0, category=None, language=None, is_read=None,
                 is_favorite=None, search=None, date_from=None, date_to=None,
                 source_id=None, unanalyzed_only=False):
    conn = get_connection()
    q = "SELECT a.*, s.name as source_name, s.economic_axis as source_economic, s.authority_axis as source_authority FROM articles a LEFT JOIN sources s ON a.source_id=s.id WHERE (s.active=1 OR s.id IS NULL)"
    params = []
    if category:       q += " AND (a.category=? OR a.ai_category LIKE ?)"; params += [category, f"%{category}%"]
    if language:       q += " AND a.language=?"; params.append(language)
    if is_read is not None: q += " AND a.is_read=?"; params.append(int(is_read))
    if is_favorite is not None: q += " AND a.is_favorite=?"; params.append(int(is_favorite))
    if search:         q += " AND (a.title LIKE ? OR a.summary LIKE ?)"; params += [f"%{search}%",f"%{search}%"]
    if date_from:      q += " AND a.published_at>=?"; params.append(date_from)
    if date_to:        q += " AND a.published_at<=?"; params.append(date_to)
    if source_id:      q += " AND a.source_id=?"; params.append(source_id)
    if unanalyzed_only: q += " AND a.analysis_done=0 AND a.analysis_queued=0"
    q += " ORDER BY a.published_at DESC,a.fetched_at DESC LIMIT ? OFFSET ?"; params += [limit,offset]
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def deactivate_source(source_id: int) -> None:
    """Desativa uma fonte (mantém artigos existentes)."""
    conn = get_connection()
    conn.execute("UPDATE sources SET active=0 WHERE id=?", (source_id,))
    conn.commit(); conn.close()

def delete_source(source_id: int, delete_articles: bool = False) -> int:
    """
    Exclui permanentemente uma fonte do banco.
    Se delete_articles=True, remove também todos os artigos dessa fonte.
    Retorna o número de artigos deletados (0 se delete_articles=False).
    """
    conn = get_connection()
    deleted = 0
    if delete_articles:
        row = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE source_id=?", (source_id,)
        ).fetchone()
        deleted = row[0] if row else 0
        conn.execute("DELETE FROM articles WHERE source_id=?", (source_id,))
    conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
    conn.commit(); conn.close()
    return deleted

def get_article(article_id):
    conn = get_connection()
    row = conn.execute("SELECT a.*,s.name as source_name,s.url as source_url,s.economic_axis as source_economic,s.authority_axis as source_authority FROM articles a LEFT JOIN sources s ON a.source_id=s.id WHERE a.id=?", (article_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def mark_read(article_id, value=True):
    conn = get_connection()
    conn.execute("UPDATE articles SET is_read=? WHERE id=?", (int(value),article_id))
    conn.commit()
    conn.close()

def toggle_favorite(article_id):
    conn = get_connection()
    row = conn.execute("SELECT is_favorite FROM articles WHERE id=?", (article_id,)).fetchone()
    new_val = 0 if (row and row["is_favorite"]) else 1
    conn.execute("UPDATE articles SET is_favorite=? WHERE id=?", (new_val,article_id))
    conn.commit()
    conn.close()
    return bool(new_val)

def update_article_analysis(article_id, **kwargs):
    if not kwargs: return
    kwargs["analysis_done"] = 1; kwargs["analysis_queued"] = 0
    fields = ", ".join(f"{k}=?" for k in kwargs)
    conn = get_connection()
    conn.execute(f"UPDATE articles SET {fields} WHERE id=?", list(kwargs.values())+[article_id])
    conn.commit()
    conn.close()

def mark_queued(article_ids):
    if not article_ids: return
    conn = get_connection()
    conn.executemany("UPDATE articles SET analysis_queued=1 WHERE id=?", [(i,) for i in article_ids])
    conn.commit()
    conn.close()

def get_unanalyzed_articles(limit=50):
    return get_articles(limit=limit, unanalyzed_only=True)

def save_translation(article_id, target_lang, title=None, content=None, summary=None):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO translations (article_id,target_language,title_translated,content_translated,summary_translated) VALUES (?,?,?,?,?)", (article_id,target_lang,title,content,summary))
    conn.commit()
    conn.close()

def get_translation(article_id, target_lang):
    conn = get_connection()
    row = conn.execute("SELECT * FROM translations WHERE article_id=? AND target_language=?", (article_id,target_lang)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_alert_rules():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM alert_rules WHERE active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_alert_rule(rule_type, value):
    conn = get_connection()
    conn.execute("INSERT INTO alert_rules (type,value) VALUES (?,?)", (rule_type,value))
    conn.commit()
    conn.close()

def save_trending_cluster(label, keywords, article_ids, source_count):
    conn = get_connection()
    conn.execute("INSERT INTO trending_clusters (label,keywords,article_ids,source_count) VALUES (?,?,?,?)", (label,json.dumps(keywords),json.dumps(article_ids),source_count))
    conn.commit()
    conn.close()

def get_trending_clusters(limit=10):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM trending_clusters WHERE detected_at>=datetime('now','-6 hours') ORDER BY source_count DESC,detected_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["keywords"] = json.loads(d["keywords"] or "[]")
        d["article_ids"] = json.loads(d["article_ids"] or "[]")
        result.append(d)
    return result

def save_social_posts(posts):
    conn = get_connection()
    for p in posts:
        try:
            conn.execute("INSERT OR IGNORE INTO social_posts (platform,post_id,author,content,url,score,comments,published_at,category) VALUES (?,?,?,?,?,?,?,?,?)",
                (p.get("platform"),p.get("post_id"),p.get("author"),p.get("content"),p.get("url"),p.get("score",0),p.get("comments",0),p.get("published_at"),p.get("category")))
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_social_posts(platform=None, limit=50):
    conn = get_connection()
    q = "SELECT * FROM social_posts WHERE 1=1"
    params = []
    if platform: q += " AND platform=?"; params.append(platform)
    q += " ORDER BY score DESC,fetched_at DESC LIMIT ?"; params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_dashboard_data():
    conn = get_connection()
    sp = conn.execute("SELECT s.id,s.name,s.economic_axis,s.authority_axis,s.political_confirmed,COUNT(a.id) as article_count FROM sources s LEFT JOIN articles a ON a.source_id=s.id AND a.fetched_at>=datetime('now','-7 days') WHERE s.active=1 GROUP BY s.id ORDER BY s.economic_axis").fetchall()
    tone = conn.execute("SELECT s.name,a.emotional_tone,COUNT(*) as count FROM articles a JOIN sources s ON a.source_id=s.id WHERE a.emotional_tone IS NOT NULL AND a.fetched_at>=datetime('now','-7 days') GROUP BY s.name,a.emotional_tone").fetchall()
    cb = conn.execute("SELECT s.name,AVG(a.clickbait_score) as avg_score FROM articles a JOIN sources s ON a.source_id=s.id WHERE a.clickbait_score IS NOT NULL GROUP BY s.name ORDER BY avg_score DESC LIMIT 12").fetchall()
    tl = conn.execute("SELECT date(a.published_at) as day,s.name as source,AVG(a.economic_axis) as avg_economic,AVG(a.authority_axis) as avg_authority FROM articles a JOIN sources s ON a.source_id=s.id WHERE a.economic_axis IS NOT NULL AND a.published_at>=datetime('now','-30 days') GROUP BY day,source ORDER BY day").fetchall()
    cat = conn.execute("SELECT COALESCE(ai_category,category) as cat,COUNT(*) as count FROM articles WHERE fetched_at>=datetime('now','-1 day') GROUP BY cat ORDER BY count DESC").fetchall()
    conn.close()
    return {"sources_political":[dict(r) for r in sp],"tone_by_source":[dict(r) for r in tone],"clickbait":[dict(r) for r in cb],"bias_timeline":[dict(r) for r in tl],"by_category":[dict(r) for r in cat]}
# ── Arquivo (pastas com tags) ────────────────────────────────────────────────

def get_archive_tags():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT tag FROM archive_items ORDER BY tag").fetchall()
    conn.close()
    return [r["tag"] for r in rows]

def get_archive_items(tag=None, search=None):
    conn = get_connection()
    q = """SELECT ar.*, a.title, a.url, a.summary, a.ai_summary, a.published_at,
                  a.emotional_tone, a.clickbait_score, a.economic_axis, a.authority_axis,
                  a.ai_keywords, a.ai_category, a.category,
                  s.name as source_name, s.economic_axis as source_economic, s.authority_axis as source_authority
           FROM archive_items ar
           JOIN articles a ON ar.article_id = a.id
           LEFT JOIN sources s ON a.source_id = s.id
           WHERE 1=1"""
    params = []
    if tag:
        q += " AND ar.tag=?"; params.append(tag)
    if search:
        q += " AND (a.title LIKE ? OR ar.note LIKE ?)"; params += [f"%{search}%", f"%{search}%"]
    q += " ORDER BY ar.saved_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_to_archive(article_id, tags: list, note=""):
    conn = get_connection()
    for tag in tags:
        tag = tag.strip()
        if tag:
            conn.execute(
                "INSERT OR IGNORE INTO archive_items (article_id, tag, note) VALUES (?,?,?)",
                (article_id, tag, note)
            )
    conn.commit()
    conn.close()

def remove_from_archive(article_id, tag=None):
    conn = get_connection()
    if tag:
        conn.execute("DELETE FROM archive_items WHERE article_id=? AND tag=?", (article_id, tag))
    else:
        conn.execute("DELETE FROM archive_items WHERE article_id=?", (article_id,))
    conn.commit()
    conn.close()

def is_archived(article_id):
    conn = get_connection()
    rows = conn.execute("SELECT tag FROM archive_items WHERE article_id=?", (article_id,)).fetchall()
    conn.close()
    return [r["tag"] for r in rows]

def rename_archive_tag(old_tag, new_tag):
    conn = get_connection()
    conn.execute("UPDATE archive_items SET tag=? WHERE tag=?", (new_tag, old_tag))
    conn.commit()
    conn.close()

def delete_archive_tag(tag):
    conn = get_connection()
    conn.execute("DELETE FROM archive_items WHERE tag=?", (tag,))
    conn.commit()
    conn.close()


# ── Controle de limite de data por fonte ─────────────────────────────────────

def _ensure_source_date_limit_col():
    """Garante que a coluna date_limit_days existe na tabela sources."""
    conn = get_connection()
    _add_col(conn.cursor(), "sources", "date_limit_days", "INTEGER DEFAULT NULL")
    conn.commit()
    conn.close()

def get_source_date_limit(source_id: int):
    """
    Retorna datetime do limite mais antigo para esta fonte.
    Prioridade: limite da fonte > limite global > padrão (30 dias).
    Retorna None se não há limite configurado.
    """
    from datetime import datetime, timezone, timedelta
    _ensure_source_date_limit_col()

    conn = get_connection()
    row = conn.execute("SELECT date_limit_days FROM sources WHERE id=?", (source_id,)).fetchone()
    conn.close()

    # Limite da fonte tem prioridade
    if row and row["date_limit_days"] is not None:
        days = row["date_limit_days"]
        if days == 0:  # 0 = sem limite para esta fonte
            return None
        return datetime.now(timezone.utc) - timedelta(days=days)

    # Limite global
    global_days = get_setting("article_max_age_days", None)
    if global_days is None:
        # Pergunta já foi respondida? Usa padrão de 30 dias se sim.
        asked = get_setting("date_limit_asked", "0")
        if asked == "1":
            global_days = get_setting("article_max_age_days", "30")
        else:
            return None  # ainda não configurado — sem limite por ora

    days = int(global_days)
    if days == 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)

def set_source_date_limit(source_id: int, days: int):
    """Define limite de dias para uma fonte específica. 0 = sem limite."""
    _ensure_source_date_limit_col()
    conn = get_connection()
    conn.execute("UPDATE sources SET date_limit_days=? WHERE id=?", (days, source_id))
    conn.commit()
    conn.close()
