"""
Cronos — Sidebar Corrigida
Sincronizada com MainWindow v1.2
"""
import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QFrame, QSizePolicy, QPushButton
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QPoint
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QFontMetrics, QPainterPath
)

W_COLLAPSED = 56
W_EXPANDED  = 210

NAV_ITEMS = [
    ("feed",       "📰",  "Feed"),
    ("trending",   "🔥",  "Trending"),
    ("sources",    "📡",  "Fontes"),
    ("social",     "🌐",  "Redes Sociais"),
    ("dashboard",  "📊",  "Dashboard"),
    ("archive",    "🗂",   "Arquivo"),
    ("settings",   "⚙",   "Configurações"),
]


class _LogoWidget(QWidget):
    """Logotipo fixo com estrelas a lápis. Nunca colapsa."""
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.setFixedHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        import random; random.seed(7)
        # (x_frac, y_frac, size, rotation_deg)
        self._stars = [
            (random.uniform(0.04, 0.96), random.uniform(0.07, 0.90),
             random.uniform(4, 11), random.uniform(0, 360))
            for _ in range(12)
        ]

    def set_night(self, v):
        self.night = v
        self.update()

    def _draw_star(self, p, cx, cy, size, rot_deg):
        rot = math.radians(rot_deg - 90)
        outer, inner = size, size * 0.42
        path = QPainterPath()
        for i in range(10):
            r = outer if i % 2 == 0 else inner
            a = rot + math.pi * i / 5
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            path.moveTo(cx, cy) if i == 0 else None
            if i == 0: path.moveTo(x, y)
            else:       path.lineTo(x, y)
        path.closeSubpath()
        if self.night:
            p.setPen(QPen(QColor(180, 100, 255, 150), 0.7))
            p.setBrush(QBrush(QColor(210, 150, 255, 55)))
        else:
            p.setPen(QPen(QColor(110, 70, 15, 110), 0.7))
            p.setBrush(QBrush(QColor(150, 110, 30, 45)))
        p.drawPath(path)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bg = QColor("#0a0018" if self.night else "#c0aa78")
        p.fillRect(0, 0, w, h, bg)
        for fx, fy, sz, rot in self._stars:
            self._draw_star(p, fx * w, fy * h, sz, rot)
        # texto
        font = QFont("IM Fell English", 17)
        font.setItalic(True)
        p.setFont(font)
        col = QColor("#cc88ff" if self.night else "#2e1806")
        p.setPen(QPen(col))
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance("CRONOS")
        p.drawText(QPoint((w - tw) // 2, h // 2 + fm.ascent() // 2 - 2), "CRONOS")
        # separador
        p.setPen(QPen(QColor("#9900ff44" if self.night else "#8b691444"), 1))
        p.drawLine(6, h - 1, w - 6, h - 1)


class _NavButton(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, key, icon, label, night=False, parent=None):
        super().__init__(parent)
        self.key, self.icon, self.label = key, icon, label
        self.night = night
        self.active = False
        self._expanded = False
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_active(self, v):  self.active = v;     self.update()
    def set_night(self, v):   self.night = v;      self.update()
    def set_expanded(self, v):self._expanded = v;  self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self.active:
            p.fillRect(0, 0, w, h,
                QColor("#33007755") if self.night else QColor("#b8903833"))
            p.fillRect(0, 6, 3, h - 12,
                QColor("#9900ff") if self.night else QColor("#8b6914"))
        # ícone sempre centrado dentro de W_COLLAPSED
        p.setFont(QFont("Segoe UI Emoji", 15))
        p.setPen(QPen(QColor("#cc88ff" if self.night else "#3a2008")))
        from PyQt6.QtCore import QRect
        p.drawText(QRect(0, 0, W_COLLAPSED, h),
                   Qt.AlignmentFlag.AlignCenter, self.icon)
        # label só quando expandido
        if self._expanded:
            p.setFont(QFont("Special Elite", 10))
            p.setPen(QPen(QColor("#e0d0ff" if self.night else "#2a1a08")))
            from PyQt6.QtCore import QRect
            p.drawText(QRect(W_COLLAPSED + 4, 0, w - W_COLLAPSED - 8, h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self.label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class _OllamaDot(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night, self.online = night, False
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._expanded = False
        t = QTimer(self); t.timeout.connect(self._check); t.start(15000)
        QTimer.singleShot(2000, self._check)

    def set_night(self, v): self.night = v; self.update()
    def set_expanded(self, v): self._expanded = v; self.update()

    def _check(self):
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            ok = True
        except Exception:
            ok = False
        if ok != self.online:
            self.online = ok; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        dot = QColor("#44dd44" if self.online else "#dd4444")
        cx, cy = W_COLLAPSED // 2, h // 2
        halo = QColor(dot); halo.setAlpha(40)
        p.setBrush(QBrush(halo)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPoint(cx, cy), 9, 9)
        p.setBrush(QBrush(dot)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPoint(cx, cy), 5, 5)
        if self._expanded:
            p.setFont(QFont("Special Elite", 9))
            p.setPen(QPen(QColor("#e0d0ff" if self.night else "#2a1a08")))
            p.drawText(W_COLLAPSED + 4, cy + 4,
                       "IA online" if self.online else "IA offline")


class Sidebar(QWidget):
    # Sinal renomeado de nav_changed para navigate para alinhar com main_window.py
    navigate = pyqtSignal(str) 

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._expanded = False
        self.setMinimumWidth(W_COLLAPSED)
        self.setMaximumWidth(W_COLLAPSED)
        self.setMouseTracking(True)
        self._build()

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._do_expand)

        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._do_collapse)

        self._anim_min = QPropertyAnimation(self, b"minimumWidth")
        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        for a in (self._anim_min, self._anim_max):
            a.setDuration(170)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo — separado visualmente, nunca colapsa
        self._logo = _LogoWidget(self.night_mode)
        layout.addWidget(self._logo)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setObjectName("sidebarDivider")
        layout.addWidget(div)

        # Navegação
        self._buttons: dict[str, _NavButton] = {}
        for key, icon, label in NAV_ITEMS:
            btn = _NavButton(key, icon, label, self.night_mode)
            btn.clicked.connect(self._on_nav)
            layout.addWidget(btn)
            self._buttons[key] = btn

        layout.addStretch()

        # Adição do botão de refresh esperado pela MainWindow na linha 70
        self.refresh_btn = QPushButton("🔄") 
        self.refresh_btn.setFlat(True) 
        self.refresh_btn.setFixedSize(W_COLLAPSED, 40) 
        self.refresh_btn.setStyleSheet("color: #cc88ff; border: none; font-size: 16px;") 
        layout.addWidget(self.refresh_btn) 

        # Status Ollama
        self._dot = _OllamaDot(self.night_mode)
        layout.addWidget(self._dot)

        self._set_active("feed")

    # Método para retornar o botão de atualização solicitado pela MainWindow
    def get_refresh_btn(self): 
        return self.refresh_btn

    # Método para atualizar o status da IA via timer da MainWindow (linha 307)
    def set_ollama_status(self, online, model_name): 
        self._dot.online = online
        self._dot.update()

    def _on_nav(self, key):
        self._set_active(key)
        self.navigate.emit(key) # Emite o sinal renomeado

    def _set_active(self, key):
        for k, btn in self._buttons.items():
            btn.set_active(k == key)

    def set_active(self, key):
        self._set_active(key)

    def enterEvent(self, event):
        self._leave_timer.stop()
        self._hover_timer.start(70)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._leave_timer.start(130)
        super().leaveEvent(event)

    def _do_expand(self):
        if self._expanded: return
        self._expanded = True
        for btn in self._buttons.values():
            btn.set_expanded(True)
        self._dot.set_expanded(True)
        self._animate(W_EXPANDED)

    def _do_collapse(self):
        if not self._expanded: return
        self._expanded = False
        for btn in self._buttons.values():
            btn.set_expanded(False)
        self._dot.set_expanded(False)
        self._animate(W_COLLAPSED)

    def _animate(self, target):
        cur = self.width()
        for a in (self._anim_min, self._anim_max):
            a.stop()
            a.setStartValue(cur)
            a.setEndValue(target)
            a.start()

    def set_night_mode(self, v):
        self.night_mode = v
        self._logo.set_night(v)
        self._dot.set_night(v)
        for btn in self._buttons.values():
            btn.set_night(v)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h,
            QColor("#0a0018" if self.night_mode else "#c0aa78"))
        p.setPen(QPen(
            QColor("#9900ff33" if self.night_mode else "#8b691433"), 1))
        p.drawLine(w - 1, 0, w - 1, h)
