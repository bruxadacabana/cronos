"""
Cronos - AnalysisQueue
Fila de análise automática em QThread com suporte a Multi-Tags e Fatiamento (Chunking).
"""
import json, logging, re, time
from collections import deque
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

logger = logging.getLogger("cronos.analyzer")

ANALYSIS_PROMPT = """Você é um analista de dados e mídia experiente e imparcial. Analise a parte da notícia abaixo e responda APENAS com um objeto JSON válido.

Notícia:
Título: {title}
Conteúdo: {content}

Responda com este JSON exato (sem campos extras, sem markdown):
{{
  "summary": "Resumo detalhado desta parte em 1 a 2 parágrafos curtos, destacando os argumentos",
  "categories": ["tema principal", "subtema", "alinhamento político (se houver)"],
  "keywords": ["palavra1", "palavra2", "palavra3"],
  "emotional_tone": "um de: neutro|positivo|negativo|alarmista|esperancoso|indignado|celebrativo",
  "clickbait_score": 0.0,
  "economic_axis": 0.0,
  "authority_axis": 0.0,
  "implications": "Implicações principais em 1 frase curta",
  "5ws": {{
    "who": "quem", "what": "o que", "when": "quando", "where": "onde", "why": "por que"
  }}
}}

Regras:
- categories: Extraia de 2 a 5 temas. Inclua categorias amplas (ex: Tecnologia), específicas (ex: IA) e o alinhamento político/ideológico (ex: Centro-Direita, Progressista, Libertário).
- clickbait_score: 0.0 (sem clickbait) a 1.0 (puro clickbait)
- economic_axis: -1.0 (esquerda econômica) a +1.0 (direita econômica), 0.0 = neutro
- authority_axis: -1.0 (libertário) a +1.0 (autoritário), 0.0 = neutro
- Responda SOMENTE o JSON."""


class AnalysisWorker(QThread):
    article_analyzed = pyqtSignal(int, dict)
    progress = pyqtSignal(int, int)
    finished_batch = pyqtSignal()

    def prioritize_article(self, article_id: int):
        from core.database import get_article
        art = get_article(article_id)
        if not art: return

        with QMutexLocker(self._mutex):
            if hasattr(self, '_queue'):
                nova_fila = deque()
                for a in self._queue:
                    if a.get("id") != article_id:
                        nova_fila.append(a)
                nova_fila.appendleft(art)
                self._queue = nova_fila

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = deque()
        self._mutex = QMutex()
        self._running = True
        self._processing = False

    def enqueue(self, articles: list):
        with QMutexLocker(self._mutex):
            for a in articles:
                self._queue.append(a)
        if not self._processing:
            self.start()

    def stop(self):
        self._running = False
        self.quit()

    def run(self):
        from core.ai import is_ollama_available, _ollama_generate
        from core.database import update_article_analysis
        from core.fetcher import chunk_article_text

        self._processing = True
        done = 0

        while self._running:
            with QMutexLocker(self._mutex):
                if not self._queue:
                    break
                article = self._queue.popleft()

            total = done + len(self._queue) + 1
            self.progress.emit(done, total)

            if not is_ollama_available():
                logger.warning("IA indisponível — pausando análise")
                time.sleep(30)
                with QMutexLocker(self._mutex):
                    self._queue.appendleft(article)
                continue

            art_id = article.get("id")
            title   = article.get("title", "")
            content_full = article.get("content_clean") or article.get("summary", "")

            if not title or not content_full:
                continue

            # Corta o texto em fatias de 15.000 caracteres para não sobrecarregar a memória de contexto
            chunks = chunk_article_text(content_full, chunk_size=15000)
            all_results = []

            for i, chunk in enumerate(chunks):
                prompt = ANALYSIS_PROMPT.format(title=title, content=chunk)
                try:
                    logger.info(f"A analisar parte {i+1}/{len(chunks)} do artigo {art_id}")
                    raw = _ollama_generate(prompt, max_tokens=600, timeout=60)
                    res = _parse_analysis(raw)
                    if res:
                        all_results.append(res)
                except Exception as e:
                    logger.error(f"Erro ao analisar parte {i+1} do artigo {art_id}: {e}")
                time.sleep(0.5)

            if all_results:
                final_result = self._merge_results(all_results)
                update_article_analysis(art_id, **final_result)
                self.article_analyzed.emit(art_id, final_result)
                logger.info(f"Analisado artigo {art_id} completo")

            done += 1

        self._processing = False
        self.finished_batch.emit()

    def _merge_results(self, results: list) -> dict:
        """Junta as análises de todas as fatias num único resultado final."""
        if len(results) == 1:
            return results[0]
            
        final = {}
        
        # Junta os resumos com duas quebras de linha
        summaries = [r.get("ai_summary", "") for r in results if r.get("ai_summary")]
        final["ai_summary"] = "\n\n".join(summaries)[:3000]
        
        # Junta todas as tags de categorias sem duplicados
        all_tags = []
        for r in results:
            cat_str = r.get("ai_category", "")
            if cat_str:
                all_tags.extend([t.strip() for t in cat_str.split(",")])
        unique_tags = list(dict.fromkeys(all_tags))
        final["ai_category"] = ", ".join(unique_tags[:8])
        
        # Média das pontuações matemáticas
        for key in ["clickbait_score", "economic_axis", "authority_axis"]:
            vals = [r.get(key, 0.0) for r in results if isinstance(r.get(key), (int, float))]
            if vals:
                final[key] = sum(vals) / len(vals)
                
        # Tom emocional mais frequente
        tones = [r.get("emotional_tone") for r in results if r.get("emotional_tone")]
        if tones:
            final["emotional_tone"] = max(set(tones), key=tones.count)
            
        # Factos principais (usamos o da primeira fatia) e conclusões (da última)
        final["ai_5ws"] = results[0].get("ai_5ws", "{}")
        final["ai_implications"] = results[-1].get("ai_implications", "")
        
        return final


def _parse_analysis(raw: str) -> dict:
    """Extrai JSON da resposta da IA com fallbacks robustos."""
    if not raw: return {}
    raw = raw.strip()
    
    # A REGRA CORRIGIDA ESTÁ AQUI: Usa {3} em vez de três aspas literais para evitar corte.
    raw = re.sub(r"`{3}(?:json)?", "", raw).strip().rstrip("`")
    
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0: return {}
    json_str = raw[start:end]
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        try:
            data = json.loads(json_str)
        except Exception:
            return {}

    result = {}
    if isinstance(data.get("summary"), str):
        result["ai_summary"] = data["summary"][:500]
        
    # Processa a lista de Multi-Tags e salva como texto separado por vírgulas
    if isinstance(data.get("categories"), list):
        result["ai_category"] = ", ".join(str(c).strip() for c in data["categories"][:5])
    elif isinstance(data.get("category"), str):
        result["ai_category"] = data["category"]

    if isinstance(data.get("keywords"), list):
        result["ai_keywords"] = ", ".join(str(k) for k in data["keywords"][:6])
    if isinstance(data.get("emotional_tone"), str):
        result["emotional_tone"] = data["emotional_tone"]
    if isinstance(data.get("clickbait_score"), (int, float)):
        result["clickbait_score"] = max(0.0, min(1.0, float(data["clickbait_score"])))
    if isinstance(data.get("economic_axis"), (int, float)):
        result["economic_axis"] = max(-1.0, min(1.0, float(data["economic_axis"])))
    if isinstance(data.get("authority_axis"), (int, float)):
        result["authority_axis"] = max(-1.0, min(1.0, float(data["authority_axis"])))
    if isinstance(data.get("implications"), str):
        result["ai_implications"] = data["implications"][:300]
    if isinstance(data.get("5ws"), dict):
        result["ai_5ws"] = json.dumps(data["5ws"], ensure_ascii=False)
        
    return result