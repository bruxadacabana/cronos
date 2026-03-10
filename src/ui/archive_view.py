"""
Cronos - ArchiveView
Arquivo pessoal: salva artigos com tags múltiplas.
"""
import html, re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QDialog, QLineEdit, QTextEdit, QMessageBox, QInputDialog,
    QSplitter, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

from core.database import (
    get_archive_tags, get_archive_items, remove_from_archive,
    rename_archive_tag, delete_archive_tag
)
from .widgets.article_card import ArticleCard, clean


class ArchiveView(QWidget):
    article_selected = pyqtSignal(dict)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._current_tag = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Painel esquerdo: lista de tags ──────────────────────────────────
        left = QWidget()
        left.setObjectName("archiveTagPanel")
        left.setMinimumWidth(180)
        left.setMaximumWidth(260)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 12)
        lv.setSpacing(8)

        hdr = QLabel("🗂  Arquivo")
        hdr.setObjectName("sectionHeader")
        lv.addWidget(hdr)

        self.search_tags = QLineEdit()
        self.search_tags.setObjectName("searchInput")
        self.search_tags.setPlaceholderText("Filtrar tags…")
        self.search_tags.textChanged.connect(self._filter_tags)
        lv.addWidget(self.search_tags)

        self.tag_list = QListWidget()
        self.tag_list.setObjectName("tagList")
        self.tag_list.currentItemChanged.connect(self._on_tag_selected)
        lv.addWidget(self.tag_list)

        tag_btns = QHBoxLayout()
        rename_btn = QPushButton("✏")
        rename_btn.setFixedWidth(34)
        rename_btn.setToolTip("Renomear tag")
        rename_btn.clicked.connect(self._rename_tag)
        del_tag_btn = QPushButton("✕")
        del_tag_btn.setFixedWidth(34)
        del_tag_btn.setObjectName("btnDanger")
        del_tag_btn.setToolTip("Apagar tag")
        del_tag_btn.clicked.connect(self._delete_tag)
        tag_btns.addWidget(rename_btn)
        tag_btns.addWidget(del_tag_btn)
        tag_btns.addStretch()
        lv.addLayout(tag_btns)

        splitter.addWidget(left)

        # ── Painel direito: artigos da tag ──────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("filterBar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(14, 8, 14, 8)
        tb.setSpacing(8)

        self.title_lbl = QLabel("Selecione uma tag")
        self.title_lbl.setObjectName("sectionHeader")
        tb.addWidget(self.title_lbl)
        tb.addStretch()

        self.search_articles = QLineEdit()
        self.search_articles.setObjectName("searchInput")
        self.search_articles.setPlaceholderText("Buscar nos arquivados…")
        self.search_articles.setMaximumWidth(240)
        self.search_articles.returnPressed.connect(self._load_articles)
        tb.addWidget(self.search_articles)

        rv.addWidget(toolbar)

        # Scroll de cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(16, 12, 16, 12)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()

        self.scroll.setWidget(self.container)
        rv.addWidget(self.scroll)

        splitter.addWidget(right)
        splitter.setSizes([200, 800])
        root.addWidget(splitter)

        self.reload()

    # ── Tags ─────────────────────────────────────────────────────────────────

    def reload(self):
        self.tag_list.clear()

        # Item "Todos"
        all_item = QListWidgetItem("📂  Todos os arquivados")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.tag_list.addItem(all_item)

        tags = get_archive_tags()
        for tag in tags:
            items = get_archive_items(tag=tag)
            item = QListWidgetItem(f"🏷  {tag}  ({len(items)})")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self.tag_list.addItem(item)

        if self.tag_list.count() > 0:
            self.tag_list.setCurrentRow(0)

    def _filter_tags(self, text):
        for i in range(self.tag_list.count()):
            it = self.tag_list.item(i)
            it.setHidden(text.lower() not in it.text().lower())

    def _on_tag_selected(self, current, _):
        if not current:
            return
        self._current_tag = current.data(Qt.ItemDataRole.UserRole)
        self._load_articles()

    def _rename_tag(self):
        item = self.tag_list.currentItem()
        if not item:
            return
        tag = item.data(Qt.ItemDataRole.UserRole)
        if not tag:
            return
        new_name, ok = QInputDialog.getText(self, "Renomear tag", "Novo nome:", text=tag)
        if ok and new_name.strip() and new_name.strip() != tag:
            rename_archive_tag(tag, new_name.strip())
            self.reload()

    def _delete_tag(self):
        item = self.tag_list.currentItem()
        if not item:
            return
        tag = item.data(Qt.ItemDataRole.UserRole)
        if not tag:
            return
        reply = QMessageBox.question(
            self, "Confirmar",
            f"Apagar a tag '{tag}' e remover todos os artigos dela do arquivo?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_archive_tag(tag)
            self.reload()

    # ── Artigos ───────────────────────────────────────────────────────────────

    def _load_articles(self):
        search = self.search_articles.text().strip() or None
        items = get_archive_items(tag=self._current_tag, search=search)

        # Limpa cards
        while self.cards_layout.count() > 1:
            it = self.cards_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        tag_label = self._current_tag or "Todos"
        self.title_lbl.setText(f"🗂  {tag_label}  —  {len(items)} artigo{'s' if len(items) != 1 else ''}")

        if not items:
            lbl = QLabel("Nenhum artigo arquivado aqui.\nAbra uma notícia e clique em '📁 Arquivar'.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setObjectName("emptyLabel")
            self.cards_layout.insertWidget(0, lbl)
            return

        for i, item in enumerate(items):
            card = _ArchiveCard(item, self.night_mode, index=i)
            card.open_article.connect(self.article_selected)
            card.remove_requested.connect(self._on_remove)
            self.cards_layout.insertWidget(i, card)

    def _on_remove(self, article_id, tag):
        remove_from_archive(article_id, tag if tag != "__all__" else None)
        self.reload()
        self._load_articles()


class _ArchiveCard(QFrame):
    open_article = pyqtSignal(dict)
    remove_requested = pyqtSignal(int, str)

    def __init__(self, item: dict, night_mode=False, index=0, parent=None):
        super().__init__(parent)
        self.item = item
        self.night_mode = night_mode
        self.setObjectName("articleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()
        QTimer.singleShot(index * 40, self._fade_in)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(5)

        # Header
        hdr = QHBoxLayout()
        src = QLabel(clean(self.item.get("source_name", "")).upper()[:20])
        src.setObjectName("stampLabel")
        hdr.addWidget(src)

        tag_lbl = QLabel(f"🏷 {self.item.get('tag', '')}")
        tag_lbl.setObjectName("categoryBadge")
        hdr.addWidget(tag_lbl)
        hdr.addStretch()

        saved = self.item.get("saved_at", "")[:10]
        if saved:
            dl = QLabel(f"📁 {saved}")
            dl.setObjectName("statusLabel")
            hdr.addWidget(dl)

        layout.addLayout(hdr)

        # Título
        title = QLabel(clean(self.item.get("title", "")))
        title.setWordWrap(True)
        font = QFont("IM Fell English", 13)
        font.setItalic(True)
        title.setFont(font)
        layout.addWidget(title)

        # Nota
        note = self.item.get("note", "")
        if note:
            note_lbl = QLabel(f"📝 {note}")
            note_lbl.setWordWrap(True)
            note_lbl.setObjectName("statusLabel")
            layout.addWidget(note_lbl)

        # Resumo
        summary = clean(self.item.get("ai_summary") or self.item.get("summary", ""))
        if summary:
            sl = QLabel(summary[:180] + ("…" if len(summary) > 180 else ""))
            sl.setWordWrap(True)
            sl.setObjectName("statusLabel")
            layout.addWidget(sl)

        # Footer
        ftr = QHBoxLayout()
        open_btn = QPushButton("Abrir notícia →")
        open_btn.setObjectName("btnPrimary")
        open_btn.setFixedHeight(28)
        open_btn.clicked.connect(lambda: self.open_article.emit(dict(self.item)))
        ftr.addWidget(open_btn)
        ftr.addStretch()

        rem_btn = QPushButton("✕ Remover")
        rem_btn.setObjectName("btnDanger")
        rem_btn.setFixedHeight(28)
        rem_btn.clicked.connect(lambda: self.remove_requested.emit(
            self.item["article_id"], self.item.get("tag", "__all__")
        ))
        ftr.addWidget(rem_btn)
        layout.addLayout(ftr)

    def _fade_in(self):
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity")
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_article.emit(dict(self.item))
        super().mousePressEvent(event)


class ArchiveDialog(QDialog):
    """Dialog para arquivar um artigo com tags e nota."""

    def __init__(self, article: dict, existing_tags: list, night_mode=False, parent=None):
        super().__init__(parent)
        self.article = article
        self.setWindowTitle("Arquivar notícia")
        self.setMinimumWidth(460)
        self._build(existing_tags)

    def _build(self, existing_tags):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(clean(self.article.get("title", ""))[:100])
        title.setWordWrap(True)
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        # Tags existentes como botões de atalho
        if existing_tags:
            layout.addWidget(QLabel("Tags existentes (clique para adicionar):"))
            tags_row = QWidget()
            tags_fl = QHBoxLayout(tags_row)
            tags_fl.setContentsMargins(0, 0, 0, 0)
            tags_fl.setSpacing(6)
            for tag in existing_tags[:8]:
                btn = QPushButton(f"🏷 {tag}")
                btn.setFixedHeight(26)
                btn.clicked.connect(lambda _, t=tag: self._add_quick_tag(t))
                tags_fl.addWidget(btn)
            tags_fl.addStretch()
            layout.addWidget(tags_row)

        # Campo de tags
        layout.addWidget(QLabel("Tags (separadas por vírgula):"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("ex: política, favoritos, para-ler")
        layout.addWidget(self.tags_input)

        # Nota opcional
        layout.addWidget(QLabel("Nota (opcional):"))
        self.note_input = QTextEdit()
        self.note_input.setMaximumHeight(80)
        self.note_input.setPlaceholderText("Por que você está arquivando este artigo?")
        layout.addWidget(self.note_input)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("📁 Arquivar")
        ok.setObjectName("btnPrimary")
        ok.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _add_quick_tag(self, tag):
        current = self.tags_input.text()
        tags = [t.strip() for t in current.split(",") if t.strip()]
        if tag not in tags:
            tags.append(tag)
        self.tags_input.setText(", ".join(tags))

    def get_data(self):
        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        note = self.note_input.toPlainText().strip()
        return tags, note
