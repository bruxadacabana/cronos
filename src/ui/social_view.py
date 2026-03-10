"""
Cronos - SocialView
Aba de redes sociais: Reddit, Bluesky, Mastodon, YouTube, Twitter/X.
"""
import html, re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QScrollArea, QFrame, QListWidget, QListWidgetItem,
    QTextBrowser, QProgressBar, QStackedWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

def _clean(t):
    if not t: return ""
    for _ in range(3):
        d = html.unescape(t)
        if d == t: break
        t = d
    return re.sub(r'<[^>]+>', ' ', t).strip()


class SocialFetcher(QThread):
    posts_ready = pyqtSignal(str, list)
    error = pyqtSignal(str, str)

    def __init__(self, platform, params, parent=None):
        super().__init__(parent)
        self.platform = platform
        self.params = params

    def run(self):
        try:
            posts = []
            if self.platform == "reddit":
                from core.social.reddit import fetch_reddit
                posts = fetch_reddit(self.params.get("subreddits","worldnews"))
            elif self.platform == "bluesky":
                from core.social.bluesky import fetch_bluesky
                posts = fetch_bluesky()
            elif self.platform == "mastodon":
                from core.social.mastodon import fetch_mastodon
                posts = fetch_mastodon(self.params.get("instance","mastodon.social"))
            elif self.platform == "youtube":
                from core.social.youtube import fetch_youtube
                posts = fetch_youtube(self.params.get("api_key",""))
            elif self.platform == "twitter":
                from core.social.twitter import fetch_twitter
                posts = fetch_twitter(self.params.get("username",""), self.params.get("password",""))
            elif self.platform == "substack":
                from core.social.substack import fetch_substack
                posts = fetch_substack(self.params.get("urls", ""))
            from core.database import save_social_posts
            if posts: save_social_posts(posts)
            self.posts_ready.emit(self.platform, posts)
        except Exception as e:
            self.error.emit(self.platform, str(e))


class PostCard(QFrame):
    def __init__(self, post: dict, night_mode=False, parent=None):
        super().__init__(parent)
        self.setObjectName("articleCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        hdr = QHBoxLayout()
        author = QLabel(f"@{_clean(post.get('author','')[:20])}")
        author.setObjectName("stampLabel")
        hdr.addWidget(author)
        hdr.addStretch()
        score = post.get("score",0)
        if score:
            sl = QLabel(f"▲ {score:,}")
            sl.setObjectName("statusLabel")
            hdr.addWidget(sl)
        layout.addLayout(hdr)

        content = _clean(post.get("content",""))
        cl = QLabel(content[:280] + ("…" if len(content) > 280 else ""))
        cl.setWordWrap(True)
        font = QFont("IM Fell English", 12)
        cl.setFont(font)
        layout.addWidget(cl)

        cat = post.get("category","")
        if cat:
            bl = QLabel(cat)
            bl.setObjectName("categoryBadge")
            layout.addWidget(bl, alignment=Qt.AlignmentFlag.AlignLeft)


class SocialPlatformView(QWidget):
    """View de uma plataforma específica."""
    def __init__(self, platform: str, params: dict, night_mode=False, parent=None):
        super().__init__(parent)
        self.platform = platform
        self.params = params
        self.night_mode = night_mode
        self._fetcher = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton(f"↻  Atualizar {self.platform.title()}")
        self.refresh_btn.setObjectName("btnPrimary")
        self.refresh_btn.clicked.connect(self.fetch)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addStretch()
        self.status_lbl = QLabel("Clique em Atualizar para carregar.")
        self.status_lbl.setObjectName("statusLabel")
        toolbar.addWidget(self.status_lbl)
        layout.addLayout(toolbar)

        self.progress = QProgressBar()
        self.progress.setRange(0,0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(0,0,0,0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        # Carrega do banco imediatamente
        self._load_from_db()

    def fetch(self):
        self.progress.show()
        self.refresh_btn.setEnabled(False)
        self.status_lbl.setText("Carregando…")
        self._fetcher = SocialFetcher(self.platform, self.params)
        self._fetcher.posts_ready.connect(self._on_posts)
        self._fetcher.error.connect(self._on_error)
        self._fetcher.start()

    def _on_posts(self, platform, posts):
        self.progress.hide()
        self.refresh_btn.setEnabled(True)
        self.status_lbl.setText(f"{len(posts)} posts carregados")
        self._show_posts(posts)

    def _on_error(self, platform, err):
        self.progress.hide()
        self.refresh_btn.setEnabled(True)
        self.status_lbl.setText(f"Erro: {err[:60]}")

    def _load_from_db(self):
        from core.database import get_social_posts
        posts = get_social_posts(platform=self.platform, limit=40)
        if posts:
            self._show_posts(posts)
            self.status_lbl.setText(f"{len(posts)} posts (cache local)")

    def _show_posts(self, posts):
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i, p in enumerate(posts[:50]):
            card = PostCard(p, self.night_mode)
            self.cards_layout.insertWidget(i, card)


class SocialView(QWidget):
    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._build()

    def _build(self):
        from core.database import get_setting
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Redes & Tendências Sociais")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        hint = QLabel("Monitore os assuntos mais comentados nas redes sociais e compare com a cobertura da mídia.")
        hint.setObjectName("statusLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tabs = QTabWidget()

        platforms = [
            ("Substack",  "substack", {"urls": get_setting("substack_urls", "")}),
            ("Reddit",    "reddit",   {"subreddits": get_setting("reddit_subreddits","worldnews,brasil,technology")}),
            ("Bluesky",   "bluesky",  {}),
            ("Mastodon",  "mastodon", {"instance": get_setting("mastodon_instance","mastodon.social")}),
            ("YouTube",   "youtube",  {"api_key": get_setting("youtube_api_key","")}),
            ("Twitter/X", "twitter",  {"username": get_setting("twitter_username",""), "password": get_setting("twitter_password","")}),
        ]

        self._platform_views = {}
        for label, key, params in platforms:
            view = SocialPlatformView(key, params, self.night_mode)
            # Twitter desativado visualmente se não configurado
            if key == "twitter" and not get_setting("twitter_enabled","0") == "1":
                tab_label = f"{label} (desativado)"
            else:
                tab_label = label
            self.tabs.addTab(view, tab_label)
            self._platform_views[key] = view

        layout.addWidget(self.tabs)

    def refresh(self):
        pass  # lazy — usuário clica em atualizar em cada aba
