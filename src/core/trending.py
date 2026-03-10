"""
Cronos - Detecção de Trending
Híbrido: Jaccard nas palavras-chave → Ollama nomeia clusters.
"""
import re, json, logging, math
from collections import defaultdict, Counter
from datetime import datetime, timedelta

logger = logging.getLogger("cronos.trending")

STOPWORDS = {
    "de","da","do","das","dos","em","no","na","nos","nas","um","uma","uns","umas",
    "o","a","os","as","e","é","para","por","com","que","se","seu","sua","seus","suas",
    "ele","ela","eles","elas","ao","aos","à","às","ou","mais","mas","foi","são","ser",
    "como","sobre","após","entre","até","quando","the","of","in","to","a","is","for",
    "and","or","that","this","with","on","at","by","from","an","be","was","are","were",
    "it","its","as","he","she","they","have","has","had","will","would","could","been",
}

def _tokenize(text: str) -> set:
    words = re.findall(r'\b[a-záàâãéèêíïóôõöúüçñ]{3,}\b', text.lower())
    return {w for w in words if w not in STOPWORDS}

def _jaccard(a: set, b: set) -> float:
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)

def detect_trending(articles: list, threshold=0.22, min_sources=2) -> list:
    """
    Agrupa artigos por similaridade de título (Jaccard).
    Retorna clusters com source_count >= min_sources.
    """
    if not articles:
        return []

    # Tokeniza títulos + keywords
    tokens = []
    for a in articles:
        t = _tokenize((a.get("title","")) + " " + (a.get("ai_keywords","") or ""))
        tokens.append(t)

    # Clustering guloso
    clusters = []
    assigned = [False] * len(articles)

    for i, art in enumerate(articles):
        if assigned[i]:
            continue
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, len(articles)):
            if assigned[j]:
                continue
            if _jaccard(tokens[i], tokens[j]) >= threshold:
                cluster.append(j)
                assigned[j] = True
        # Verifica diversidade de fontes
        source_ids = {articles[k].get("source_id") for k in cluster}
        if len(source_ids) >= min_sources:
            clusters.append(cluster)

    # Monta resultado
    result = []
    for cl in sorted(clusters, key=lambda c: len(c), reverse=True)[:12]:
        arts = [articles[i] for i in cl]
        source_ids = {a.get("source_id") for a in arts}
        # Palavras mais frequentes como label provisório
        all_words = Counter()
        for a in arts:
            all_words.update(_tokenize(a.get("title", "")))
        top_words = [w for w, _ in all_words.most_common(6)]
        label = " · ".join(w.capitalize() for w in top_words[:3]) or "Trending"
        result.append({
            "label": label,
            "keywords": top_words,
            "article_ids": [a["id"] for a in arts if a.get("id")],
            "source_count": len(source_ids),
            "articles": arts,
        })
    return result


def refine_with_ollama(cluster: dict) -> str:
    """Usa Ollama para gerar um título mais legível para o cluster."""
    try:
        from core.ai import _ollama_generate, is_ollama_available
        if not is_ollama_available():
            return cluster["label"]
        titles = "\n".join(f"- {a.get('title','')}" for a in cluster.get("articles",[])[:5])
        prompt = f"""Dado este grupo de notícias cobrindo o mesmo evento:
{titles}

Gere UM título curto e descritivo (máximo 8 palavras) que resume o assunto em comum.
Responda APENAS o título, sem aspas, sem pontuação no final."""
        result = _ollama_generate(prompt, max_tokens=40, timeout=15)
        if result and len(result.strip()) > 3:
            return result.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Ollama refine falhou: {e}")
    return cluster["label"]
