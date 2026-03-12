"""
Cronos - ReaderView v1.3
Leitor de artigos com botão de "Pontos de Vista" para comparação de viés.
"""
import sys, html, re
from pathlib import Path
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QFrame, QComboBox, QGraphicsOpacityEffect, QSizePolicy,
    QDialog, QListWidget, QListWidgetItem, QScrollArea, QStackedWidget,
    QProgressBar
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QThread, pyqtSignal, QRect
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import mark_read, toggle_favorite, get_article, get_articles
from core.fetcher import fetch_article_content, find_similar_articles, _is_meaningful
from core.translator import get_supported_languages, translate_article


def clean(text):
    if not text: return ""
    for _ in range(3):
        d = html.unescape(text)
        if d == text: break
        text = d
    return re.sub(r'\s+', ' ', text).strip()


def _is_markdown(content: str) -> bool:
    """Heurística: tem pelo menos uma marca Markdown estrutural."""
    return bool(re.search(r"(^#{1,4} |^- |\*\*|^> )", content, re.MULTILINE))


def _markdown_to_html(md: str) -> str:
    """
    Converte Markdown em HTML rico para o QTextBrowser.
    Ordem de tentativas: markdown stdlib → regex manual.
    """
    try:
        import markdown as _md_lib
        return _md_lib.markdown(md, extensions=["extra", "nl2br"])
    except ImportError:
        pass

    # Fallback manual via regex (cobre 90% dos casos do Cronos)
    html_out = md

    # Headings  # ## ###
    html_out = re.sub(r"^### (.+)$",  r"<h3>\1</h3>", html_out, flags=re.MULTILINE)
    html_out = re.sub(r"^## (.+)$",   r"<h2>\1</h2>", html_out, flags=re.MULTILINE)
    html_out = re.sub(r"^# (.+)$",    r"<h1>\1</h1>", html_out, flags=re.MULTILINE)
    # Blockquotes
    html_out = re.sub(r"^> (.+)$",    r"<blockquote>\1</blockquote>", html_out, flags=re.MULTILINE)
    # Bold / italic
    html_out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html_out)
    html_out = re.sub(r"\*(.+?)\*",   r"<i>\1</i>", html_out)
    # Listas
    html_out = re.sub(r"^- (.+)$",    r"<li>\1</li>",   html_out, flags=re.MULTILINE)
    html_out = re.sub(r"(<li>.*</li>\n?)+", r"<ul>\g<0></ul>", html_out, flags=re.DOTALL)
    # Parágrafos: blocos de texto separados por linha vazia
    blocks = re.split(r"\n{2,}", html_out)
    parts  = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        if re.match(r"<(h[1-4]|ul|blockquote)", b):
            parts.append(b)
        else:
            parts.append(f"<p>{b.replace(chr(10), ' ')}</p>")
    return "\n".join(parts)


def _normalize_content(content: str) -> str:
    """
    Normaliza conteúdo para HTML rico exibível no QTextBrowser.
    Detecta Markdown (novo padrão) → converte para HTML estruturado.
    Fallback para texto plano → agrupa em parágrafos.
    """
    if not content or str(content).strip().lower() in ("none", "null"):
        return ""

    content = str(content).strip()

    # 1. Markdown estruturado (vem do novo scraper) → HTML rico
    if _is_markdown(content):
        return _markdown_to_html(content)

    # 2. Já é HTML com tags — limpa e reconstrói parágrafos
    if re.search(r"<p[^>]*>", content, re.IGNORECASE):
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", content, re.DOTALL | re.IGNORECASE)
        if paragraphs:
            cleaned = []
            for p in paragraphs:
                text = re.sub(r"<[^>]+>", " ", p)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 20:
                    cleaned.append(text)
            if cleaned:
                return "".join(f"<p>{p}</p>" for p in cleaned)

    # 3. Texto plano puro — divide por quebras e agrupa em parágrafos
    raw = re.sub(r"<[^>]+>", " ", content)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return ""

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]

    # 4. Bloco único → divide por frases (3 por parágrafo)
    if len(paragraphs) <= 1:
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚ"\u201C\u201E])', raw)
        buf, groups = [], []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            buf.append(s)
            if len(buf) >= 3:
                groups.append(" ".join(buf))
                buf = []
        if buf:
            groups.append(" ".join(buf))
        paragraphs = groups if len(groups) > 1 else [raw]

    return "".join(f"<p>{p}</p>" for p in paragraphs)



class TranslationWorker(QThread):
    finished_translation = pyqtSignal(dict)

    def __init__(self, article, lang, parent=None):
        super().__init__(parent)
        self.article = article
        self.lang = lang

    def run(self):
        result = translate_article(
            self.article["id"],
            self.article.get("title", ""),
            self.article.get("content_clean") or self.article.get("content", ""),
            self.article.get("summary", ""), 
            self.lang
        )
        self.finished_translation.emit(result)


class _BiasBar(QWidget):
    """Barra visual de viés político (esq ←→ dir)."""
    def __init__(self, ea, aa, night=False, parent=None):
        super().__init__(parent)
        self.ea = ea or 0.0
        self.aa = aa or 0.0
        self.night = night
        self.setFixedSize(120, 14)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
        from PyQt6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Track
        track = QColor("#2a0050" if self.night else "#d4c090")
        p.setBrush(QBrush(track)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 3, w, h-6), 4, 4)
        # Fill
        mid = w // 2
        bw = int(abs(self.ea) * mid)
        x = mid - bw if self.ea < 0 else mid
        col = QColor("#dd4444" if self.ea < 0 else "#4488dd")
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(x, 3, bw, h-6), 3, 3)
        # Center line
        p.setPen(QPen(QColor("#9900ff" if self.night else "#8b6914"), 1))
        p.drawLine(mid, 0, mid, h)


class _PovCard(QFrame):
    """Card visual para um artigo no dialog Pontos de Vista."""
    open_requested = pyqtSignal(dict)

    def __init__(self, art: dict, night=False, parent=None):
        super().__init__(parent)
        self.art = art
        self.setObjectName("articleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Header: fonte + viés
        hdr = QHBoxLayout()
        src = QLabel(clean(art.get("source_name", "")).upper()[:22])
        src.setObjectName("stampLabel")
        hdr.addWidget(src)
        hdr.addSpacing(8)

        # Texto de viés
        ea = art.get("source_economic", 0) or 0
        aa = art.get("source_authority", 0) or 0
        bias_txt = _bias_label(ea, aa)
        bias_lbl = QLabel(bias_txt)
        bias_lbl.setObjectName("categoryBadge")
        hdr.addWidget(bias_lbl)
        hdr.addSpacing(6)
        hdr.addWidget(_BiasBar(ea, aa, night))
        hdr.addStretch()

        pub = art.get("published_at", "")[:10]
        if pub:
            dl = QLabel(pub)
            dl.setObjectName("statusLabel")
            hdr.addWidget(dl)
        layout.addLayout(hdr)

        # Título
        title = QLabel(clean(art.get("title", "")))
        title.setWordWrap(True)
        f = QFont("IM Fell English", 12)
        f.setItalic(True)
        title.setFont(f)
        layout.addWidget(title)

        # Resumo
        summary = clean(art.get("ai_summary") or art.get("summary", ""))
        if summary:
            sl = QLabel(summary[:140] + ("…" if len(summary) > 140 else ""))
            sl.setWordWrap(True)
            sl.setObjectName("statusLabel")
            layout.addWidget(sl)

        # Botão abrir
        open_btn = QPushButton("Ler esta matéria →")
        open_btn.setObjectName("btnPrimary")
        open_btn.setFixedHeight(26)
        open_btn.clicked.connect(lambda: self.open_requested.emit(art))
        layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.art)
        super().mousePressEvent(event)


def _bias_label(ea, aa):
    eco = "Centro"
    if ea <= -0.4:   eco = "◀◀ Esquerda"
    elif ea <= -0.1: eco = "◀ C-Esq"
    elif ea >= 0.4:  eco = "Direita ▶▶"
    elif ea >= 0.1:  eco = "C-Dir ▶"
    auth = ""
    if aa >= 0.3:    auth = " · Aut↑"
    elif aa <= -0.3: auth = " · Lib↓"
    return eco + auth


class PointsOfViewDialog(QDialog):
    """Pontos de Vista — redesenhado com cards visuais e viés político."""
    article_selected         = pyqtSignal(dict)
    retry_analysis_requested = pyqtSignal(int)   # article_id

    def __init__(self, current_article, night_mode=False, parent=None):
        super().__init__(parent)
        self.current_article = current_article
        self.night_mode = night_mode
        self.setWindowTitle("👁  Outros Pontos de Vista")
        self.setMinimumWidth(720)
        self.setMinimumHeight(560)
        self._build()
        self._load_similar_articles()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title_art = clean(self.current_article.get("title", ""))[:80]
        lbl = QLabel(f"Cobertura de:  {title_art}")
        lbl.setObjectName("sectionHeader")
        lbl.setWordWrap(True)
        hdr.addWidget(lbl, 1)
        close_btn = QPushButton("✕ Fechar")
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # Legenda de viés
        legend = QLabel("Barra de viés:  ◀ vermelho = esquerda  |  azul ▶ = direita  |  tamanho = intensidade")
        legend.setObjectName("statusLabel")
        layout.addWidget(legend)

        # Scroll de cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.status_lbl = QLabel("Buscando matérias similares…")
        self.status_lbl.setObjectName("statusLabel")
        layout.addWidget(self.status_lbl)

    def _load_similar_articles(self):
        from core.fetcher import find_similar_articles

        try:
            pub_date_str = self.current_article.get("published_at", "")[:19].replace("Z", "")
            pub_date = datetime.fromisoformat(pub_date_str)
        except Exception:
            pub_date = datetime.now()

        date_from = (pub_date - timedelta(days=5)).isoformat()
        date_to   = (pub_date + timedelta(days=5)).isoformat()
        all_arts  = get_articles(limit=1500, date_from=date_from, date_to=date_to)

        results = find_similar_articles(
            self.current_article, all_arts,
            min_score=0.12, max_results=15
        )

        # Limpa placeholder
        while self.cards_layout.count() > 1:
            it = self.cards_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        if not results:
            self.status_lbl.setText("Nenhuma cobertura adicional encontrada para este assunto.")
            return

        self.status_lbl.setText(f"{len(results[:15])} matérias encontradas de fontes diferentes")
        for i, (score, art) in enumerate(results[:15]):
            card = _PovCard(art, self.night_mode)
            card.open_requested.connect(self._on_open)
            self.cards_layout.insertWidget(i, card)

    def _on_open(self, art):
        self.article_selected.emit(art)
        # NÃO fecha — permite continuar comparando


class ReaderView(QWidget):
    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self.current_article = None
        self.hide()   # visível só ao abrir artigo
        self._build()

    # ── Overlay escurecido ────────────────────────────────────────────────────
    def paintEvent(self, event):
        """Pinta o fundo escurecido do overlay."""
        p = QPainter(self)
        if self.night_mode:
            p.fillRect(self.rect(), QColor(0, 0, 10, 184))
        else:
            p.fillRect(self.rect(), QColor(30, 18, 4, 176))

    def _apply_modal_style(self):
        if self.night_mode:
            self._modal.setStyleSheet(
                "QFrame#readerModal{background:#080012;border:1px solid #7700ee;border-left:3px solid #cc0066;}"
            )
        else:
            self._modal.setStyleSheet(
                "QFrame#readerModal{background:#faf5e8;border:1px solid #b89050;border-left:3px solid #c03020;}"
            )

    def _update_margin_style(self):
        if self.night_mode:
            self._margin.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #cc0066,stop:1 #880044);")
        else:
            self._margin.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #c03928,stop:1 #901a10);")

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(0)

        # Caixa modal
        self._modal = QFrame(self)
        self._modal.setObjectName("readerModal")
        self._apply_modal_style()
        layout = QVBoxLayout(self._modal)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        outer.addWidget(self._modal)

        # Toolbar
        toolbar = QFrame(self._modal)
        toolbar.setObjectName("readerToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(14,8,14,8)
        tb.setSpacing(8)
        
        self.back_btn = QPushButton("◀  Voltar")
        tb.addWidget(self.back_btn)
        
        self.pov_btn = QPushButton("👁 Pontos de Vista")
        self.pov_btn.setObjectName("btnPrimary")
        self.pov_btn.clicked.connect(self._show_pov)
        self.pov_btn.hide()
        tb.addWidget(self.pov_btn)

        self.archive_btn = QPushButton("📁 Arquivar")
        self.archive_btn.clicked.connect(self._archive_article)
        self.archive_btn.hide()
        tb.addWidget(self.archive_btn)
        
        tb.addStretch()
        
        # Banner de clickbait
        self.clickbait_banner = QLabel("⚠  ALTO CLICKBAIT  ⚠")
        self.clickbait_banner.setObjectName("clickbaitBanner")
        self.clickbait_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clickbait_banner.hide()
        tb.addWidget(self.clickbait_banner)
        tb.addStretch()
        tb.addWidget(QLabel("Traduzir:"))
        
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("— idioma —", "")
        for code, name in get_supported_languages().items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.currentIndexChanged.connect(self._on_translate)
        tb.addWidget(self.lang_combo)
        
        self.fav_btn = QPushButton("☆")
        self.fav_btn.setFixedSize(34,34)
        self.fav_btn.clicked.connect(self._toggle_fav)
        tb.addWidget(self.fav_btn)
        layout.addWidget(toolbar)

        # Painel de análise
        self.analysis_panel = QFrame()
        self.analysis_panel.setObjectName("analysisPanel")
        ap = QHBoxLayout(self.analysis_panel)
        ap.setContentsMargins(14,5,14,5)
        ap.setSpacing(10)
        self.bias_lbl = QLabel()
        self.bias_lbl.setObjectName("stampLabel")
        self.tone_lbl = QLabel()
        self.tone_lbl.setObjectName("stampLabel")
        self.cb_lbl = QLabel()
        self.cb_lbl.setObjectName("stampLabel")
        ap.addWidget(self.bias_lbl)
        ap.addWidget(self.tone_lbl)
        ap.addWidget(self.cb_lbl)
        ap.addStretch()
        self.analysis_pending = QLabel("⏳ Analisando…")
        self.analysis_pending.setObjectName("statusLabel")
        self.analysis_pending.hide()
        ap.addWidget(self.analysis_pending)

        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 60000)   # 0..timeout_ms = progresso real
        self.analysis_progress.setValue(0)
        self.analysis_progress.setMaximumWidth(160)
        self.analysis_progress.setFixedHeight(12)
        self.analysis_progress.setTextVisible(False)
        self.analysis_progress.hide()
        ap.addWidget(self.analysis_progress)

        # Flag de falha — carimbo vermelho visível quando análise falha
        self.analysis_fail_lbl = QLabel("✕ Falha na análise")
        self.analysis_fail_lbl.setObjectName("analysisFailFlag")
        self.analysis_fail_lbl.setToolTip(
            "O Ollama não respondeu a tempo.\n"
            "Clique em 'Tentar novamente' para re-analisar."
        )
        self.analysis_fail_lbl.hide()
        ap.addWidget(self.analysis_fail_lbl)

        self.analysis_retry_btn = QPushButton("↺ Tentar novamente")
        self.analysis_retry_btn.setObjectName("btnRetryAnalysis")
        self.analysis_retry_btn.setFixedHeight(22)
        self.analysis_retry_btn.hide()
        self.analysis_retry_btn.clicked.connect(self._retry_analysis)
        ap.addWidget(self.analysis_retry_btn)
        self.analysis_panel.hide()
        layout.addWidget(self.analysis_panel)

        # Corpo: linha margem vermelha + leitor
        body = QHBoxLayout()
        body.setContentsMargins(0,0,0,0)
        body.setSpacing(0)
        # Linha de margem
        self._margin = QFrame()
        self._margin.setFixedWidth(4)
        self._margin.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #c03928, stop:1 #901a10);" if not self.night_mode else "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #cc0066, stop:1 #880044);")
        body.addWidget(self._margin)
        self.reader = QTextBrowser()
        self.reader.setObjectName("articleReader")
        self.reader.setOpenExternalLinks(True)
        body.addWidget(self.reader)
        layout.addLayout(body, 1)

        # Painel POV inline (conteúdo parcial)
        self.pov_inline_frame = QFrame()
        self.pov_inline_frame.setObjectName("povInlineFrame")
        pov_if = QVBoxLayout(self.pov_inline_frame)
        pov_if.setContentsMargins(16, 10, 16, 10)
        pov_if.setSpacing(6)
        pov_hdr = QHBoxLayout()
        pov_title = QLabel("⊘  Conteúdo parcial — outras coberturas do mesmo assunto")
        pov_title.setObjectName("sectionHeader")
        pov_hdr.addWidget(pov_title, 1)
        pov_close = QPushButton("✕")
        pov_close.setFixedSize(24, 24)
        pov_close.setFlat(True)
        pov_close.clicked.connect(self.pov_inline_frame.hide)
        pov_hdr.addWidget(pov_close)
        pov_if.addLayout(pov_hdr)
        self.pov_inline_list = QListWidget()
        self.pov_inline_list.setMaximumHeight(180)
        self.pov_inline_list.itemDoubleClicked.connect(self._on_pov_inline_click)
        pov_if.addWidget(self.pov_inline_list)
        self.pov_inline_frame.hide()
        layout.addWidget(self.pov_inline_frame)

        # Resumo IA
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("summaryFrame")
        sf = QVBoxLayout(self.summary_frame)
        sf.setContentsMargins(20,10,20,10)
        sf.setSpacing(4)
        sf_t = QLabel("✦  Resumo por IA")
        sf_t.setObjectName("sectionHeader")
        
        self.summary_lbl = QLabel()
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setStyleSheet("font-size: 15px; line-height: 1.5;")
        
        self.implications_lbl = QLabel()
        self.implications_lbl.setWordWrap(True)
        self.implications_lbl.setStyleSheet("font-size: 15px; line-height: 1.5;")
        
        sf.addWidget(sf_t)
        sf.addWidget(self.summary_lbl)
        sf.addWidget(self.implications_lbl)
        self.summary_frame.hide()
        layout.addWidget(self.summary_frame)

    # ── Análise prioritária — chamados pelo main_window ──────────────────────

    def notify_analysis_progress(self, elapsed_ms: int, timeout_ms: int):
        """Atualiza a barra de progresso real da análise do artigo aberto."""
        if not self.isVisible():
            return
        self.analysis_pending.show()
        self.analysis_progress.setRange(0, max(timeout_ms, 1))
        self.analysis_progress.setValue(min(elapsed_ms, timeout_ms))
        self.analysis_progress.show()
        self.analysis_fail_lbl.hide()
        self.analysis_retry_btn.hide()

    def notify_analysis_failed(self, article_id: int):
        """Exibe a flag de falha e o botão de retry para o artigo aberto."""
        if not self.isVisible():
            return
        art = getattr(self, "current_article", None)
        if not art or art.get("id") != article_id:
            return
        self.analysis_pending.hide()
        self.analysis_progress.hide()
        self.analysis_fail_lbl.show()
        self.analysis_retry_btn.show()

    def _retry_analysis(self):
        """Re-enfileira o artigo atual para análise prioritária."""
        art = getattr(self, "current_article", None)
        if not art:
            return
        # Esconde fail, mostra spinner
        self.analysis_fail_lbl.hide()
        self.analysis_retry_btn.hide()
        self.analysis_progress.setRange(0, 60000)
        self.analysis_progress.setValue(0)
        self.analysis_pending.show()
        self.analysis_progress.show()
        # Sinaliza para o main_window re-enfileirar
        self.retry_analysis_requested.emit(art["id"])

    def load_article(self, article: dict):
        self.show()   # torna o overlay visível
        self.raise_()
        self.current_article = article
        self.pov_btn.show()
        self.archive_btn.show()
        # Verifica clickbait
        cb = article.get("clickbait_score")
        if cb is not None and cb > 0.5:
            self.clickbait_banner.show()
        else:
            self.clickbait_banner.hide()
        
        mark_read(article["id"])
        self.fav_btn.setText("★" if article.get("is_favorite") else "☆")

        content = article.get("content_clean") or article.get("content") or ""
        # Garantir string — banco pode retornar None mesmo com OR acima
        if content is None or str(content).strip().lower() in ("none", "null", ""):
            content = ""
        texto_puro = clean(content)

        # Se o texto real for muito curto, tenta baixar a matéria completa
        if len(texto_puro) < 800 and article.get("url"):
            raw_html, fetched_text = fetch_article_content(article["url"])
            if raw_html and len(clean(raw_html)) > len(texto_puro):
                content = raw_html or ""
                texto_puro = clean(raw_html)

        # Marca/desmarca content_partial com base no conteúdo real obtido agora
        is_partial = not _is_meaningful(texto_puro)
        if is_partial != bool(article.get("content_partial")):
            from core.database import get_connection
            conn = get_connection()
            conn.execute("UPDATE articles SET content_partial=? WHERE id=?",
                         (1 if is_partial else 0, article["id"]))
            conn.commit(); conn.close()
            article["content_partial"] = 1 if is_partial else 0

        if not content:
            content = article.get("summary", "Conteúdo não disponível.")

        # Animação: flip de página
        self._flip_in(lambda: self.reader.setHtml(self._build_html(article, content)))
        self._update_analysis(article)

        # Pontos de Vista automático quando conteúdo parcial
        if is_partial:
            self._show_pov_inline(article)

    def _archive_article(self):
        if not self.current_article:
            return
        from .archive_view import ArchiveDialog
        from core.database import get_archive_tags, save_to_archive
        tags = get_archive_tags()
        dlg = ArchiveDialog(self.current_article, tags, self.night_mode, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_tags, note = dlg.get_data()
            if new_tags:
                save_to_archive(self.current_article["id"], new_tags, note)
                self.archive_btn.setText("✓ Arquivado")
                QTimer.singleShot(2000, lambda: self.archive_btn.setText("📁 Arquivar"))

    def _show_pov_inline(self, article: dict):
        """Carrega Pontos de Vista inline quando o conteúdo é parcial."""
        from core.fetcher import find_similar_articles

        self.pov_inline_list.clear()

        try:
            pub_str = article.get("published_at", "")[:19].replace("Z", "")
            pub_dt  = datetime.fromisoformat(pub_str)
        except Exception:
            pub_dt  = datetime.now()

        date_from = (pub_dt - timedelta(days=5)).isoformat()
        date_to   = (pub_dt + timedelta(days=5)).isoformat()
        all_arts  = get_articles(limit=1500, date_from=date_from, date_to=date_to)

        results = find_similar_articles(article, all_arts, min_score=0.12, max_results=10)

        # Completos primeiro, depois parciais (mesma pontuação relativa)
        results.sort(key=lambda x: (x[1].get("content_partial", 0), -x[0]))

        if not results:
            self.pov_inline_frame.hide()
            return

        for _, art in results[:10]:
            partial_flag = " [⊘ parcial]" if art.get("content_partial") else ""
            src   = clean(art.get("source_name", ""))
            title = clean(art.get("title", ""))
            item  = QListWidgetItem(f"{src}{partial_flag}  —  {title}")
            item.setData(Qt.ItemDataRole.UserRole, art)
            # Cor diferente para parciais
            if art.get("content_partial"):
                item.setForeground(QColor("#9a6030"))
            self.pov_inline_list.addItem(item)

        self.pov_inline_frame.show()

    def _on_pov_inline_click(self, item):
        art = item.data(Qt.ItemDataRole.UserRole)
        if art:
            self.load_article(art)

    def _show_pov(self):
        """Abre a janela de Pontos de Vista para a matéria atual."""
        if not self.current_article: return
        dlg = PointsOfViewDialog(self.current_article, self.night_mode, self)
        # Se o usuário clicar em uma matéria na janela, ela carrega direto no leitor!
        dlg.article_selected.connect(self.load_article) 
        dlg.exec()

    def _flip_in(self, callback):
        """Simula virada de página: fade out → callback → fade in."""
        eff = QGraphicsOpacityEffect(self.reader)
        self.reader.setGraphicsEffect(eff)
        a_out = QPropertyAnimation(eff, b"opacity")
        a_out.setDuration(100)
        a_out.setStartValue(1.0); a_out.setEndValue(0.0)
        a_out.setEasingCurve(QEasingCurve.Type.InQuad)
        def _do_in():
            callback()
            a_in = QPropertyAnimation(eff, b"opacity")
            a_in.setDuration(220)
            a_in.setStartValue(0.0); a_in.setEndValue(1.0)
            a_in.setEasingCurve(QEasingCurve.Type.OutCubic)
            a_in.start()
            self._anim_in = a_in
        a_out.finished.connect(_do_in)
        a_out.start()
        self._anim_out = a_out

    def _build_html(self, article, content):
        night  = self.night_mode
        bg     = "#04000a" if night else "#faf5e8"
        fg     = "#e0d0ff" if night else "#2a1a08"
        acc    = "#9944ff" if night else "#8b6914"
        link   = "#cc88ff" if night else "#6a4a10"
        bq_bg  = "#0d0020" if night else "#f5edd8"
        font   = "'IM Fell English', Georgia, serif"

        pub = ""
        if article.get("published_at"):
            try:
                dt = datetime.fromisoformat(article["published_at"].replace("Z","+00:00"))
                # Converte UTC → horário local
                if dt.tzinfo is not None:
                    import time as _time
                    from datetime import timezone, timedelta
                    local_offset = timedelta(seconds=-_time.timezone)
                    dt = dt.astimezone(timezone(local_offset))
                pub = dt.strftime("%d de %B de %Y · %H:%M")
            except Exception:
                pub = article["published_at"][:16]

        title  = clean(article.get("title",""))
        source = clean(article.get("source_name",""))
        author = clean(article.get("author",""))
        url    = article.get("url","")

        # Normaliza conteúdo → parágrafos HTML legíveis
        content = _normalize_content(content or "")

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* {{ box-sizing:border-box; }}
body {{ background:{bg}; color:{fg}; font-family:{font}; font-size:16px; line-height:1.9; max-width:820px; margin:0 auto; padding:28px 44px 40px 36px; }}

/* Título do artigo */
h1.article-title {{ font-size:28px; font-weight:normal; font-style:italic; border-bottom:2px solid {acc}; padding-bottom:14px; margin-bottom:10px; line-height:1.3; }}

/* Metadados */
.meta {{ font-family:'Special Elite','Courier New',monospace; font-size:11px; color:{acc}; margin-bottom:28px; letter-spacing:.5px; }}
.meta a {{ color:{link}; text-decoration:none; }}

/* Headings dentro do artigo — estilo jornal */
h1 {{ font-size:22px; font-weight:normal; font-style:italic; color:{acc}; margin:28px 0 12px; border-bottom:1px solid {acc}; padding-bottom:6px; }}
h2 {{ font-size:19px; font-weight:normal; font-style:italic; color:{acc}; margin:24px 0 10px; }}
h3 {{ font-size:16px; font-weight:bold; font-style:normal; color:{acc}; margin:20px 0 8px; text-transform:uppercase; letter-spacing:.8px; }}
h4 {{ font-size:14px; font-weight:bold; color:{acc}; margin:16px 0 6px; }}

/* Parágrafos */
p {{ margin:0 0 20px 0; text-align:justify; }}

/* Blockquote — estilo recorte de jornal */
blockquote {{
    border-left:4px solid {acc};
    background:{bq_bg};
    margin:22px 0 22px 0;
    padding:12px 20px;
    font-style:italic;
    border-radius:0 2px 2px 0;
    color:{acc};
    font-size:15px;
}}

/* Listas */
ul,ol {{ margin:0 0 20px 0; padding-left:26px; }}
li {{ margin-bottom:8px; }}

/* Links */
a {{ color:{link}; }}

/* Separador */
hr {{ border:none; border-top:1px dashed {acc}; margin:28px 0; opacity:.5; }}

/* Imagens */
img {{ max-width:100%; height:auto; border:1px solid {acc}; margin:12px 0; display:block; }}

/* Bold / italic dentro do corpo */
b,strong {{ color:{acc}; font-weight:bold; }}
</style></head><body>
<h1 class="article-title">{title}</h1>
<div class="meta">
{source}{f' · {author}' if author else ''}{f' · {pub}' if pub else ''}
{f' · <a href="{url}">Abrir no navegador ↗</a>' if url else ''}
</div>
{content}
</body></html>"""

    def _update_analysis(self, article):
        # Análise está presente só se ao menos o resumo OU o tom emocional existirem
        # (campos numéricos como economic_axis=0.0 podem ser o padrão do banco, não resultado real)
        has_analysis = bool(
            article.get("ai_summary") or
            article.get("emotional_tone") or
            article.get("ai_category")
        )
        if has_analysis:
            ea = article.get("economic_axis", 0) or 0
            aa = article.get("authority_axis", 0) or 0
            eco_map = [(-1,-.5,"◀◀ Esq.Eco"),  (-.5,-.2,"◀ Centro-Esq"),
                       (-.2,.2,"● Centro"),      (.2,.5,"▶ Centro-Dir"),
                       (.5,1,"▶▶ Dir.Eco")]
            eco_txt = "● Centro"
            for lo,hi,txt in eco_map:
                if lo <= ea < hi: eco_txt = txt
            auth_txt = ("↑ Autoritária" if aa > 0.3 else "↓ Libertária" if aa < -0.3 else "— Moderada")
            self.bias_lbl.setText(f"{eco_txt}  {auth_txt}")
            tone = article.get("emotional_tone")
            if tone: self.tone_lbl.setText(f"Tom: {tone}")
            cb = article.get("clickbait_score")
            if cb is not None: self.cb_lbl.setText(f"Clickbait: {cb:.0%}")
            self.analysis_panel.show()
            self.analysis_pending.hide()
            self.analysis_progress.hide()
            self.analysis_fail_lbl.hide()
            self.analysis_retry_btn.hide()

            # 5Ws e implicações
            import json
            ws = {}
            if article.get("ai_5ws"):
                try: ws = json.loads(article["ai_5ws"])
                except Exception: pass
            summary = clean(article.get("ai_summary",""))
            if summary:
                self.summary_lbl.setText(summary)
                self.summary_frame.show()
            impl = clean(article.get("ai_implications",""))
            if impl:
                self.implications_lbl.setText(f"Implicações: {impl}")
        else:
            self.analysis_panel.show()
            self.analysis_pending.show()
            self.analysis_progress.setRange(0, 60000)
            self.analysis_progress.setValue(0)
            self.analysis_progress.show()
            self.analysis_fail_lbl.hide()
            self.analysis_retry_btn.hide()
            self.bias_lbl.setText("")
            self.tone_lbl.setText("")
            self.cb_lbl.setText("")

    def _on_translate(self, _):
        lang = self.lang_combo.currentData()
        if not lang or not self.current_article: return

        # Trava o botão e avisa que está traduzindo
        self.lang_combo.setEnabled(False)
        idx = self.lang_combo.currentIndex()
        self.lang_combo.setItemText(idx, "Traduzindo ⏳...")

        # Inicia a tradução em segundo plano
        self._trans_worker = TranslationWorker(self.current_article, lang)
        self._trans_worker.finished_translation.connect(self._on_translation_done)
        self._trans_worker.start()

    def _on_translation_done(self, result):
        # Destrava o botão e restaura o nome original
        self.lang_combo.setEnabled(True)
        langs = get_supported_languages()
        lang_code = result.get("target_language")
        idx = self.lang_combo.findData(lang_code)
        if idx >= 0:
            self.lang_combo.setItemText(idx, langs.get(lang_code, lang_code))

        # Erro de tradução — mostra mensagem
        if result.get("error"):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Tradução indisponível",
                f"Não foi possível traduzir o artigo.\n\n{result['error']}\n\n"
                "Instale o módulo para usar o Google Translate:\n"
                "  pip install deep-translator")
            return

        # Aplica o texto traduzido na tela
        if result.get("content_translated"):
            art = dict(self.current_article)
            if result.get("title_translated"): art["title"] = result["title_translated"]
            via = " (via Ollama)" if result.get("via_ollama") else ""
            art["source_name"] = (art.get("source_name") or "") + f" — traduzido{via}"
            self.reader.setHtml(self._build_html(art, result["content_translated"]))
        elif result.get("title_translated"):
            # Só título foi traduzido (conteúdo muito curto ou erro parcial)
            art = dict(self.current_article)
            art["title"] = result["title_translated"]
            self.reader.setHtml(self._build_html(art,
                self.current_article.get("content_clean") or
                self.current_article.get("content", "")))

    def _toggle_fav(self):
        if self.current_article:
            is_fav = toggle_favorite(self.current_article["id"])
            self.fav_btn.setText("★" if is_fav else "☆")

    def set_night_mode(self, night: bool):
        self.night_mode = night
        self._update_margin_style()
        self._apply_modal_style()
        self.update()
        if self.current_article:
            content = self.current_article.get("content_clean") or self.current_article.get("summary","")
            self.reader.setHtml(self._build_html(self.current_article, content))