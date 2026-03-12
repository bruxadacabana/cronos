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

# Helpers de log estruturado (importados lazy para evitar ciclo)
def _log_start(art_id, title, mode):
    try:
        from core.log_setup import log_analysis_start
        log_analysis_start(art_id, title, mode)
    except Exception:
        logger.info(f"[{mode}] Iniciando análise artigo {art_id}: {title[:60]}")

def _log_result(art_id, result, elapsed, mode):
    try:
        from core.log_setup import log_analysis_result
        log_analysis_result(art_id, result, elapsed, mode)
    except Exception:
        logger.info(f"[{mode}] Concluído artigo {art_id} em {elapsed:.1f}s")

def _log_error(art_id, title, error, chunk=None, mode="batch"):
    try:
        from core.log_setup import log_analysis_error
        log_analysis_error(art_id, title, error, chunk, mode)
    except Exception:
        logger.error(f"[{mode}] Erro artigo {art_id}: {error}", exc_info=True)

# ── Prompt de pré-análise (só título, resposta pequena) ───────────────────────
PRE_ANALYSIS_SYSTEM = (
    "You are a JSON API. You ONLY output raw valid JSON, nothing else. "
    "No explanations, no thinking, no markdown, no code blocks. "
    "First character of your response must be '{'."
)

PRE_ANALYSIS_PROMPT = """Analyze this news headline and return ONLY valid JSON.

Headline: {title}

Return EXACTLY this JSON structure (filled in):
{{
  "keywords": ["term1", "term2", "term3"],
  "categories": ["main theme", "subtheme"],
  "emotional_tone": "neutro|positivo|negativo|alarmista|esperancoso|indignado|celebrativo",
  "clickbait_score": 0.0
}}

Rules:
- keywords: 3 to 6 key terms from the headline
- categories: 2 to 4 thematic categories  
- clickbait_score: 0.0 (no clickbait) to 1.0 (pure clickbait)
- Output ONLY the JSON object, nothing before or after."""

# ── Prompt de análise completa (título + conteúdo) ────────────────────────────
ANALYSIS_SYSTEM = (
    "You are a JSON API and media analyst. You ONLY output raw valid JSON, nothing else. "
    "No explanations, no thinking, no markdown, no code blocks. "
    "First character of your response must be '{'."
)

ANALYSIS_PROMPT = """Analyze this news article and return ONLY valid JSON.

Title: {title}
Content: {content}

Return EXACTLY this JSON structure (filled in):
{{
  "summary": "Summary in 1-2 short paragraphs in Portuguese",
  "categories": ["main theme", "subtheme"],
  "keywords": ["term1", "term2", "term3"],
  "emotional_tone": "neutro|positivo|negativo|alarmista|esperancoso|indignado|celebrativo",
  "clickbait_score": 0.0,
  "economic_axis": 0.0,
  "authority_axis": 0.0,
  "implications": "Main implication in 1 sentence in Portuguese",
  "5ws": {{
    "who": "who", "what": "what", "when": "when", "where": "where", "why": "why"
  }}
}}

Rules:
- Output ONLY the JSON object, nothing before or after
- summary and implications: write in Portuguese
- economic_axis: -1.0 (left) to +1.0 (right)
- authority_axis: -1.0 (libertarian) to +1.0 (authoritarian)
- clickbait_score: 0.0 to 1.0"""


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

            _log_start(art_id, title, "pre")
            prompt = PRE_ANALYSIS_PROMPT.format(title=title)
            _t0 = time.monotonic()
            _retry_count = getattr(article, "_retry", 0) if hasattr(article, "_retry") else article.get("_pre_retry", 0)
            try:
                raw = _ollama_generate(prompt, max_tokens=600, timeout=45, system=PRE_ANALYSIS_SYSTEM)
                result = _parse_pre_analysis(raw)
                elapsed = time.monotonic() - _t0
                if result:
                    update_article_analysis(art_id, **result)
                    self.article_pre_analyzed.emit(art_id, result)
                    _log_result(art_id, result, elapsed, "pre")
                    done += 1
                else:
                    # JSON inválido — descarta (modelo respondeu mas mal formado)
                    logger.warning(
                        f"[PRE] ✗ JSON inválido/vazio para artigo {art_id}\n"
                        f"  Título  : {title[:80]}\n"
                        f"  Resposta: {(raw or '')[:400]}"
                    )
                    done += 1
            except Exception as e:
                elapsed = time.monotonic() - _t0
                _log_error(art_id, title, e, mode="pre")
                # Timeout/erro de rede — re-enfileira com limite de 2 tentativas
                if _retry_count < 2:
                    article["_pre_retry"] = _retry_count + 1
                    backoff = 5 * (2 ** _retry_count)   # 5s, 10s
                    logger.info(
                        f"[PRE] Re-enfileirando artigo {art_id} "
                        f"(tentativa {_retry_count + 1}/2, aguardando {backoff}s)"
                    )
                    time.sleep(backoff)
                    with QMutexLocker(self._mutex):
                        self._queue.append(article)
                    # Não incrementa done — artigo ainda não foi processado
                else:
                    logger.warning(
                        f"[PRE] Artigo {art_id} descartado após 2 tentativas com falha"
                    )
                    done += 1

            time.sleep(0.1)

        self._processing = False
        self.finished_batch.emit()


# ── Worker de análise completa de UM artigo (prioridade máxima) ───────────────

class _SingleArticleWorker(QThread):
    """Thread dedicado para análise completa de UM artigo específico."""
    done          = pyqtSignal(int, dict)
    failed        = pyqtSignal(int)
    progress_tick = pyqtSignal(int, int, int, int)  # (elapsed_ms, timeout_ms, chunk_i, total_chunks)

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

        content_full = content_full[:5000]
        _log_start(art_id, title, "priority")
        _t0_total = time.monotonic()
        chunks = chunk_article_text(content_full, chunk_size=4500)
        import threading
        PRIORITY_TIMEOUT_MS = 60_000
        total_chunks = len(chunks)
        all_results = []
        for i, chunk in enumerate(chunks):
            self.progress_tick.emit(0, PRIORITY_TIMEOUT_MS, i, total_chunks)
            prompt = ANALYSIS_PROMPT.format(title=title, content=chunk)
            _t0 = time.monotonic()
            _stop_tick = [False]
            def _ticker(w=self, t0=_t0, tms=PRIORITY_TIMEOUT_MS, ci=i, tc=total_chunks, flag=_stop_tick):
                while not flag[0]:
                    e_ms = int((time.monotonic() - t0) * 1000)
                    w.progress_tick.emit(min(e_ms, tms - 10), tms, ci, tc)
                    time.sleep(0.4)
            _tick_t = threading.Thread(target=_ticker, daemon=True)
            _tick_t.start()
            try:
                raw = _ollama_generate(prompt, max_tokens=1200, timeout=90, system=ANALYSIS_SYSTEM)
                _stop_tick[0] = True
                elapsed_chunk = time.monotonic() - _t0
                res = _parse_analysis(raw)
                if res:
                    all_results.append(res)
                    logger.debug(
                        f"[PRIORITY] chunk {i+1}/{len(chunks)} OK "
                        f"({elapsed_chunk:.1f}s) artigo {art_id}"
                    )
                else:
                    logger.warning(
                        f"[PRIORITY] ✗ JSON inválido chunk {i+1} artigo {art_id}\n"
                        f"  Resposta: {(raw or '')[:400]}"
                    )
            except Exception as e:
                _stop_tick[0] = True
                _log_error(art_id, title, e, chunk=i+1, mode="priority")
            time.sleep(0.2)

        elapsed_total = time.monotonic() - _t0_total
        if all_results:
            final = _merge_chunks(all_results)
            update_article_analysis(art_id, **final)
            self.done.emit(art_id, final)
            _log_result(art_id, final, elapsed_total, "priority")
        else:
            logger.error(
                f"[PRIORITY] ✗ Análise completa falhou — nenhum chunk válido\n"
                f"  ID    : {art_id}\n"
                f"  Título: {title[:80]}\n"
                f"  Chunks: {len(chunks)}  Tempo: {elapsed_total:.1f}s"
            )
            self.failed.emit(art_id)


# ── Worker de análise completa em batch (background) ─────────────────────────

class AnalysisWorker(QThread):
    """
    Gerencia dois níveis de análise:
      - Pré-análise rápida via PreAnalysisWorker (todos os artigos novos)
      - Análise completa via _SingleArticleWorker (artigo aberto) ou batch interno
    """
    article_analyzed        = pyqtSignal(int, dict)
    article_pre_analyzed    = pyqtSignal(int, dict)
    article_analysis_failed = pyqtSignal(int)
    priority_progress       = pyqtSignal(int, int)   # (elapsed_ms, timeout_ms)
    progress                = pyqtSignal(int, int)
    finished_batch          = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue      = deque()
        self._mutex      = QMutex()
        self._running    = True
        self._processing = False
        self._priority_ids: set = set()
        self._priority_worker   = None

        # Contadores globais para progresso combinado (pré + completa)
        self._total_enqueued = 0   # total acumulado desde último reset
        self._total_done     = 0   # concluídos (pré + completa)

        # Worker de pré-análise separado
        self._pre_worker = PreAnalysisWorker(parent=parent)
        self._pre_worker.article_pre_analyzed.connect(self._on_pre_done)
        self._pre_worker.progress.connect(self._on_pre_progress)
        self._pre_worker.finished_batch.connect(self._on_pre_finished)

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
        worker.progress_tick.connect(self._on_priority_tick)
        self._priority_worker = worker
        worker.start()

    def enqueue(self, articles: list):
        """
        Enfileira artigos para:
          - pré-análise imediata (todos sem ai_keywords)
          - análise completa em background (todos sem ai_summary)
        """
        needs_pre = [a for a in articles if not a.get("ai_keywords")]
        if needs_pre:
            self._pre_worker.enqueue(needs_pre)
            with QMutexLocker(self._mutex):
                self._total_enqueued += len(needs_pre)

        needs_full = [a for a in articles
                      if a.get("ai_keywords") and not a.get("ai_summary")]
        with QMutexLocker(self._mutex):
            existing = {a.get("id") for a in self._queue} | self._priority_ids
            added = 0
            for a in needs_full:
                if a.get("id") not in existing:
                    self._queue.append(a)
                    existing.add(a.get("id"))
                    added += 1
            self._total_enqueued += added

        self._emit_combined_progress()

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
        with QMutexLocker(self._mutex):
            self._total_done += 1
        self._emit_combined_progress()
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

    def _on_priority_tick(self, elapsed_ms, timeout_ms, chunk_i, total_chunks):
        self.priority_progress.emit(elapsed_ms, timeout_ms)

    def _on_priority_failed(self, article_id: int):
        with QMutexLocker(self._mutex):
            self._priority_ids.discard(article_id)
        self._pre_worker.unskip(article_id)
        logger.warning(f"[priority] Falha análise completa artigo {article_id}")
        self.article_analysis_failed.emit(article_id)

    # ── Progresso combinado ──────────────────────────────────────────────────

    def _emit_combined_progress(self):
        with QMutexLocker(self._mutex):
            done  = self._total_done
            total = self._total_enqueued
        if total > 0:
            self.progress.emit(done, total)

    def _on_pre_progress(self, pre_done: int, pre_total: int):
        """Repassa progresso da pré-análise."""
        self._emit_combined_progress()

    def _on_pre_finished(self):
        """Pré-análise terminou. Só emite finished_batch se a fila de análise
        completa também estiver vazia E não houver processamento em curso."""
        with QMutexLocker(self._mutex):
            pre_done  = len(self._queue) == 0
            full_done = not self._processing
        if pre_done and full_done:
            logger.info("[AnalysisWorker] Pré-análise e batch concluídos — emitindo finished_batch")
            with QMutexLocker(self._mutex):
                self._total_enqueued = 0
                self._total_done = 0
            self.finished_batch.emit()
        else:
            remaining = len(self._queue)
            logger.debug(
                f"[AnalysisWorker] Pré-análise concluída; "
                f"batch ainda em curso ({remaining} na fila, processing={self._processing})"
            )

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

            content_full = content_full[:5000]
            _log_start(art_id, title, "batch")
            _t0_total = time.monotonic()
            chunks = chunk_article_text(content_full, chunk_size=4500)
            all_results = []
            for i, chunk in enumerate(chunks):
                with QMutexLocker(self._mutex):
                    if art_id in self._priority_ids:
                        logger.info(
                            f"[BATCH] Artigo {art_id} promovido a prioritário — abortando batch"
                        )
                        break
                prompt = ANALYSIS_PROMPT.format(title=title, content=chunk)
                _t0 = time.monotonic()
                try:
                    raw = _ollama_generate(prompt, max_tokens=1200, timeout=90, system=ANALYSIS_SYSTEM)
                    elapsed_chunk = time.monotonic() - _t0
                    res = _parse_analysis(raw)
                    if res:
                        all_results.append(res)
                        logger.debug(
                            f"[BATCH] chunk {i+1}/{len(chunks)} OK "
                            f"({elapsed_chunk:.1f}s) artigo {art_id}"
                        )
                    else:
                        logger.warning(
                            f"[BATCH] ✗ JSON inválido chunk {i+1} artigo {art_id}\n"
                            f"  Resposta: {(raw or '')[:400]}"
                        )
                except Exception as e:
                    _log_error(art_id, title, e, chunk=i+1, mode="batch")
                time.sleep(0.1)

            elapsed_total = time.monotonic() - _t0_total
            if all_results:
                final = _merge_chunks(all_results)
                update_article_analysis(art_id, **final)
                self.article_analyzed.emit(art_id, final)
                _log_result(art_id, final, elapsed_total, "batch")
                with QMutexLocker(self._mutex):
                    self._total_done += 1
                self._emit_combined_progress()

            done += 1

        self._processing = False
        # Só finaliza se pré-análise também já terminou
        pre_still_running = self._pre_worker.isRunning()
        if not pre_still_running:
            logger.info("[AnalysisWorker] Batch completo concluído — emitindo finished_batch")
            with QMutexLocker(self._mutex):
                self._total_enqueued = 0
                self._total_done = 0
            self.finished_batch.emit()
        else:
            logger.debug(
                "[AnalysisWorker] Batch completo concluído; "
                "aguardando pré-análise terminar para emitir finished_batch"
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_thinking(raw: str) -> str:
    """Remove blocos <think>...</think> que modelos reasoning inserem antes do JSON."""
    # Remove bloco thinking completo
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove tag incompleta (thinking cortado pelo max_tokens)
    raw = re.sub(r"<think>.*$", "", raw, flags=re.DOTALL | re.IGNORECASE)
    return raw.strip()


def _parse_pre_analysis(raw: str) -> dict:
    """Extrai resultado de pré-análise (só keywords/categoria/tom/clickbait)."""
    if not raw:
        return {}
    raw = _strip_thinking(raw)
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
    raw = _strip_thinking(raw)
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
