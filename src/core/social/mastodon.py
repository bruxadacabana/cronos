"""Cronos - Mastodon timeline pública."""
import logging, httpx
logger = logging.getLogger("cronos.social.mastodon")

def fetch_mastodon(instance="mastodon.social", limit=30) -> list:
    import html, re
    try:
        r = httpx.get(f"https://{instance}/api/v1/timelines/public",
                      params={"limit": limit, "local": False}, timeout=12)
        posts = []
        for s in r.json():
            content = html.unescape(re.sub(r'<[^>]+>', ' ', s.get("content",""))).strip()[:500]
            if not content: continue
            posts.append({
                "platform": "mastodon",
                "post_id": str(s.get("id","")),
                "author": s.get("account",{}).get("acct",""),
                "content": content,
                "url": s.get("url",""),
                "score": s.get("favourites_count",0),
                "comments": s.get("replies_count",0),
                "published_at": s.get("created_at"),
                "category": "geral",
            })
        return posts
    except Exception as e:
        logger.error(f"Mastodon {instance}: {e}")
        return []
