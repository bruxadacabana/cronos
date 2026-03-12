"""
Cronos - MainWindow v1.2
Sidebar fichário animada + stack de views.
"""
import sys
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QStatusBar, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from core.database import init_db, get_setting, set_setting
from .widgets.sidebar import Sidebar


def _load_fonts():
    fonts_dir = BASE_DIR / "src" / "assets" / "fonts"
    ids = []
    for f in fonts_dir.glob("*.ttf"):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            fams = QFontDatabase.applicationFontFamilies(fid)
            ids.append((fid, fams))
    return ids


def load_stylesheet(theme: str) -> str:
    path = BASE_DIR / "src" / "ui" / "themes" / f"{theme}.qss"
    return path.read_text(encoding="utf-8") if path.exists() else ""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        _load_fonts()
        self.night_mode = get_setting("theme","day") == "night"
        self._current_section = "feed"
        self._build_ui()
        self._setup_scheduler()
        self._setup_analysis_queue()
        self._setup_notifier()
        self._apply_theme()
        self._setup_auto_theme()
        self.setWindowTitle("Cronos — Leitor de Notícias")
        self.resize(1360, 860)
        # Startup: análise dos artigos não analisados
        if get_setting("analyze_on_startup","1") == "1":
            QTimer.singleShot(4000, self._startup_analysis)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar fichário ──
        self.sidebar = Sidebar(self.night_mode)
        self.sidebar.navigate.connect(self._navigate)
        self.sidebar.get_refresh_btn().clicked.connect(self._manual_fetch)
        root.addWidget(self.sidebar)


        # ── Stack principal ──
        from PyQt6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        # ReaderView como overlay sobre o STACK inteiro (funciona em qualquer aba)
        from .reader_view import ReaderView
        self.reader_view = ReaderView(self.night_mode, parent=self.stack)
        self.reader_view.back_btn.clicked.connect(self._close_reader)
        self.reader_view.retry_analysis_requested.connect(self._retry_article_analysis)

        # 0: Feed
        feed_page = QWidget()
        fp = QHBoxLayout(feed_page)
        fp.setContentsMargins(0,0,0,0)
        fp.setSpacing(0)

        from .feed_view import FeedView
        self.feed_view = FeedView(self.night_mode)
        self.feed_view.article_selected.connect(self._open_article)
        self.feed_view.source_feed_requested.connect(self._open_source_in_feed)
        self.feed_view.theme_toggle.connect(self._toggle_theme)
        fp.addWidget(self.feed_view)

        self.stack.addWidget(feed_page)          # 0

        # 1: Fontes
        from .sources_view import SourcesView
        self.sources_view = SourcesView(self.night_mode)
        self.sources_view.open_source_feed.connect(self._open_source_in_feed)
        self.sources_view.fetch_now.connect(self._manual_fetch) # <--- ADICIONAMOS ISTO AQUI
        self.stack.addWidget(self.sources_view)  # 1

        # 2: Social
        from .social_view import SocialView
        self.social_view = SocialView(self.night_mode)
        self.stack.addWidget(self.social_view)   # 2

        # 3: Dashboard
        from .dashboard_view import DashboardView
        self.dashboard_view = DashboardView(self.night_mode)
        self.dashboard_view.open_source_feed.connect(self._open_source_in_feed)
        self.stack.addWidget(self.dashboard_view) # 3

        # 4: Configurações
        from .settings_view import SettingsView
        self.settings_view = SettingsView(self.night_mode)
        self.settings_view.theme_changed.connect(self._set_theme)
        # <--- A LINHA QUE ESTAVA AQUI FOI APAGADA
        self.stack.addWidget(self.settings_view) # 4

        # NOVO - 5: Trending Expandido
        from .trending_view import TrendingView
        self.trending_view = TrendingView(self.night_mode)
        self.trending_view.article_selected.connect(self._open_article)
        self.stack.addWidget(self.trending_view) # 5

        # 6: Arquivo
        from .archive_view import ArchiveView
        self.archive_view = ArchiveView(self.night_mode)
        self.archive_view.article_selected.connect(self._open_article)
        self.stack.addWidget(self.archive_view) # 6

        # ── Status bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Cronos pronto.")

        # Label de análise em tempo real (ex: "Analisando 12 de 45 artigos")
        self._analysis_lbl = QLabel()
        self._analysis_lbl.setObjectName("statusLabel")
        self._analysis_lbl.hide()
        self.status_bar.addPermanentWidget(self._analysis_lbl)

        # Barra de progresso maior com % decimal
        self.progress = QProgressBar()
        self.progress.setMinimumWidth(260)
        self.progress.setMaximumWidth(380)
        self.progress.setMinimumHeight(18)
        self.progress.setMaximumHeight(18)
        self.progress.setFormat("%.1f%%")   # será substituído por setText manual
        self.progress.hide()
        self.status_bar.addPermanentWidget(self.progress)

        self._navigate("feed")
        # Ollama check
        self._ollama_timer = QTimer(self)
        self._ollama_timer.timeout.connect(self._check_ollama)
        self._ollama_timer.start(30000)
        self._check_ollama()

    # ── Navegação ─────────────────────────────────────────────────────────────

    def _navigate(self, key: str):
        if key == "feed" and self._current_section == "feed":
            self.feed_view.reset_to_home()
            return

        # Esconde o leitor ao trocar de aba — evita overlay fantasma
        if hasattr(self, "reader_view") and self.reader_view.isVisible():
            self.reader_view.hide()

        self._current_section = key
        self.sidebar.set_active(key)

        idx_map = {"feed":0, "favorites":0, "sources":1, "social":2, "dashboard":3, "settings":4, "trending":5, "archive":6}
        idx = idx_map.get(key, 0)
        self.stack.setCurrentIndex(idx)

        if key == "favorites":
            self.feed_view._show_favorites = True
            self.feed_view.fav_btn.setChecked(True)
            self.feed_view._reset()
        elif key == "dashboard":
            self.dashboard_view.refresh()
        elif key == "sources":
            self.sources_view.reload()
        elif key == "trending":
            self.trending_view.refresh()
        elif key == "archive":
            self.archive_view.reload()

    def _open_article(self, article: dict):
        # Overlay cobre o stack inteiro — funciona em qualquer aba
        self.reader_view.setGeometry(self.stack.rect())
        self.reader_view.raise_()
        self.reader_view.load_article(article)
        # Prioriza análise se QUALQUER campo essencial estiver faltando
        needs_analysis = (
            not article.get("ai_summary") or
            not article.get("emotional_tone") or
            article.get("clickbait_score") is None
        )
        if needs_analysis and hasattr(self, "analysis_worker"):
            self.analysis_worker.prioritize_article(article["id"])

    def _close_reader(self):
        self.reader_view.hide()

    def resizeEvent(self, event):
        """Mantém o overlay do leitor cobrindo o feed ao redimensionar."""
        super().resizeEvent(event)
        if hasattr(self, "stack") and hasattr(self, "reader_view"):
            self.reader_view.setGeometry(self.stack.rect())

    def _open_source_in_feed(self, source_id: int, source_name: str):
        self._current_section = "feed"
        self.sidebar.set_active("feed")
        self.stack.setCurrentIndex(0)
        self.feed_view.set_source_filter(source_id, source_name)
        self.status_bar.showMessage(f"Notícias de: {source_name}", 4000)

    # ── Scheduler / Análise ──────────────────────────────────────────────────

    def _setup_scheduler(self):
        from core.scheduler import Scheduler
        self.scheduler = Scheduler(self)
        self.scheduler.new_articles.connect(self._on_new_articles)
        self.scheduler.fetch_started.connect(lambda: self.status_bar.showMessage("Atualizando feeds…"))
        self.scheduler.fetch_error.connect(lambda e: self.status_bar.showMessage(f"Erro: {e}", 5000))
        self.scheduler.start()

    def _setup_analysis_queue(self):
        from core.analyzer import AnalysisWorker
        self.analysis_worker = AnalysisWorker(self)
        self.analysis_worker.article_analyzed.connect(self._on_article_analyzed)
        self.analysis_worker.article_pre_analyzed.connect(self._on_article_pre_analyzed)
        self.analysis_worker.article_analysis_failed.connect(self._on_article_analysis_failed)
        self.analysis_worker.priority_progress.connect(self._on_priority_progress)
        self.analysis_worker.progress.connect(self._on_analysis_progress)
        self.analysis_worker.finished_batch.connect(self._on_analysis_finished)

    def _startup_analysis(self):
        from core.database import get_unanalyzed_articles, mark_queued
        arts = get_unanalyzed_articles(limit=30)
        if arts:
            ids = [a["id"] for a in arts]
            mark_queued(ids)
            self.analysis_worker.enqueue(arts)
            self.status_bar.showMessage(f"Analisando {len(arts)} artigos em background…")

    def _on_new_articles(self, count: int):
        self.status_bar.showMessage(f"{count} novas notícias", 5000)
        self.feed_view.mark_new()
        # Enfileira para análise
        from core.database import get_unanalyzed_articles, mark_queued
        arts = get_unanalyzed_articles(limit=50)
        if arts:
            mark_queued([a["id"] for a in arts])
            self.analysis_worker.enqueue(arts)
        try:
            self.notifier.notify_fetch_complete(count)
        except Exception:
            pass

    def _on_article_pre_analyzed(self, article_id: int, result: dict):
        """Pré-análise concluída — sem atualização visual por enquanto (evita recarregar o feed inteiro)."""
        pass

    def _on_article_analyzed(self, article_id: int, result: dict):
        # 1. Atualiza o dashboard se estiver aberto
        if self._current_section == "dashboard":
            self.dashboard_view.refresh()

        # 2. Atualiza o painel do leitor se esse artigo está aberto agora
        if (self.reader_view.isVisible() and
                self.reader_view.current_article and
                self.reader_view.current_article.get("id") == article_id):
            from core.database import get_article
            updated = get_article(article_id)
            if updated:
                self.reader_view.current_article = updated
                self.reader_view._update_analysis(updated)

    def _on_article_analysis_failed(self, article_id: int):
        """Repassa falha ao reader_view se o artigo estiver aberto."""
        if (self.reader_view.isVisible() and
                getattr(self.reader_view, "current_article", None) and
                self.reader_view.current_article.get("id") == article_id):
            self.reader_view.notify_analysis_failed(article_id)

    def _on_priority_progress(self, elapsed_ms: int, timeout_ms: int):
        """Repassa progresso real da análise prioritária ao reader_view."""
        if self.reader_view.isVisible():
            self.reader_view.notify_analysis_progress(elapsed_ms, timeout_ms)

    def _retry_article_analysis(self, article_id: int):
        """Re-enfileira artigo para análise, limpando resultado anterior."""
        if not hasattr(self, "analysis_worker"):
            return
        from core.database import get_connection
        conn = get_connection()
        conn.execute(
            "UPDATE articles SET analysis_done=0, analysis_queued=0, "
            "ai_summary=NULL, emotional_tone=NULL, clickbait_score=NULL, "
            "ai_category=NULL, ai_keywords=NULL, ai_implications=NULL, "
            "ai_5ws=NULL, economic_axis=0.0, authority_axis=0.0 "
            "WHERE id=?", (article_id,)
        )
        conn.commit(); conn.close()
        self.analysis_worker.prioritize_article(article_id)

    def _on_analysis_finished(self):
        self.progress.hide()
        self._analysis_lbl.hide()
        self.status_bar.showMessage("Análises concluídas.", 3000)

    def _on_analysis_progress(self, done: int, total: int):
        if total > 0:
            pct = (done / total) * 100
            remaining = total - done
            self._analysis_lbl.setText(
                f"Analisando {done} de {total} artigos  ({remaining} restantes)"
            )
            self._analysis_lbl.show()
            self.progress.show()
            # Usa escala ×10 para permitir 1 casa decimal (QProgressBar só aceita int)
            self.progress.setRange(0, total * 10)
            self.progress.setValue(int(done * 10))
            self.progress.setFormat(f"{pct:.1f}%")

    def _manual_fetch(self):
        self.sidebar.get_refresh_btn().setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, 0)
        self.scheduler.fetch_now()
        QTimer.singleShot(3000, lambda: (
            self.sidebar.get_refresh_btn().setEnabled(True),
            self.progress.hide()
        ))

    # ── Notifier ──────────────────────────────────────────────────────────────

    def _setup_notifier(self):
        try:
            from core.notifier import NotificationManager
            self.notifier = NotificationManager(self)
            self.notifier.setup_tray(QApplication.instance())
            self.notifier.notification_clicked.connect(self._open_article_by_id)
        except Exception:
            pass

    def _open_article_by_id(self, article_id):
        from core.database import get_article
        art = get_article(article_id)
        if art:
            self._navigate("feed")
            self._open_article(art)

    # ── Tema ──────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        new_theme = "day" if self.night_mode else "night"
        self._set_theme(new_theme)

    def _apply_theme(self):
        theme = "night" if self.night_mode else "day"
        qss = load_stylesheet(theme)
        QApplication.instance().setStyleSheet(qss)
        try:
            from core.font_loader import apply_paper_texture
            apply_paper_texture(QApplication.instance(), theme)
        except Exception:
            pass
        # Propaga para todas as views
        if hasattr(self, "feed_view"):
            self.feed_view.set_night_mode(self.night_mode)
        if hasattr(self, "reader_view"):
            self.reader_view.set_night_mode(self.night_mode)
        if hasattr(self, "dashboard_view"):
            self.dashboard_view.set_night_mode(self.night_mode)
        if hasattr(self, "sources_view") and hasattr(self.sources_view, "set_night_mode"):
            self.sources_view.set_night_mode(self.night_mode)
        if hasattr(self, "trending_view") and hasattr(self.trending_view, "set_night_mode"):
            self.trending_view.set_night_mode(self.night_mode)
        if hasattr(self, "archive_view") and hasattr(self.archive_view, "set_night_mode"):
            self.archive_view.set_night_mode(self.night_mode)
        if hasattr(self, "social_view") and hasattr(self.social_view, "set_night_mode"):
            self.social_view.set_night_mode(self.night_mode)
        if hasattr(self, "sidebar"):
            self.sidebar.set_night_mode(self.night_mode)

    def _set_theme(self, theme: str):
        self.night_mode = (theme == "night")
        set_setting("theme", theme)
        self._apply_theme()

    def _setup_auto_theme(self):
        if get_setting("theme_auto","1") == "1":
            t = QTimer(self, timeout=self._check_auto_theme, interval=60000)
            t.start()
            self._check_auto_theme()

    def _check_auto_theme(self):
        now = datetime.now().strftime("%H:%M")
        day_s = get_setting("theme_day_start","07:00")
        night_s = get_setting("theme_night_start","19:00")
        should_night = not (day_s <= now < night_s)
        if should_night != self.night_mode:
            self._set_theme("night" if should_night else "day")

    def _check_ollama(self):
        try:
            from core.ai import is_ollama_available
            model = get_setting("ollama_model","llama3")
            ok = is_ollama_available()
            self.sidebar.set_ollama_status(ok, model)
        except Exception:
            pass
