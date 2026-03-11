"""
Cronos - Widgets extras para o Dashboard v1.3
Nuvem de palavras, linha do tempo emocional, radar de temas,
termômetro de polarização, ranking de fontes, índice de diversidade.
"""
import math, re
import random
from collections import Counter
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QLinearGradient


# ── Nuvem de palavras ─────────────────────────────────────────────────────────

class WordCloudWidget(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.words = []  # list of (word, count)
        self.setMinimumHeight(160)
        random.seed(99)

    def set_data(self, words): self.words = words[:40]; self.update()
    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        if not self.words: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        max_c = max(c for _, c in self.words) or 1

        placed = []
        cx, cy = w // 2, h // 2
        colors_day   = ["#8b4513","#a05020","#6a3010","#c08030","#7a5828","#503010"]
        colors_night = ["#cc66ff","#9933ee","#ff44aa","#7700ee","#aa44ff","#dd22cc"]
        colors = colors_night if self.night else colors_day

        for i, (word, count) in enumerate(self.words):
            size = int(9 + (count / max_c) * 18)
            font = QFont("Special Elite", size)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(word)
            th = fm.height()
            col = QColor(colors[i % len(colors)])

            # Spiral placement
            placed_ok = False
            for attempt in range(300):
                angle = attempt * 0.4
                r = attempt * 1.8
                tx = int(cx + r * math.cos(angle) - tw / 2)
                ty = int(cy + r * math.sin(angle) + th / 2)
                rect = (tx, ty - th, tw, th)
                if not any(
                    abs(tx - px) < (tw + pw) // 2 + 4 and abs(ty - py) < (th + ph) // 2 + 4
                    for px, py, pw, ph in placed
                ):
                    placed.append((tx, ty, tw, th))
                    placed_ok = True
                    break

            if placed_ok:
                p.setFont(font)
                p.setPen(QPen(col))
                p.drawText(QPointF(tx, ty), word)


# ── Linha do tempo emocional por fonte ───────────────────────────────────────

TONE_COLORS = {
    "neutro":      "#888888",
    "positivo":    "#44aa44",
    "negativo":    "#cc4444",
    "alarmista":   "#ee8800",
    "esperançoso": "#44aadd",
    "indignado":   "#dd2266",
    "celebrativo": "#ddaa00",
}

class EmotionTimelineWidget(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.data = []   # list of {source, day, tone, count}
        self.setMinimumHeight(180)

    def set_data(self, data): self.data = data; self.update()
    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        if not self.data: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        fg = QColor("#e0d0ff" if self.night else "#2a1a08")
        mg = 40

        days = sorted(set(r.get("day","") for r in self.data))
        if len(days) < 2: return

        dx = (w - mg*2) / (len(days) - 1)
        tones_found = list({r.get("tone","") for r in self.data if r.get("tone")})

        p.setFont(QFont("Special Elite", 7))
        # Draw one line per tone
        for tone in tones_found:
            col = QColor(TONE_COLORS.get(tone, "#888888"))
            tone_data = {r["day"]: r["count"] for r in self.data if r.get("tone") == tone}
            pts = []
            for i, day in enumerate(days):
                val = tone_data.get(day, 0)
                x = mg + i * dx
                y = h - mg - val * 3
                pts.append(QPointF(x, max(mg, min(h - mg, y))))
            if len(pts) >= 2:
                p.setPen(QPen(col, 1.8))
                for i in range(len(pts)-1):
                    p.drawLine(pts[i], pts[i+1])

        # Legend
        lx = mg
        for tone in tones_found[:6]:
            col = QColor(TONE_COLORS.get(tone, "#888888"))
            p.setPen(QPen(col, 2)); p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(lx, h - 10), 4, 4)
            p.setPen(QPen(fg)); p.drawText(QPointF(lx + 7, h - 6), tone[:10])
            lx += 80

        # Date labels
        p.setPen(QPen(fg))
        for i, day in enumerate(days[::max(1, len(days)//5)]):
            x = mg + i * max(1, len(days)//5) * dx
            p.drawText(QPointF(x - 15, h - mg + 14), day[5:])  # MM-DD


# ── Radar de temas ────────────────────────────────────────────────────────────

class RadarWidget(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.data = []  # list of (label, value 0-1)
        self.setMinimumHeight(200)
        self.setMinimumWidth(200)

    def set_data(self, data): self.data = data[:8]; self.update()
    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        if len(self.data) < 3: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w//2, h//2
        r = min(w, h) // 2 - 30
        n = len(self.data)
        fg   = QColor("#e0d0ff" if self.night else "#2a1a08")
        grid = QColor("#4400aa55" if self.night else "#b8904055")
        fill = QColor("#7700ee80" if self.night else "#8b691440")
        line = QColor("#9900ff"   if self.night else "#8b6914")

        # Grid circles
        p.setPen(QPen(grid, 0.8))
        for level in [0.25, 0.5, 0.75, 1.0]:
            pts2 = []
            for i in range(n):
                a = math.radians(-90 + 360 * i / n)
                pts2.append(QPointF(cx + math.cos(a)*r*level, cy + math.sin(a)*r*level))
            for i in range(len(pts2)):
                p.drawLine(pts2[i], pts2[(i+1) % len(pts2)])
        # Spokes
        for i in range(n):
            a = math.radians(-90 + 360 * i / n)
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(a)*r, cy + math.sin(a)*r))

        # Data polygon
        data_pts = []
        for i, (label, val) in enumerate(self.data):
            a = math.radians(-90 + 360 * i / n)
            data_pts.append(QPointF(cx + math.cos(a)*r*val, cy + math.sin(a)*r*val))

        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(data_pts[0])
        for pt in data_pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        p.fillPath(path, QBrush(fill))
        p.setPen(QPen(line, 2))
        p.drawPath(path)

        # Dots + labels
        p.setFont(QFont("Special Elite", 8))
        p.setPen(QPen(fg))
        p.setBrush(QBrush(line))
        for i, (label, val) in enumerate(self.data):
            a = math.radians(-90 + 360 * i / n)
            x = cx + math.cos(a)*r*val
            y = cy + math.sin(a)*r*val
            p.drawEllipse(QPointF(x, y), 4, 4)
            # Label
            lx = cx + math.cos(a)*(r + 16)
            ly = cy + math.sin(a)*(r + 16)
            p.setPen(QPen(fg)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawText(QPointF(lx - 20, ly + 4), label[:12])


# ── Termômetro de polarização ─────────────────────────────────────────────────

class PolarizationThermometerWidget(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.value = 0.0   # -1 (esq) to +1 (dir)
        self.diversity = 0.0  # 0-1
        self.setMinimumHeight(100)

    def set_data(self, value, diversity):
        self.value = max(-1.0, min(1.0, value))
        self.diversity = max(0.0, min(1.0, diversity))
        self.update()

    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        fg = QColor("#e0d0ff" if self.night else "#2a1a08")
        mg = 30

        # Gradient bar: vermelho (esq) → cinza (centro) → azul (dir)
        grad = QLinearGradient(mg, 0, w-mg, 0)
        grad.setColorAt(0.0, QColor(200, 60, 60))
        grad.setColorAt(0.5, QColor(160, 140, 100) if not self.night else QColor(80, 60, 120))
        grad.setColorAt(1.0, QColor(60, 100, 200))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(mg, 30, w-mg*2, 24), 8, 8)

        # Indicator needle
        pos_x = mg + (self.value + 1) / 2 * (w - mg*2)
        p.setPen(QPen(QColor("#ffffff" if self.night else "#2a1a08"), 2))
        p.drawLine(QPointF(pos_x, 24), QPointF(pos_x, 58))
        # Diamond
        p.setBrush(QBrush(QColor("#ffdd00")))
        diamond = __import__("PyQt6.QtGui", fromlist=["QPainterPath"]).QPainterPath()
        diamond.moveTo(pos_x, 22)
        diamond.lineTo(pos_x+6, 30)
        diamond.lineTo(pos_x, 38)
        diamond.lineTo(pos_x-6, 30)
        diamond.closeSubpath()
        p.drawPath(diamond)

        # Labels
        p.setFont(QFont("Special Elite", 9))
        p.setPen(QPen(fg))
        p.drawText(QPointF(mg, 22), "◀ Esquerda")
        fw = QFontMetrics(p.font()).horizontalAdvance("Direita ▶")
        p.drawText(QPointF(w - mg - fw, 22), "Direita ▶")
        p.drawText(QPointF(w//2 - 15, 22), "Centro")

        # Diversity bar
        p.setFont(QFont("Special Elite", 8))
        p.setPen(QPen(fg))
        p.drawText(QPointF(mg, 82), f"Diversidade de fontes: {self.diversity:.0%}")
        div_col = QColor("#44cc44") if self.diversity > 0.6 else QColor("#cc8800") if self.diversity > 0.3 else QColor("#cc4444")
        p.setBrush(QBrush(div_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(mg, 86, (w-mg*2)*self.diversity, 8), 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor("#88888855")))
        p.drawRoundedRect(QRectF(mg, 86, w-mg*2, 8), 3, 3)


# ── Ranking de fontes ─────────────────────────────────────────────────────────

class SourceRankingWidget(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.data = []  # list of (name, count)
        self.setMinimumHeight(200)

    def set_data(self, data): self.data = data[:10]; self.update()
    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        if not self.data: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        fg  = QColor("#e0d0ff" if self.night else "#2a1a08")
        bar = QColor("#7b00ff" if self.night else "#8b6914")
        medal = ["🥇","🥈","🥉"]

        n = len(self.data)
        row_h = h // max(n, 1)
        max_v = max(v for _, v in self.data) or 1
        label_w = 130

        p.setFont(QFont("Special Elite", 9))
        for i, (name, val) in enumerate(self.data):
            y = i * row_h + 2
            ico = medal[i] if i < 3 else f"{i+1}."
            p.setPen(QPen(fg))
            p.drawText(QRectF(0, y, label_w - 4, row_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{ico} {name[:14]}")
            bw = int((val / max_v) * (w - label_w - 50))
            # Bar gradient
            g = QLinearGradient(label_w+4, 0, label_w+4+bw, 0)
            g.setColorAt(0, bar); g.setColorAt(1, bar.lighter(150))
            p.fillRect(QRectF(label_w+4, y+4, bw, row_h-10), QBrush(g))
            p.setPen(QPen(fg))
            p.drawText(QRectF(label_w+bw+10, y, 50, row_h), Qt.AlignmentFlag.AlignVCenter, str(val))
