"""Cronos - Bluesky scraper via atproto."""
import logging
logger = logging.getLogger("cronos.social.bluesky")

def fetch_bluesky(limit=30) -> list:
    try:
        from atproto import Client
        c = Client()
        c.login("", "")  # público, sem auth necessário para feeds públicos
        feed = c.app.bsky.feed.get_timeline({"limit": limit})
        posts = []
        for item in feed.feed:
            p = item.post
            posts.append({
                "platform": "bluesky",
                "post_id": p.cid,
                "author": p.author.handle,
                "content": p.record.text if hasattr(p.record,'text') else "",
                "url": f"https://bsky.app/profile/{p.author.handle}",
                "score": p.like_count or 0,
                "comments": p.reply_count or 0,
                "published_at": None,
                "category": "geral",
            })
        return posts
    except Exception as e:
        return _fallback_bluesky(limit)

def _fallback_bluesky(limit):
    """Fallback: API pública do Bluesky sem auth."""
    import httpx
    try:
        r = httpx.get("https://public.api.bsky.app/xrpc/app.bsky.feed.getFeedGenerator",
                      params={"feed":"at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/whats-hot"},
                      timeout=10)
        data = r.json()
        posts = []
        for item in (data.get("feed") or [])[:limit]:
            p = item.get("post", {})
            rec = p.get("record", {})
            posts.append({
                "platform": "bluesky",
                "post_id": p.get("cid",""),
                "author": p.get("author",{}).get("handle",""),
                "content": rec.get("text",""),
                "url": "",
                "score": p.get("likeCount",0),
                "comments": p.get("replyCount",0),
                "published_at": None,
                "category": "geral",
            })
        return posts
    except Exception as e:
        logger.error(f"Bluesky fallback: {e}")
        return []
