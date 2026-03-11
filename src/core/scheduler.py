"""
Cronos - Módulo Scheduler
Gerencia atualização automática de feeds em background usando QThread.
"""

import logging
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject
from .database import get_setting
from .fetcher import fetch_all_sources

logger = logging.getLogger("cronos.scheduler")


class FetchWorker(QThread):
    """Thread de busca de feeds."""
    progress = pyqtSignal(int, int, str)   # atual, total, nome_fonte
    finished = pyqtSignal(int)              # total de artigos novos
    error = pyqtSignal(str)

    def run(self):
        try:
            def progress_cb(current, total, name):
                self.progress.emit(current, total, name)

            total = fetch_all_sources(progress_callback=progress_cb)
            self.finished.emit(total)
        except Exception as e:
            logger.error(f"Erro no FetchWorker: {e}")
            self.error.emit(str(e))


class AnalysisWorker(QThread):
    """Thread de análise de artigos com Ollama."""
    progress = pyqtSignal(int, int)   # atual, total
    finished = pyqtSignal()
    article_done = pyqtSignal(int)    # article_id analisado

    def __init__(self, article_ids: list, parent=None):
        super().__init__(parent)
        self.article_ids = article_ids

    def run(self):
        from .ai import full_analysis, is_ollama_available
        from .database import get_article

        if not is_ollama_available():
            logger.warning("Ollama não disponível para análise")
            self.finished.emit()
            return

        total = len(self.article_ids)
        for i, article_id in enumerate(self.article_ids):
            try:
                article = get_article(article_id)
                if article and not article.get("analysis_done"):
                    content = article.get("content_clean") or article.get("summary") or ""
                    full_analysis(
                        article_id,
                        article["title"],
                        content,
                        article.get("language", "pt")
                    )
                    self.article_done.emit(article_id)
            except Exception as e:
                logger.error(f"Erro ao analisar artigo {article_id}: {e}")
            self.progress.emit(i + 1, total)

        self.finished.emit()


class Scheduler(QObject):
    """
    Gerencia o timer de atualização automática.
    Emite sinal quando há novos artigos.
    """
    new_articles = pyqtSignal(int)
    fetch_started = pyqtSignal()
    fetch_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._do_fetch)
        self.worker = None
        self._running = False

    def start(self):
        """Inicia o scheduler com o intervalo configurado."""
        interval_min = int(get_setting("fetch_interval", "30"))
        interval_ms = interval_min * 60 * 1000
        self.timer.start(interval_ms)
        logger.info(f"Scheduler iniciado: intervalo de {interval_min} minutos")

        # Busca imediata na inicialização se configurado
        if get_setting("fetch_on_startup", "1") == "1":
            self._do_fetch()

    def stop(self):
        self.timer.stop()
        logger.info("Scheduler parado")

    def update_interval(self, minutes: int):
        """Atualiza o intervalo sem reiniciar o scheduler."""
        self.timer.setInterval(minutes * 60 * 1000)
        logger.info(f"Intervalo atualizado: {minutes} minutos")

    def fetch_now(self):
        """Dispara uma busca imediata."""
        self._do_fetch()

    def _do_fetch(self):
        if self._running:
            logger.info("Fetch já em andamento, pulando")
            return

        self._running = True
        self.fetch_started.emit()
        self.worker = FetchWorker()
        self.worker.finished.connect(self._on_fetch_done)
        self.worker.error.connect(self._on_fetch_error)
        self.worker.start()

    def _on_fetch_done(self, total: int):
        self._running = False
        logger.info(f"Fetch concluído: {total} artigos novos")
        if total > 0:
            self.new_articles.emit(total)

    def _on_fetch_error(self, error: str):
        self._running = False
        logger.error(f"Erro no fetch: {error}")
        self.fetch_error.emit(error)
