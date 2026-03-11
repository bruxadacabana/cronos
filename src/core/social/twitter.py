"""
Cronos - Twitter/X via twscrape
Desativado por padrão. Requer credenciais configuradas pelo usuário.
"""
import logging
logger = logging.getLogger("cronos.social.twitter")

def fetch_twitter(username: str, password: str, queries=None, limit=20) -> list:
    """Tenta buscar posts do Twitter/X usando twscrape."""
    if not username or not password:
        logger.info("Twitter: credenciais não configuradas")
        return []
    try:
        import asyncio
        from twscrape import API as TwAPI, gather
        async def _run():
            api = TwAPI(str(__import__('pathlib').Path(__file__).parent.parent.parent.parent / "data" / "social" / "twitter_accounts.db"))
            accounts = await api.pool.get_all()
            if not accounts:
                await api.pool.add_account(username, password, "", "")
                await api.pool.login_all()
            posts = []
            search_q = " OR ".join(queries or ["breaking news", "notícias"])
            async for t in api.search(search_q, limit=limit):
                posts.append({
                    "platform": "twitter",
                    "post_id": str(t.id),
                    "author": t.user.username,
                    "content": t.rawContent,
                    "url": t.url,
                    "score": t.likeCount,
                    "comments": t.replyCount,
                    "published_at": t.date.isoformat() if t.date else None,
                    "category": "geral",
                })
            return posts
        return asyncio.run(_run())
    except ImportError:
        logger.warning("twscrape não instalado. Instale com: pip install twscrape")
        return []
    except Exception as e:
        logger.error(f"Twitter: {e}")
        return []
