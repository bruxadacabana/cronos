import feedparser

def fetch_substack(urls_string):
    posts = []
    if not urls_string:
        return posts

    # Separa as URLs que você vai digitar nas configurações
    urls = [u.strip() for u in urls_string.split(',') if u.strip()]

    for url in urls:
        # Garante que a URL termine com /feed para puxar o RSS
        if not url.endswith('/feed'):
            url = url.rstrip('/') + '/feed'

        try:
            feed = feedparser.parse(url)
            author = feed.feed.get('title', 'Substack')

            # Pega os 5 posts mais recentes de cada newsletter
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')
                
                posts.append({
                    "platform": "substack",
                    "author": author,
                    # Junta o título e o resumo para o card social
                    "content": f"【 {title} 】\n\n{summary}",
                    "category": "Newsletter",
                    "url": entry.get('link', '')
                })
        except Exception:
            continue

    return posts