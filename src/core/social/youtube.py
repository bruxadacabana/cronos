"""Cronos - YouTube trending via Data API v3."""
import logging
logger = logging.getLogger("cronos.social.youtube")

def fetch_youtube(api_key: str, region="BR", limit=20) -> list:
    if not api_key:
        return []
    try:
        import httpx
        r = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                      params={"part":"snippet,statistics","chart":"mostPopular",
                              "regionCode":region,"maxResults":limit,"key":api_key},
                      timeout=10)
        items = r.json().get("items", [])
        posts = []
        for it in items:
            sn = it.get("snippet", {})
            st = it.get("statistics", {})
            posts.append({
                "platform": "youtube",
                "post_id": it.get("id",""),
                "author": sn.get("channelTitle",""),
                "content": sn.get("title","") + "\n" + sn.get("description","")[:200],
                "url": f"https://youtube.com/watch?v={it.get('id','')}",
                "score": int(st.get("likeCount",0) or 0),
                "comments": int(st.get("commentCount",0) or 0),
                "published_at": sn.get("publishedAt"),
                "category": "youtube",
            })
        return posts
    except Exception as e:
        logger.error(f"YouTube: {e}")
        return []
