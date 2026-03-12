"""
Cronos - SocialView v2.0
Redes sociais com botões de configuração por aba e Twitter/X ativado.
"""
import html, re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QScrollArea, QFrame, QListWidget, QListWidgetItem,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox,
    QProgressBar, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


def _clean(t):
    if not t: return ""
    for _ in range(3):
        d = html.unescape(t)
        if d == t: break
        t = d
    return re.sub(r'<[^>]+>', ' ', t).strip()


# ── Configurações por plataforma ──────────────────────────────────────────────

PLATFORM_CONFIGS = {
    "substack": {
        "label": "Substack",
        "fields": [
            ("substack_urls", "URLs (uma por linha)", "multiline",
             "https://newsletter.exemplo.com/feed"),
        ],
        "help": "Cole as URLs dos feeds RSS dos newsletters Substack que quer seguir.",
    },
    "reddit": {
        "label": "Reddit",
        "fields": [
            ("reddit_subreddits", "Subreddits (separados por vírgula)", "text",
             "worldnews,brasil,technology"),
        ],
        "help": "Ex: worldnews,brasil,technology — sem o r/",
    },
    "bluesky": {
        "label": "Bluesky",
        "fields": [
            ("bluesky_handle", "Handle (ex: usuario.bsky.social)", "text", ""),
            ("bluesky_app_password", "App Password (em Configurações > Privacidade)", "password", ""),
        ],
        "help": "Crie um App Password em bsky.app → Configurações → Privacidade e Segurança.",
    },
    "mastodon": {
        "label": "Mastodon",
        "fields": [
            ("mastodon_instance", "Instância (ex: mastodon.social)", "text", "mastodon.social"),
            ("mastodon_access_token", "Access Token (opcional)", "password", ""),
        ],
        "help": "O Access Token permite ver posts do seu feed. Sem ele, mostra o feed público da instância.",
    },
    "youtube": {
        "label": "YouTube",
        "fields": [
            ("youtube_api_key", "API Key do Google", "password", ""),
            ("youtube_channels", "IDs de canais (separados por vírgula)", "text", ""),
        ],
        "help": "Obtenha uma API Key em console.cloud.google.com → APIs → YouTube Data API v3.",
    },
    "twitter": {
        "label": "Twitter/X",
        "fields": [
            ("twitter_username", "Usuário (e-mail ou @handle)", "text", ""),
            ("twitter_password", "Senha", "password", ""),
        ],
        "help": "Usa twscrape para buscar tweets sem API oficial. Requer conta real do Twitter/X.",
    },
}


class _ConfigDialog(QDialog):
    """Diálogo genérico de configuração de uma plataforma social."""

    def __init__(self, platform: str, parent=None):
        super().__init__(parent)
        from core.database import get_setting
        cfg = PLATFORM_CONFIGS[platform]
        self.platform  = platform
        self.cfg       = cfg
        self._fields   = {}

        self.setWindowTitle(f"Configurar {cfg['label']}")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        help_lbl = QLabel(cfg["help"])
        help_lbl.setWordWrap(True)
        help_lbl.setObjectName("statusLabel")
        layout.addWidget(help_lbl)

        form = QFormLayout()
        form.setSpacing(8)
        for key, label, ftype, placeholder in cfg["fields"]:
            current = get_setting(key, "")
            if ftype == "password":
                w = QLineEdit(current)
                w.setEchoMode(QLineEdit.EchoMode.Password)
            elif ftype == "multiline":
                from PyQt6.QtWidgets import QPlainTextEdit
                w = QPlainTextEdit(current)
                w.setFixedHeight(80)
                w.setPlaceholderText(placeholder)
            else:
                w = QLineEdit(current)
                w.setPlaceholderText(placeholder)
            self._fields[key] = w
            form.addRow(f"{label}:", w)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        from core.database import set_setting
        from PyQt6.QtWidgets import QPlainTextEdit
        for key, w in self._fields.items():
            if isinstance(w, QPlainTextEdit):
                set_setting(key, w.toPlainText().strip())
            else:
                set_setting(key, w.text().strip())
        self.accept()


# ── Worker de fetch ───────────────────────────────────────────────────────────

class SocialFetcher(QThread):
    posts_ready = pyqtSignal(str, list)
    error       = pyqtSignal(str, str)

    def __init__(self, platform, params, parent=None):
        super().__init__(parent)
        self.platform = platform
        self.params   = params

    def run(self):
        try:
            posts = []
            p = self.platform
            if p == "reddit":
                from core.social.reddit import fetch_reddit
                posts = fetch_reddit(self.params.get("subreddits", "worldnews"))
            elif p == "bluesky":
                from core.social.bluesky import fetch_bluesky
                posts = fetch_bluesky()
            elif p == "mastodon":
                from core.social.mastodon import fetch_mastodon
                posts = fetch_mastodon(self.params.get("instance", "mastodon.social"))
            elif p == "youtube":
                from core.social.youtube import fetch_youtube
                posts = fetch_youtube(self.params.get("api_key", ""))
            elif p == "twitter":
                from core.social.twitter import fetch_twitter
                posts = fetch_twitter(
                    self.params.get("username", ""),
                    self.params.get("password", "")
                )
            elif p == "substack":
                from core.social.substack import fetch_substack
                posts = fetch_substack(self.params.get("urls", ""))

            from core.database import save_social_posts
            if posts:
                save_social_posts(posts)
            self.posts_ready.emit(self.platform, posts)
        except Exception as e:
            self.error.emit(self.platform, str(e))


# ── Card de post ──────────────────────────────────────────────────────────────

class PostCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, post: dict, night_mode=False, parent=None):
        super().__init__(parent)
        self._post = post
        self.setObjectName("articleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        hdr = QHBoxLayout()
        author = QLabel(f"@{_clean(post.get('author',''))[:30]}")
        author.setObjectName("stampLabel")
        hdr.addWidget(author)
        hdr.addStretch()
        score = post.get("score", 0)
        if score:
            sl = QLabel(f"▲ {score:,}")
            sl.setObjectName("statusLabel")
            hdr.addWidget(sl)

        # Botão abrir URL
        url = post.get("url", "")
        if url:
            open_btn = QPushButton("↗")
            open_btn.setFixedSize(24, 24)
            open_btn.setToolTip("Abrir no navegador")
            open_btn.clicked.connect(lambda: self._open_url(url))
            hdr.addWidget(open_btn)

        layout.addLayout(hdr)

        content = _clean(post.get("content", ""))
        cl = QLabel(content[:300] + ("…" if len(content) > 300 else ""))
        cl.setWordWrap(True)
        cl.setFont(QFont("IM Fell English", 12))
        layout.addWidget(cl)

        cat = post.get("category", "")
        if cat:
            bl = QLabel(cat)
            bl.setObjectName("categoryBadge")
            layout.addWidget(bl, alignment=Qt.AlignmentFlag.AlignLeft)

    def _open_url(self, url: str):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._post)
        super().mousePressEvent(event)


# ── View de uma plataforma ────────────────────────────────────────────────────

class SocialPlatformView(QWidget):
    def __init__(self, platform: str, parent=None):
        super().__init__(parent)
        self.platform = platform
        self._fetcher = None
        self._build()

    def _get_params(self) -> dict:
        from core.database import get_setting
        cfg = PLATFORM_CONFIGS[self.platform]
        params = {}
        for key, _, _, _ in cfg["fields"]:
            params[key.replace(f"{self.platform}_", "")] = get_setting(key, "")
        # Aliases esperados pelos fetchers
        params["subreddits"]  = get_setting("reddit_subreddits", "worldnews,brasil")
        params["instance"]    = get_setting("mastodon_instance", "mastodon.social")
        params["api_key"]     = get_setting("youtube_api_key", "")
        params["username"]    = get_setting("twitter_username", "")
        params["password"]    = get_setting("twitter_password", "")
        params["urls"]        = get_setting("substack_urls", "")
        return params

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        cfg_lbl = PLATFORM_CONFIGS[self.platform]["label"]

        self.refresh_btn = QPushButton(f"↻  Atualizar")
        self.refresh_btn.setObjectName("btnPrimary")
        self.refresh_btn.clicked.connect(self.fetch)
        toolbar.addWidget(self.refresh_btn)

        config_btn = QPushButton("⚙ Configurar")
        config_btn.clicked.connect(self._open_config)
        toolbar.addWidget(config_btn)

        toolbar.addStretch()

        self.status_lbl = QLabel("Clique em Atualizar para carregar.")
        self.status_lbl.setObjectName("statusLabel")
        toolbar.addWidget(self.status_lbl)
        layout.addLayout(toolbar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self._load_from_db()

    def _open_config(self):
        dlg = _ConfigDialog(self.platform, parent=self)
        dlg.exec()

    def fetch(self):
        self.progress.show()
        self.refresh_btn.setEnabled(False)
        self.status_lbl.setText("Carregando…")
        self._fetcher = SocialFetcher(self.platform, self._get_params())
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
        self.status_lbl.setText(f"Erro: {err[:80]}")

    def _load_from_db(self):
        from core.database import get_social_posts
        posts = get_social_posts(platform=self.platform, limit=40)
        if posts:
            self._show_posts(posts)
            self.status_lbl.setText(f"{len(posts)} posts (cache local)")

    def _on_card_click(self, post: dict):
        """Abre a URL do post no navegador, ou mostra conteúdo expandido."""
        url = post.get("url", "")
        if url:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))
        else:
            # Sem URL: mostra conteúdo completo num diálogo simples
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle(post.get("author", "Post"))
            dlg.setMinimumSize(520, 300)
            lay = QVBoxLayout(dlg)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setPlainText(_clean(post.get("content", "")))
            lay.addWidget(txt)
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            btns.rejected.connect(dlg.reject)
            lay.addWidget(btns)
            dlg.exec()

    def _show_posts(self, posts):
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, p in enumerate(posts[:50]):
            card = PostCard(p)
            card.clicked.connect(self._on_card_click)
            self.cards_layout.insertWidget(i, card)


# ── View principal ────────────────────────────────────────────────────────────

class SocialView(QWidget):
    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Redes & Tendências Sociais")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        hint = QLabel(
            "Monitore os assuntos mais comentados nas redes sociais e compare com a cobertura da mídia. "
            "Clique em ⚙ Configurar em cada aba para inserir suas credenciais."
        )
        hint.setObjectName("statusLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tabs = QTabWidget()

        platforms = ["substack", "reddit", "bluesky", "mastodon", "youtube", "twitter"]
        self._platform_views = {}
        for key in platforms:
            view = SocialPlatformView(key)
            label = PLATFORM_CONFIGS[key]["label"]
            self.tabs.addTab(view, label)
            self._platform_views[key] = view

        layout.addWidget(self.tabs)

    def refresh(self):
        pass  # lazy — usuário clica em cada aba
