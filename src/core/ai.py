"""
Cronos - Módulo de IA (Ollama)
Integração com Ollama para resumo, análise política, tom emocional,
detecção de clickbait e tradução.
"""

import httpx
import json
import logging
import re
import time
from typing import Optional
from pathlib import Path

from .database import get_setting, get_connection

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "logs"
logger = logging.getLogger("cronos.ai")

TIMEOUT = 60  # segundos — modelos locais podem ser lentos


def _get_ollama_url() -> str:
    return get_setting("ollama_url", "http://localhost:11434")


def _get_model() -> str:
    return get_setting("ollama_model", "llama3")


def is_ollama_available() -> bool:
    """Verifica se o Ollama está rodando e acessível."""
    try:
        resp = httpx.get(f"{_get_ollama_url()}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False

def query_ollama(prompt: str, max_tokens: int = 600) -> str:
    """Interface pública para o analyzer.py e outros módulos."""
    return _query(prompt, max_tokens=max_tokens) or ""

def _ollama_generate(prompt: str, max_tokens: int = 600, timeout: int = 60) -> str:
    """Alias direto para uso interno (analyzer, trending)."""
    return _query(prompt, max_tokens=max_tokens, timeout=timeout) or ""



def get_available_models() -> list:
    """Retorna lista de modelos disponíveis no Ollama."""
    try:
        resp = httpx.get(f"{_get_ollama_url()}/api/tags", timeout=5)
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _query(prompt: str, system: str = "", model: str = None,
           max_tokens: int = 600, timeout: int = None) -> Optional[str]:
    """
    Faz uma query ao Ollama. Retorna texto da resposta ou None se falhar.
    Não verifica is_ollama_available() aqui — evita HTTP extra antes de cada chamada.
    """
    model = model or _get_model()
    effective_timeout = timeout or TIMEOUT
    payload = {
        "model": model,
        "stream": False,
        "think": False,          # desativa thinking mode (qwen3, deepseek-r1) — nível raiz
        "options": {
            "num_predict": max_tokens,
        },
        "messages": [],
    }

    if system:
        payload["messages"].append({"role": "system", "content": system})
    payload["messages"].append({"role": "user", "content": prompt})

    _t0 = time.monotonic()
    try:
        resp = httpx.post(
            f"{_get_ollama_url()}/api/chat",
            json=payload,
            timeout=effective_timeout
        )
        resp.raise_for_status()
        data = resp.json()

        # Extrair conteúdo — suporta /api/chat e variantes cloud
        message_obj = data.get("message", {}) or {}
        content = (
            message_obj.get("content") or
            message_obj.get("text") or
            data.get("response") or
            data.get("content") or
            ""
        ).strip()

        # qwen3: thinking pode vir em campo separado; se content vazio, usa thinking
        thinking = (message_obj.get("thinking") or
                    message_obj.get("reasoning_content") or
                    message_obj.get("reasoning") or "")
        if thinking and not content:
            content = thinking.strip()

        elapsed = time.monotonic() - _t0

        # Log diagnóstico — mostra estrutura da resposta e primeiros 300 chars
        logger.debug(
            f"Ollama resp keys={list(data.keys())} "
            f"msg_keys={list(message_obj.keys())} "
            f"content({len(content)}c)={content[:300]!r}"
        )

        # Se ainda vazio, tentar /api/generate como fallback
        if not content:
            logger.debug("Tentando /api/generate como fallback...")
            gen_payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens, "think": False},
            }
            resp2 = httpx.post(
                f"{_get_ollama_url()}/api/generate",
                json=gen_payload,
                timeout=effective_timeout
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            content = (data2.get("response") or "").strip()
            logger.debug(f"/api/generate content({len(content)}c)={content[:300]!r}")

        try:
            from core.log_setup import log_ollama_call
            log_ollama_call(len(prompt), max_tokens, effective_timeout,
                            success=True, elapsed=elapsed)
        except Exception:
            logger.debug(f"Ollama OK — {elapsed:.2f}s")
        return content
    except httpx.TimeoutException:
        elapsed = time.monotonic() - _t0
        try:
            from core.log_setup import log_ollama_call
            log_ollama_call(len(prompt), max_tokens, effective_timeout,
                            success=False, elapsed=elapsed,
                            error=f"Timeout após {effective_timeout}s")
        except Exception:
            logger.error(f"Ollama timeout após {effective_timeout}s ({elapsed:.1f}s decorridos)")
        return None
    except Exception as e:
        elapsed = time.monotonic() - _t0
        try:
            from core.log_setup import log_ollama_call
            log_ollama_call(len(prompt), max_tokens, effective_timeout,
                            success=False, elapsed=elapsed, error=str(e))
        except Exception:
            logger.error(f"Ollama error após {elapsed:.1f}s: {e}")
        return None


# ─── Resumo ───────────────────────────────────────────────────────────────────

def summarize_article(title: str, content: str, language: str = "pt") -> Optional[str]:
    """Gera um resumo conciso do artigo."""
    lang_name = {"pt": "português", "en": "inglês", "es": "espanhol"}.get(language, language)

    system = f"""Você é um assistente especializado em resumir notícias de forma objetiva e imparcial.
Responda sempre em {lang_name}. Seja conciso e factual. Máximo 3 frases."""

    prompt = f"""Resuma a seguinte notícia em 2-3 frases objetivas:

Título: {title}

Conteúdo: {content[:2000]}

Resumo:"""

    return _query(prompt, system)


# ─── Análise Política ─────────────────────────────────────────────────────────

def analyze_political_bias(title: str, content: str) -> Optional[dict]:
    """
    Analisa o viés político de um artigo.
    Retorna dict com score (-1.0 a 1.0) e justificativa.
    -1.0 = extrema esquerda, 0.0 = neutro, 1.0 = extrema direita
    """
    system = """Você é um analista político imparcial especializado em detectar viés em textos jornalísticos.
Analise o texto e retorne APENAS um JSON válido, sem explicações adicionais."""

    prompt = f"""Analise o viés político desta notícia e retorne um JSON com este formato exato:
{{
  "score": <número de -1.0 a 1.0>,
  "label": "<extrema-esquerda|esquerda|centro-esquerda|centro|centro-direita|direita|extrema-direita>",
  "confidence": <0.0 a 1.0>,
  "reasoning": "<justificativa em 1 frase>",
  "indicators": ["<indicador1>", "<indicador2>"]
}}

Onde:
- score -1.0 = extrema esquerda, 0.0 = neutro/centro, 1.0 = extrema direita
- confidence = quão confiante você está na análise

Título: {title}
Conteúdo: {content[:1500]}

JSON:"""

    result = _query(prompt, system)
    if not result:
        return None

    try:
        # Extrai JSON da resposta
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        logger.warning(f"Falha ao parsear JSON de análise política: {result[:100]}")
    return None


# ─── Tom Emocional ────────────────────────────────────────────────────────────

def analyze_emotional_tone(title: str, content: str) -> Optional[dict]:
    """
    Analisa o tom emocional de um artigo.
    Retorna dict com tone, score e indicadores.
    """
    system = """Você é um analista de linguagem especializado em detectar o tom emocional de textos jornalísticos.
Retorne APENAS um JSON válido."""

    prompt = f"""Analise o tom emocional desta notícia e retorne um JSON com este formato:
{{
  "tone": "<neutro|positivo|negativo|alarmista|esperançoso|indignado|celebrativo>",
  "intensity": <0.0 a 1.0>,
  "emotional_words": ["<palavra1>", "<palavra2>", "<palavra3>"],
  "reasoning": "<justificativa em 1 frase>"
}}

Título: {title}
Conteúdo: {content[:1200]}

JSON:"""

    result = _query(prompt, system)
    if not result:
        return None

    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return None


# ─── Clickbait ────────────────────────────────────────────────────────────────

def analyze_clickbait(title: str, content: str = "") -> Optional[dict]:
    """
    Detecta linguagem sensacionalista/clickbait no título e conteúdo.
    Retorna score de 0.0 (nada) a 1.0 (extremo clickbait).
    """
    system = """Você é um especialista em identificar títulos e textos sensacionalistas e clickbait.
Retorne APENAS um JSON válido."""

    prompt = f"""Analise se este título é clickbait/sensacionalista:

Título: {title}
{f'Conteúdo (primeiras linhas): {content[:500]}' if content else ''}

Retorne JSON:
{{
  "score": <0.0 a 1.0>,
  "label": "<não-clickbait|levemente-sensacionalista|clickbait|extremo-clickbait>",
  "tactics": ["<tática usada se houver>"],
  "reasoning": "<justificativa em 1 frase>"
}}

JSON:"""

    result = _query(prompt, system)
    if not result:
        return None

    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return None


# ─── Classificação ────────────────────────────────────────────────────────────

def classify_article(title: str, content: str) -> Optional[str]:
    """Classifica o artigo em uma categoria."""
    categories = [
        "política", "economia", "tecnologia", "ciência", "saúde",
        "esportes", "cultura", "internacional", "brasil", "ambiente",
        "educação", "segurança", "entretenimento"
    ]

    system = "Você é um classificador de notícias. Responda APENAS com o nome da categoria."

    prompt = f"""Classifique esta notícia em UMA das categorias: {', '.join(categories)}

Título: {title}
Resumo: {content[:300]}

Categoria:"""

    result = _query(prompt, system)
    if result:
        result = result.lower().strip().split("\n")[0].split(".")[0]
        if result in categories:
            return result
    return "geral"


# ─── Comparação Multi-Fonte ───────────────────────────────────────────────────

def compare_articles(articles: list) -> Optional[dict]:
    """
    Compara como diferentes fontes cobriram o mesmo evento.
    articles = lista de dicts com {source_name, title, content}
    """
    if len(articles) < 2:
        return None

    system = """Você é um analista de mídia especializado em comparar coberturas jornalísticas.
Retorne APENAS um JSON válido."""

    sources_text = "\n\n".join([
        f"FONTE: {a['source_name']}\nTítulo: {a['title']}\nConteúdo: {a.get('content', a.get('summary', ''))[:600]}"
        for a in articles
    ])

    prompt = f"""Compare como estas fontes cobriram o mesmo evento:

{sources_text}

Retorne JSON:
{{
  "event_summary": "<resumo neutro do evento em 2 frases>",
  "differences": ["<diferença principal 1>", "<diferença 2>"],
  "most_neutral": "<nome da fonte mais neutra>",
  "most_biased": "<nome da fonte mais tendenciosa>",
  "tone_comparison": {{
    "<fonte1>": "<descrição do tom>",
    "<fonte2>": "<descrição do tom>"
  }},
  "key_omissions": ["<informação que alguma fonte omitiu>"]
}}

JSON:"""

    result = _query(prompt, system)
    if not result:
        return None

    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return None


# ─── Tradução ─────────────────────────────────────────────────────────────────

def translate_text(text: str, target_language: str, source_language: str = "auto") -> Optional[str]:
    """
    Traduz um texto usando Ollama.
    target_language: código ISO 639-1 (pt, en, es, fr, de, etc.)
    """
    lang_names = {
        "pt": "português brasileiro",
        "en": "inglês",
        "es": "espanhol",
        "fr": "francês",
        "de": "alemão",
        "it": "italiano",
        "ja": "japonês",
        "zh": "chinês",
        "ar": "árabe",
        "ru": "russo",
    }
    target_name = lang_names.get(target_language, target_language)

    system = f"""Você é um tradutor profissional. Traduza o texto fornecido para {target_name}.
Mantenha o mesmo tom e estilo do original. Retorne APENAS a tradução, sem explicações."""

    prompt = f"Traduza para {target_name}:\n\n{text[:3000]}"

    return _query(prompt, system)


# ─── Análise Completa ─────────────────────────────────────────────────────────

def full_analysis(article_id: int, title: str, content: str, language: str = "pt") -> dict:
    """
    Executa análise completa de um artigo e salva no banco.
    Retorna dict com todos os resultados.
    """
    from .database import update_article_analysis

    results = {}

    # Resumo
    summary = summarize_article(title, content, language)
    if summary:
        results["ai_summary"] = summary

    # Viés político
    bias = analyze_political_bias(title, content)
    if bias:
        results["political_bias"] = bias.get("score")

    # Tom emocional
    tone = analyze_emotional_tone(title, content)
    if tone:
        results["emotional_tone"] = tone.get("tone")

    # Clickbait
    cb = analyze_clickbait(title, content)
    if cb:
        results["clickbait_score"] = cb.get("score")

    # Categoria
    category = classify_article(title, content)
    if category:
        results["ai_category"] = category

    if results:
        update_article_analysis(article_id, **results)

    return results
