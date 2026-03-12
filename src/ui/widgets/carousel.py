"""
Cronos - TrendingCarousel
Carrossel de notícias trending. Animação de slide (papel sendo puxado).
Auto-avança a cada 5s. Indicador de pontos.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, pyqtSignal, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QLinearGradient
from .article_card import clean

class TrendingSlide(QWidget):
    clicked = pyqtSignal(dict)

    def __init__(self, cluster: dict, night_mode=False, parent=None):
        super().__init__(parent)
        self.cluster  = cluster
        self.night_mode = night_mode
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(96)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(4)

        # Label TRENDING
        trend_lbl = QLabel("🔥  TRENDING")
        trend_lbl.setObjectName("stampLabel")
        layout.addWidget(trend_lbl)

        label = clean(self.cluster.get("label", "Assunto em destaque"))
        title_lbl = QLabel(label)
        title_lbl.setWordWrap(True)
        font = QFont("IM Fell English", 15)
        font.setItalic(True)
        title_lbl.setFont(font)
        layout.addWidget(title_lbl)

        # Fontes cobrindo
        sc = self.cluster.get("source_count", 0)
        kws = self.cluster.get("keywords", [])[:4]
        info = f"Coberto por {sc} fonte{'s' if sc>1 else ''}"
        if kws:
            info += "  ·  " + "  ".join(f"#{k}" for k in kws)
        info_lbl = QLabel(info)
        info_lbl.setObjectName("statusLabel")
        layout.addWidget(info_lbl)

    def mousePressEvent(self, event):
        arts = self.cluster.get("articles", [])
        if arts:
            self.clicked.emit(arts[0])
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hovered = True; self.update(); super().enterEvent(event)
    def leaveEvent(self, event):
        self._hovered = False; self.update(); super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self.night_mode:
            bg = QColor("#120025") if not self._hovered else QColor("#1a0035")
            border = QColor("#6600dd")
        else:
            bg = QColor("#ede0b8") if not self._hovered else QColor("#e8d8a8")
            border = QColor("#c4a265")
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 12, 12)
        p.fillPath(path, QBrush(bg))
        p.setPen(QPen(border, 1.5))
        p.drawPath(path)
        # Linha de margem vermelha
        mc = QColor(180,0,60,180) if self.night_mode else QColor(192,57,43,180)
        p.setPen(QPen(mc, 2.5))
        p.drawLine(14, 8, 14, h-8)


class TrendingCarousel(QWidget):
    article_opened = pyqtSignal(dict)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._slides    = []
        self._current   = 0
        self._animating = False
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_next)
        self._timer.start(5000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(12, 6, 12, 0)
        title = QLabel("Em destaque")
        font = QFont("IM Fell English", 13)
        font.setItalic(True)
        title.setFont(font)
        hdr.addWidget(title)
        hdr.addStretch()

        self._prev_btn = QPushButton("◀")
        self._next_btn = QPushButton("▶")
        for btn in [self._prev_btn, self._next_btn]:
            btn.setFixedSize(28, 28)
            btn.setStyleSheet("border:none;background:transparent;font-size:13px;")
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        hdr.addWidget(self._prev_btn)
        hdr.addWidget(self._next_btn)
        layout.addLayout(hdr)

        # Stack de slides
        self._stack = QStackedWidget()
        self._stack.setFixedHeight(100)
        layout.addWidget(self._stack)

        # Dots
        self._dots_row = QHBoxLayout()
        self._dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots_row.setSpacing(6)
        layout.addLayout(self._dots_row)

        # Placeholder
        self._placeholder = QLabel("Carregando notícias em destaque…")
        self._placeholder.setObjectName("statusLabel")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder._is_placeholder = True
        self._stack.addWidget(self._placeholder)

    def _make_placeholder(self):
        from PyQt6.QtWidgets import QLabel
        ph = QLabel("Carregando notícias em destaque…")
        ph.setObjectName("statusLabel")
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return ph

    def set_data(self, clusters: list, articles_by_id: dict = None):
        # Limpa todos os widgets do stack com segurança
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            # Não deletar o placeholder antigo aqui — só widgets reais
            if not getattr(w, "_is_placeholder", False):
                w.deleteLater()
            else:
                w.setParent(None)   # desanexa sem deletar
        for i in reversed(range(self._dots_row.count())):
            item = self._dots_row.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
        self._slides = []

        if not clusters:
            ph = self._make_placeholder()
            ph._is_placeholder = True
            self._stack.addWidget(ph)
            return

        for cl in clusters:
            slide = TrendingSlide(cl, self.night_mode)
            slide.clicked.connect(self.article_opened)
            self._stack.addWidget(slide)
            self._slides.append(slide)
            # Dot
            dot = QLabel("●" if len(self._slides) == 1 else "·")
            dot.setObjectName("statusLabel")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dots_row.addWidget(dot)

        self._current = 0
        self._update_dots()

    def _go_next(self):
        if len(self._slides) < 2 or self._animating: return
        self._slide_to((self._current + 1) % len(self._slides), direction=1)

    def _go_prev(self):
        if len(self._slides) < 2 or self._animating: return
        self._slide_to((self._current - 1) % len(self._slides), direction=-1)

    def _auto_next(self):
        if len(self._slides) >= 2:
            self._go_next()

    def _slide_to(self, idx, direction=1):
        if idx == self._current: return
        self._animating = True
        old_w = self._stack.currentWidget()
        new_w = self._stack.widget(idx)
        w = self._stack.width()

        # Animação de slide (papel sendo puxado)
        eff_out = QGraphicsOpacityEffect(old_w)
        eff_in  = QGraphicsOpacityEffect(new_w)
        old_w.setGraphicsEffect(eff_out)
        new_w.setGraphicsEffect(eff_in)

        anim_out = QPropertyAnimation(eff_out, b"opacity")
        anim_out.setDuration(220)
        anim_out.setStartValue(1.0); anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.Type.OutQuad)

        anim_in = QPropertyAnimation(eff_in, b"opacity")
        anim_in.setDuration(220)
        anim_in.setStartValue(0.0); anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.Type.InQuad)

        self._current = idx
        self._stack.setCurrentIndex(idx)
        self._update_dots()

        group = QParallelAnimationGroup()
        group.addAnimation(anim_out)
        group.addAnimation(anim_in)
        group.finished.connect(lambda: setattr(self, '_animating', False))
        group.start()
        self._anim_group = group

    def _update_dots(self):
        for i in range(self._dots_row.count()):
            item = self._dots_row.itemAt(i)
            if item and item.widget():
                item.widget().setText("●" if i == self._current else "·")

    def set_night_mode(self, v):
        self.night_mode = v
        for s in self._slides:
            s.night_mode = v
            s.update()
