"""
Cronos - AnalysisQueue v2.0
Dois níveis de análise:

  PRÉ-ANÁLISE (rápida, ~3s por artigo)
  ─────────────────────────────────────
  Roda em batch para TODOS os artigos novos.
  Extrai apenas: keywords, categoria, tom emocional, clickbait.
  Usa apenas o TÍTULO — sem precisar do conteúdo completo.
  Salva em ai_keywords, ai_category, emotional_tone, clickbait_score.

  ANÁLISE COMPLETA (profunda, ~15-30s por artigo)
  ────────────────────────────────────────────────
  Roda quando o usuário abre uma notícia (prioridade máxima)
  OU em background quando nenhuma notícia está aberta.
  Preenche: ai_summary, ai_implications, ai_5ws, economic_axis, authority_axis.
"""
import json, logging, re, time
from collections import deque
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

logger = logging.getLogger("cronos.analyzer")

# ── Prompt de pré-análise (só título, resposta pequena) ───────────────────────
PRE_ANALYSIS_PROMPT = """Analise o TÍTULO desta notícia e responda APENAS com JSON válido.

Título: {title}

JSON exato (sem markdown):
{{
  "keywords": ["palavra1", "palavra2", "palavra3"],
  "categories": ["tema principal", "subtema"],
  "emotional_tone": "neutro|positivo|negativo|alarmista|esperancoso|indignado|celebrativo",
  "clickbait_score": 0.0
}}

Regras:
- keywords: 3 a 6 termos-chave extraídos do título
- categories: 2 a 4 categorias temáticas
- clickbait_score: 0.0 (sem clickbait) a 1.0 (puro clickbait)
- Responda SOMENTE o JSON."""

# ── Prompt de análise completa (título + conteúdo) ────────────────────────────
ANALYSIS_PROMPT = """Você é um analista de mídia experiente e imparcial. Analise a notícia abaixo e responda APENAS com JSON válido.

Título: {title}
Conteúdo: {content}

JSON exato (sem markdown):
{{
  "summary": "Resumo em 1 a 2 parágrafos curtos destacando argumentos principais",
  "categories": ["tema principal", "subtema", "alinhamento político (se houver)"],
  "keywords": ["palavra1", "palavra2", "palavra3"],
  "emotional_tone": "neutro|positivo|negativo|alarmista|esperancoso|indignado|celebrativo",
  "clickbait_score": 0.0,
  "economic_axis": 0.0,
  "authority_axis": 0.0,
  "implications": "Implicação principal em 1 frase curta",
  "5ws": {{
    "who": "quem", "what": "o que", "when": "quando", "where": "onde", "why": "por que"
  }}
}}

Regras:
- categories: 2 a 5 temas incluindo alinhamento político/ideológico se relevante
- clickbait_score: 0.0 a 1.0
- economic_axis: -1.0 (esquerda) a +1.0 (direita), 0.0 = neutro
- authority_axis: -1.0 (libertário) a +1.0 (autoritário), 0.0 = neutro
- Responda SOMENTE o JSON."""


# ── Worker de pré-análise (leve, só título) ───────────────────────────────────

class PreAnalysisWorker(QThread):
    """
    Processa uma fila de artigos fazendo apenas pré-análise rápida (só título).
    Emite article_pre_analyzed(id, resultado) para cada artigo.
    """
    article_pre_analyzed = pyqtSignal(int, dict)
    progress             = pyqtSignal(int, int)
    finished_batch       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue      = deque()
        self._mutex      = QMutex()
        self._running    = True
        self._processing = False
        self._skip_ids   = set()   # IDs em análise completa — pular aqui

    def enqueue(self, articles: list):
        """Adiciona artigos que ainda não têm pré-análise."""
        with QMutexLocker(self._mutex):
            existing = {a.get("id") for a in self._queue}
            for a in articles:
                aid = a.get("id")
                # Só enfileira se não tem keywords ainda
                if aid not in existing and not a.get("ai_keywords"):
                    self._queue.append(a)
                    existing.add(aid)
        if not self._processing:
            self.start()

    def skip(self, article_id: int):
        """Marca um ID para ser pulado (quando análise completa assumir)."""
        with QMutexLocker(self._mutex):
            self._skip_ids.add(article_id)

    def unskip(self, article_id: int):
        with QMutexLocker(self._mutex):
            self._skip_ids.discard(article_id)

    def stop(self):
        self._running = False
        self.quit()

    def run(self):
        from core.ai import is_ollama_available, _ollama_generate
        from core.database import update_article_analysis

        self._processing = True
        done = 0

        while self._running:
            with QMutexLocker(self._mutex):
                # Pula IDs em análise completa
                article = None
                skipped = deque()
                while self._queue:
                    candidate = self._queue.popleft()
                    if candidate.get("id") in self._skip_ids:
                        skipped.append(candidate)
                    else:
                        article = candidate
                        break
                self._queue.extendleft(reversed(skipped))

            if article is None:
                break

            total = done + len(self._queue) + 1
            self.progress.emit(done, total)

            if not is_ollama_available():
                time.sleep(15)
                with QMutexLocker(self._mutex):
                    self._queue.appendleft(article)
                continue

            art_id = article.get("id")
            title  = article.get("title", "")
            if not title:
                done += 1
                continue

            prompt = PRE_ANALYSIS_PROMPT.format(title=title)
            try:
                raw = _ollama_generate(prompt, max_tokens=200, timeout=30)
                result = _parse_pre_analysis(raw)
                if result:
                    update_article_analysis(art_id, **result)
                    self.article_pre_analyzed.emit(art_id, result)
                    logger.debug(f"[pre] Artigo {art_id} pré-analisado")
            except Exception as e:
                logger.error(f"[pre] Erro artigo {art_id}: {e}")

            done += 1
            time.sleep(0.1)   # pré-análise é leve, quase sem pausa

        self._processing = False
        self.finished_batch.emit()


# ── Worker de análise completa de UM artigo (prioridade máxima) ───────────────

class _SingleArticleWorker(QThread):
    """Thread dedicado para análise completa de UM artigo específico."""
    done   = pyqtSignal(int, dict)
    failed = pyqtSignal(int)

    def __init__(self, article: dict, parent=None):
        super().__init__(parent)
        self._article = article

    def run(self):
        from core.ai import _ollama_generate
        from core.database import update_article_analysis
        from core.fetcher import chunk_article_text

        art_id       = self._article.get("id")
        title        = self._article.get("title", "")
        content_full = self._article.get("content_clean") or self._article.get("summary", "")

        if not title:
            self.failed.emit(art_id)
            return

        # Se não tem conteúdo, usa só o título (melhor que falhar)
        if not content_full:
            content_full = title

        chunks = chunk_article_text(content_full, chunk_size=15000)
        all_results = []
        for i, chunk in enumerate(chunks):
            prompt = ANALYSIS_PROMPT.format(title=title, content=chunk)
            try:
                raw = _ollama_generate(prompt, max_tokens=600, timeout=90)
                res = _parse_analysis(raw)
                if res:
                    all_results.append(res)
            except Exception as e:
                logger.error(f"[priority] Erro parte {i+1} artigo {art_id}: {e}")
            time.sleep(0.2)

        if all_results:
            final = _merge_chunks(all_results)
            update_article_analysis(art_id, **final)
            self.done.emit(art_id, final)
            logger.info(f"[priority] Artigo {art_id} análise completa OK")
        else:
            self.failed.emit(art_id)


# ── Worker de análise completa em batch (background) ─────────────────────────

class AnalysisWorker(QThread):
    """
    Gerencia dois níveis de análise:
      - Pré-análise rápida via PreAnalysisWorker (todos os artigos novos)
      - Análise completa via _SingleArticleWorker (artigo aberto) ou batch interno
    """
    article_analyzed     = pyqtSignal(int, dict)   # análise completa
    article_pre_analyzed = pyqtSignal(int, dict)   # pré-análise
    progress             = pyqtSignal(int, int)
    finished_batch       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue      = deque()
        self._mutex      = QMutex()
        self._running    = True
        self._processing = False
        self._priority_ids: set = set()
        self._priority_worker   = None

        # Worker de pré-análise separado
        self._pre_worker = PreAnalysisWorker(parent=parent)
        self._pre_worker.article_pre_analyzed.connect(self._on_pre_done)

    # ── API pública ───────────────────────────────────────────────────────────

    def prioritize_article(self, article_id: int):
        """Análise completa imediata do artigo aberto no leitor."""
        # Já está rodando para ESTE artigo — não duplica
        if self._priority_worker and self._priority_worker.isRunning():
            if getattr(self._priority_worker, "_article", {}).get("id") == article_id:
                logger.debug(f"[priority] artigo {article_id} já em análise prioritária")
                return
            # Worker rodando para OUTRO artigo — deixa terminar, dispara novo em paralelo
            logger.info(f"[priority] Novo artigo {article_id} sobrepõe worker anterior")

        from core.database import get_article
        art = get_article(article_id)
        if not art:
            logger.warning(f"[priority] artigo {article_id} não encontrado no banco")
            return

        # Garante conteúdo mínimo
        if not art.get("content_clean") and not art.get("summary") and not art.get("title"):
            logger.warning(f"[priority] artigo {article_id} sem conteúdo para analisar")
            return

        logger.info(f"[priority] Iniciando análise completa do artigo {article_id}: {art.get('title','')[:60]}")

        with QMutexLocker(self._mutex):
            self._priority_ids.add(article_id)

        self._pre_worker.skip(article_id)

        worker = _SingleArticleWorker(art, parent=self.parent())
        worker.done.connect(self._on_priority_done)
        worker.failed.connect(self._on_priority_failed)
        self._priority_worker = worker
        worker.start()

    def enqueue(self, articles: list):
        """
        Enfileira artigos para:
          - pré-análise imediata (todos sem ai_keywords)
          - análise completa em background (todos sem ai_summary)
        """
        # Pré-análise: todos os sem keywords
        needs_pre = [a for a in articles if not a.get("ai_keywords")]
        if needs_pre:
            self._pre_worker.enqueue(needs_pre)

        # Análise completa batch: só os que já têm pré-análise mas não têm summary
        needs_full = [a for a in articles
                      if a.get("ai_keywords") and not a.get("ai_summary")]
        with QMutexLocker(self._mutex):
            existing = {a.get("id") for a in self._queue} | self._priority_ids
            for a in needs_full:
                if a.get("id") not in existing:
                    self._queue.append(a)
                    existing.add(a.get("id"))

        if needs_full and not self._processing:
            self.start()

    def enqueue_for_full_analysis(self, articles: list):
        """Enfileira artigos para análise completa (chamado após pré-análise)."""
        with QMutexLocker(self._mutex):
            existing = {a.get("id") for a in self._queue} | self._priority_ids
            for a in articles:
                if a.get("id") not in existing:
                    self._queue.append(a)
                    existing.add(a.get("id"))
        if not self._processing:
            self.start()

    def stop(self):
        self._running = False
        self._pre_worker.stop()
        self.quit()
        if self._priority_worker:
            self._priority_worker.quit()

    # ── Slots internos ────────────────────────────────────────────────────────

    def _on_pre_done(self, article_id: int, result: dict):
        """Pré-análise concluída — emite sinal e enfileira para análise completa."""
        self.article_pre_analyzed.emit(article_id, result)

        # Busca o artigo para enfileirar na análise completa
        from core.database import get_article
        art = get_article(article_id)
        if art and not art.get("ai_summary"):
            self.enqueue_for_full_analysis([art])

    def _on_priority_done(self, article_id: int, result: dict):
        with QMutexLocker(self._mutex):
            self._priority_ids.discard(article_id)
            self._queue = deque(a for a in self._queue if a.get("id") != article_id)
        self._pre_worker.unskip(article_id)
        self.article_analyzed.emit(article_id, result)

    def _on_priority_failed(self, article_id: int):
        with QMutexLocker(self._mutex):
            self._priority_ids.discard(article_id)
        self._pre_worker.unskip(article_id)
        logger.warning(f"[priority] Falha análise completa artigo {article_id}")

    # ── Batch de análise completa ─────────────────────────────────────────────

    def run(self):
        from core.ai import is_ollama_available, _ollama_generate
        from core.database import update_article_analysis
        from core.fetcher import chunk_article_text

        self._processing = True
        done = 0

        while self._running:
            with QMutexLocker(self._mutex):
                article = None
                skipped = deque()
                while self._queue:
                    candidate = self._queue.popleft()
                    if candidate.get("id") in self._priority_ids:
                        skipped.append(candidate)
                    else:
                        article = candidate
                        break
                self._queue.extendleft(reversed(skipped))

            if article is None:
                break

            total = done + len(self._queue) + 1
            self.progress.emit(done, total)

            if not is_ollama_available():
                logger.warning("IA indisponível — pausando batch completo")
                time.sleep(30)
                with QMutexLocker(self._mutex):
                    self._queue.appendleft(article)
                continue

            art_id       = article.get("id")
            title        = article.get("title", "")
            content_full = article.get("content_clean") or article.get("summary", "")

            if not title:
                done += 1
                continue

            if not content_full:
                content_full = title

            chunks = chunk_article_text(content_full, chunk_size=15000)
            all_results = []
            for i, chunk in enumerate(chunks):
                with QMutexLocker(self._mutex):
                    if art_id in self._priority_ids:
                        logger.info(f"[batch] Artigo {art_id} virou prioritário — abortando")
                        break
                prompt = ANALYSIS_PROMPT.format(title=title, content=chunk)
                try:
                    raw = _ollama_generate(prompt, max_tokens=600, timeout=90)
                    res = _parse_analysis(raw)
                    if res:
                        all_results.append(res)
                except Exception as e:
                    logger.error(f"[batch] Erro parte {i+1} artigo {art_id}: {e}")
                time.sleep(0.3)

            if all_results:
                final = _merge_chunks(all_results)
                update_article_analysis(art_id, **final)
                self.article_analyzed.emit(art_id, final)
                logger.info(f"[batch] Artigo {art_id} análise completa OK")

            done += 1

        self._processing = False
        self.finished_batch.emit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_pre_analysis(raw: str) -> dict:
    """Extrai resultado de pré-análise (só keywords/categoria/tom/clickbait)."""
    if not raw:
        return {}
    raw = re.sub(r"`{3}(?:json)?", "", raw.strip()).strip().rstrip("`")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    try:
        data = json.loads(raw[start:end])
    except Exception:
        try:
            cleaned = re.sub(r",\s*}", "}", re.sub(r",\s*]", "]", raw[start:end]))
            data = json.loads(cleaned)
        except Exception:
            return {}

    result = {}
    if isinstance(data.get("keywords"), list):
        result["ai_keywords"] = ", ".join(str(k) for k in data["keywords"][:6])
    if isinstance(data.get("categories"), list):
        result["ai_category"] = ", ".join(str(c).strip() for c in data["categories"][:5])
    elif isinstance(data.get("category"), str):
        result["ai_category"] = data["category"]
    if isinstance(data.get("emotional_tone"), str):
        result["emotional_tone"] = data["emotional_tone"]
    if isinstance(data.get("clickbait_score"), (int, float)):
        result["clickbait_score"] = max(0.0, min(1.0, float(data["clickbait_score"])))
    return result


def _parse_analysis(raw: str) -> dict:
    """Extrai resultado de análise completa."""
    if not raw:
        return {}
    raw = re.sub(r"`{3}(?:json)?", "", raw.strip()).strip().rstrip("`")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    try:
        data = json.loads(raw[start:end])
    except json.JSONDecodeError:
        try:
            cleaned = re.sub(r",\s*}", "}", re.sub(r",\s*]", "]", raw[start:end]))
            data = json.loads(cleaned)
        except Exception:
            return {}

    result = {}
    if isinstance(data.get("summary"), str):
        result["ai_summary"] = data["summary"][:500]
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


def _merge_chunks(results: list) -> dict:
    if len(results) == 1:
        return results[0]
    final = {}
    summaries = [r.get("ai_summary", "") for r in results if r.get("ai_summary")]
    final["ai_summary"] = "\n\n".join(summaries)[:3000]
    all_tags = []
    for r in results:
        cat_str = r.get("ai_category", "")
        if cat_str:
            all_tags.extend([t.strip() for t in cat_str.split(",")])
    final["ai_category"] = ", ".join(list(dict.fromkeys(all_tags))[:8])
    for key in ["clickbait_score", "economic_axis", "authority_axis"]:
        vals = [r.get(key, 0.0) for r in results if isinstance(r.get(key), (int, float))]
        if vals:
            final[key] = sum(vals) / len(vals)
    tones = [r.get("emotional_tone") for r in results if r.get("emotional_tone")]
    if tones:
        final["emotional_tone"] = max(set(tones), key=tones.count)
    kws = []
    for r in results:
        if r.get("ai_keywords"):
            kws.extend(r["ai_keywords"].split(", "))
    final["ai_keywords"] = ", ".join(list(dict.fromkeys(kws))[:8])
    final["ai_5ws"]          = results[0].get("ai_5ws", "{}")
    final["ai_implications"] = results[-1].get("ai_implications", "")
    return final
