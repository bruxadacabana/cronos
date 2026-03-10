"""
Cronos - StarWidget
Estrelas piscando estilo glitter/céu real.
Cada estrela tem timer próprio com fase e frequência únicos.
"""
import math, random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QRadialGradient

class StarWidget(QWidget):
    def __init__(self, count=12, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMinimumHeight(70)
        random.seed(42)
        self._stars = []
        for i in range(count):
            self._stars.append({
                "x": random.uniform(0.04, 0.96),
                "y": random.uniform(0.08, 0.92),
                "size": random.uniform(3.5, 11.0),
                "phase": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(0.6, 2.2),   # ciclos/s
                "type": random.choice(["point","star4","star5"]),
                "rot": random.uniform(-25, 25),
                "jit": [(random.uniform(-1.0,1.0), random.uniform(-1.0,1.0)) for _ in range(10)],
                "t": 0.0,
            })
        # Timer global: 40ms ≈ 25fps
        self._tick = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(40)

    def set_night_mode(self, v):
        self.night_mode = v
        self.update()

    def _update(self):
        self._tick += 0.040
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        for s in self._stars:
            brightness = 0.5 + 0.5 * math.sin(self._tick * s["speed"] * 2 * math.pi + s["phase"])
            x = s["x"] * w
            y = s["y"] * h
            sz = s["size"]
            if self.night_mode:
                col = QColor(210, 170, 255, int(40 + 215 * brightness))
                glow = QColor(180, 120, 255, int(15 + 60 * brightness))
            else:
                col = QColor(120, 85, 20, int(50 + 180 * brightness))
                glow = QColor(180, 130, 30, int(10 + 40 * brightness))

            # Halo de brilho
            if brightness > 0.6:
                grd = QRadialGradient(QPointF(x, y), sz * 2.2)
                grd.setColorAt(0, glow)
                grd.setColorAt(1, QColor(0,0,0,0))
                p.setBrush(QBrush(grd))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(x, y), sz * 2.2, sz * 2.2)

            pen = QPen(col)
            pen.setWidthF(1.1)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)

            p.save()
            p.translate(x, y)
            p.rotate(s["rot"])
            ji = s["jit"]
            t = s["type"]
            if t == "point":
                # Ponto brilhante com 4 raios curtos
                for angle in [0, 90, 180, 270]:
                    a = math.radians(angle)
                    p.drawLine(QPointF(0,0), QPointF(math.cos(a)*sz, math.sin(a)*sz))
                p.setBrush(QBrush(col))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0,0), sz*0.28, sz*0.28)
            elif t == "star4":
                # Estrela de 4 pontas estilo lápis
                for i in range(4):
                    a1 = math.radians(i * 90 - 45)
                    a2 = math.radians(i * 90 + 45)
                    x1, y1 = math.cos(a1)*sz, math.sin(a1)*sz
                    x2, y2 = math.cos(a2)*sz*0.35, math.sin(a2)*sz*0.35
                    jx, jy = ji[i % len(ji)]
                    p.drawLine(QPointF(x1,y1), QPointF(x2+jx*0.5, y2+jy*0.5))
            else:
                # Estrela de 5 pontas estilo lápis
                for i in range(5):
                    a1 = math.radians(i * 72 - 90)
                    a2 = math.radians(i * 72 - 90 + 36)
                    x1, y1 = math.cos(a1)*sz, math.sin(a1)*sz
                    x2, y2 = math.cos(a2)*sz*0.42, math.sin(a2)*sz*0.42
                    jx, jy = ji[i % len(ji)]
                    p.drawLine(QPointF(x1,y1), QPointF(x2+jx*0.6, y2+jy*0.6))
            p.restore()
