"""
Cronos - FeedView v1.2
Grid responsivo com FlowLayout, carrossel trending no topo.
Caracteres especiais: html.unescape em todos os pontos.
"""
import html, re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QLineEdit, QComboBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from .widgets.flow_layout import FlowLayout
from .widgets.article_card import ArticleCard, clean
from .widgets.carousel import TrendingCarousel


class FeedView(QWidget):
    article_selected = pyqtSignal(dict)
    source_feed_requested = pyqtSignal(int, str)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._source_filter = None
        self._show_favorites = False
        self._offset = 0
        self._page_size = 40
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barra de filtros ──
        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        fb = QHBoxLayout(filter_bar)
        fb.setContentsMargins(12, 8, 12, 8)
        fb.setSpacing(8)

        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText("🔍  Buscar notícias…")
        self.search.returnPressed.connect(self._reset)
        fb.addWidget(self.search, 2)

        self.cat_combo = QComboBox()
        self.cat_combo.addItem("Todas", "")
        for c in ["brasil","internacional","tecnologia","ciencia","economia","america-latina","política","saúde","esportes"]:
            self.cat_combo.addItem(c.title(), c)
        self.cat_combo.currentIndexChanged.connect(self._reset)
        fb.addWidget(self.cat_combo)

        self.read_combo = QComboBox()
        self.read_combo.addItems(["Todas","Não lidas","Lidas"])
        self.read_combo.currentIndexChanged.connect(self._reset)
        fb.addWidget(self.read_combo)

        self.fav_btn = QPushButton("★")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setFixedWidth(36)
        self.fav_btn.setToolTip("Favoritos")
        self.fav_btn.toggled.connect(self._toggle_fav)
        fb.addWidget(self.fav_btn)

        root.addWidget(filter_bar)

        # ── Carrossel trending ──
        self.carousel = TrendingCarousel(self.night_mode)
        self.carousel.article_opened.connect(self.article_selected.emit)
        carousel_container = QWidget()
        carousel_container.setObjectName("trendingCarousel")
        cc_layout = QVBoxLayout(carousel_container)
        cc_layout.setContentsMargins(10, 8, 10, 4)
        cc_layout.setSpacing(0)

        tr_header = QHBoxLayout()
        tr_lbl = QLabel("— Em destaque —")
        tr_lbl.setObjectName("statusLabel")
        tr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tr_header.addWidget(tr_lbl)
        cc_layout.addLayout(tr_header)
        cc_layout.addWidget(self.carousel)
        root.addWidget(carousel_container)

        # ── Scroll com grid de cards ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setObjectName("feedScroll")

        self.feed_container = QWidget()
        self.feed_container.setObjectName("feedContainer")
        self.flow = FlowLayout(self.feed_container, h_spacing=10, v_spacing=10)
        self.flow.setContentsMargins(12, 10, 12, 10)
        self.scroll.setWidget(self.feed_container)
        root.addWidget(self.scroll, 1)

        # ── Paginação ──
        nav = QHBoxLayout()
        nav.setContentsMargins(12, 6, 12, 8)
        self.prev_btn = QPushButton("◀  Anterior")
        self.prev_btn.clicked.connect(self._prev)
        self.next_btn = QPushButton("Próxima  ▶")
        self.next_btn.clicked.connect(self._next)
        self.page_lbl = QLabel()
        self.page_lbl.setObjectName("statusLabel")
        self.page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self.prev_btn)
        nav.addStretch()
        nav.addWidget(self.page_lbl)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        self.refresh()

    # ── Públicos ──────────────────────────────────────────────────────────────

    def refresh(self):
        self._load_articles()
        self._refresh_trending()

    def reset_to_home(self):
        self.search.clear()
        self.cat_combo.setCurrentIndex(0)
        self.read_combo.setCurrentIndex(0)
        self.fav_btn.setChecked(False)
        self._show_favorites = False
        self._source_filter = None
        self._offset = 0
        self.refresh()

    def set_source_filter(self, source_id, source_name=""):
        self._source_filter = source_id
        self._offset = 0
        self._load_articles()

    def mark_new(self):
        self._offset = 0
        self._load_articles()
        self._refresh_trending()

    # ── Privados ─────────────────────────────────────────────────────────────

    def _reset(self):
        self._offset = 0
        self._load_articles()

    def _load_articles(self):
        from core.database import get_articles
        self._clear_cards()

        cat  = self.cat_combo.currentData()
        ri   = self.read_combo.currentIndex()
        is_read = None if ri == 0 else (True if ri == 2 else False)
        search = self.search.text().strip() or None

        articles = get_articles(
            limit=self._page_size, offset=self._offset,
            category=cat, is_read=is_read,
            is_favorite=True if self._show_favorites else None,
            search=search, source_id=self._source_filter
        )

        if not articles:
            lbl = QLabel("Nenhuma notícia encontrada.\nAtualize os feeds ou ajuste os filtros.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setObjectName("sectionHeader")
            self.flow.addWidget(lbl)
        else:
            for i, art in enumerate(articles):
                card = ArticleCard(art, self.night_mode, index=i)
                card.clicked.connect(self.article_selected)
                card.fav_toggled.connect(self._on_fav)
                self.flow.addWidget(card)

        page = self._offset // self._page_size + 1
        self.page_lbl.setText(f"página {page}")
        self.prev_btn.setEnabled(self._offset > 0)
        self.next_btn.setEnabled(len(articles) == self._page_size)
        self.scroll.verticalScrollBar().setValue(0)
        self.feed_container.updateGeometry()

    def _refresh_trending(self):
        from core.database import get_articles
        from core.trending import detect_trending
        # Pega artigos das últimas 6h para detectar trending
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(hours=6)).isoformat()
        recent = get_articles(limit=200, date_from=since)
        clusters = detect_trending(recent, threshold=0.22, min_sources=2)
        self.carousel.set_data(clusters)

    def _clear_cards(self):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _on_fav(self, aid):
        from core.database import toggle_favorite
        toggle_favorite(aid)
        self._load_articles()

    def _toggle_fav(self, checked):
        self._show_favorites = checked
        self._reset()

    def _prev(self):
        if self._offset >= self._page_size:
            self._offset -= self._page_size
            self._load_articles()

    def _next(self):
        self._offset += self._page_size
        self._load_articles()
