"""Cronos - Reddit scraper via PRAW."""
import logging
logger = logging.getLogger("cronos.social.reddit")

def fetch_reddit(subreddits: str, limit=25) -> list:
    try:
        import praw
        from core.database import get_setting
        cid = get_setting("reddit_client_id","")
        csec = get_setting("reddit_client_secret","")
        if not cid or not csec:
            return _fetch_rss_fallback(subreddits, limit)
        r = praw.Reddit(client_id=cid, client_secret=csec, user_agent="Cronos/1.2")
        posts = []
        for sub in subreddits.split(","):
            sub = sub.strip()
            if not sub: continue
            try:
                for p in r.subreddit(sub).hot(limit=limit//max(1,len(subreddits.split(",")))):
                    posts.append({
                        "platform": "reddit",
                        "post_id": p.id,
                        "author": str(p.author),
                        "content": p.title + ("\n" + p.selftext[:300] if p.selftext else ""),
                        "url": f"https://reddit.com{p.permalink}",
                        "score": p.score,
                        "comments": p.num_comments,
                        "published_at": None,
                        "category": sub,
                    })
            except Exception as e:
                logger.warning(f"Subreddit {sub}: {e}")
        return posts
    except ImportError:
        return _fetch_rss_fallback(subreddits, limit)

def _fetch_rss_fallback(subreddits, limit):
    """Fallback: RSS público do Reddit (sem autenticação)."""
    import feedparser, html, re
    posts = []
    for sub in subreddits.split(","):
        sub = sub.strip()
        if not sub: continue
        try:
            feed = feedparser.parse(f"https://www.reddit.com/r/{sub}/hot.rss")
            for e in feed.entries[:limit]:
                content = html.unescape(re.sub(r'<[^>]+>', '', e.get("summary",""))).strip()[:400]
                posts.append({
                    "platform": "reddit",
                    "post_id": e.get("id",""),
                    "author": e.get("author",""),
                    "content": e.get("title","") + ("\n" + content if content else ""),
                    "url": e.get("link",""),
                    "score": 0,
                    "comments": 0,
                    "published_at": None,
                    "category": sub,
                })
        except Exception as ex:
            logger.warning(f"RSS fallback {sub}: {ex}")
    return posts
