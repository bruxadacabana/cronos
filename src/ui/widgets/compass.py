"""
Cronos - PoliticalCompassWidget
Gráfico de bússola política 2D interativo com Zoom e Pan.
"""
import math
from PyQt6.QtWidgets import QWidget, QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont

QUADRANT_COLORS_DAY = {
    "tl": QColor(255, 235, 235),  # Auth Left
    "tr": QColor(235, 240, 255),  # Auth Right
    "bl": QColor(235, 250, 235),  # Lib Left
    "br": QColor(255, 250, 235),  # Lib Right
}
QUADRANT_COLORS_NIGHT = {
    "tl": QColor(60, 20, 20),
    "tr": QColor(20, 30, 60),
    "bl": QColor(20, 50, 20),
    "br": QColor(60, 50, 20),
}


class PoliticalCompassWidget(QWidget):
    source_clicked = pyqtSignal(int, str)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self.sources = []
        self._dot_map = []  
        self.setMinimumHeight(300)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hovered_source = None
        
        # Sistema de Câmara (Zoom e Pan)
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._is_panning = False
        self._last_mouse_pos = None

    def set_data(self, sources: list):
        self.sources = sources
        self._dot_map = []
        self.update()

    def set_night_mode(self, v):
        self.night_mode = v
        self.update()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self._zoom *= 1.15
        else:
            self._zoom /= 1.15
        self._zoom = max(0.4, min(self._zoom, 8.0))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            mx, my = event.position().x(), event.position().y()
            clicked_on_dot = False
            for (cx, cy, s) in self._dot_map:
                if math.hypot(mx - cx, my - cy) < 14:
                    self.source_clicked.emit(s["id"], s["name"])
                    clicked_on_dot = True
                    break
            
            # Se não clicou em nenhum ponto, inicia o arrasto da tela
            if not clicked_on_dot:
                self._is_panning = True
                self._last_mouse_pos = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Lógica de arrastar a tela (Pan)
        if self._is_panning and self._last_mouse_pos is not None:
            delta = event.position() - self._last_mouse_pos
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
            return

        # Lógica de Hover nos pontos
        mx, my = event.position().x(), event.position().y()
        found = None
        for (cx, cy, s) in self._dot_map:
            if math.hypot(mx - cx, my - cy) < 14:
                found = s
                break
        if found != self._hovered_source:
            self._hovered_source = found
            self.update()
            if found:
                ea = found.get("economic_axis", 0)
                aa = found.get("authority_axis", 0)
                q = self._quadrant_name(ea, aa)
                from PyQt6.QtWidgets import QToolTip
                QToolTip.showText(event.globalPosition().toPoint(),
                    f"{found['name']}\n{q}\nEconômico: {ea:+.2f}  Autoritário: {aa:+.2f}",
                    self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self._last_mouse_pos = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().mouseReleaseEvent(event)

    def _quadrant_name(self, ea, aa):
        if ea <= 0 and aa >= 0:  return "Esquerda Autoritária"
        if ea >= 0 and aa >= 0:  return "Direita Autoritária"
        if ea <= 0 and aa <= 0:  return "Esquerda Libertária"
        return "Direita Libertária"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        
        # Define a base de cálculo aplicando Zoom e Deslocamento
        mg = 55       
        base_w = w - mg * 2
        base_h = h - mg * 2
        area_w = base_w * self._zoom
        area_h = base_h * self._zoom
        ox = mg + base_w / 2 + self._pan_x
        oy = mg + base_h / 2 + self._pan_y

        fg  = QColor("#e8d8ff") if self.night_mode else QColor("#2a1a08")
        grid = QColor("#8855cc") if self.night_mode else QColor("#c4a265")
        axis = QColor("#aa66ff") if self.night_mode else QColor("#8b6914")
        qc   = QUADRANT_COLORS_NIGHT if self.night_mode else QUADRANT_COLORS_DAY

        qrects = {
            "tl": QRectF(ox - area_w/2, oy - area_h/2, area_w/2, area_h/2),
            "tr": QRectF(ox, oy - area_h/2, area_w/2, area_h/2),
            "bl": QRectF(ox - area_w/2, oy, area_w/2, area_h/2),
            "br": QRectF(ox, oy, area_w/2, area_h/2),
        }
        for key, rect in qrects.items():
            p.fillRect(rect, qc[key])

        p.setPen(QPen(grid, 0.5, Qt.PenStyle.DotLine))
        for i in range(1, 4):
            x = ox - area_w/2 + area_w * i / 4
            y = oy - area_h/2 + area_h * i / 4
            p.drawLine(QPointF(x, oy - area_h/2), QPointF(x, oy + area_h/2))
            p.drawLine(QPointF(ox - area_w/2, y), QPointF(ox + area_w/2, y))

        p.setPen(QPen(axis, 2.0))
        p.drawLine(QPointF(ox - area_w/2, oy), QPointF(ox + area_w/2, oy))   
        p.drawLine(QPointF(ox, oy - area_h/2), QPointF(ox, oy + area_h/2))   

        font_lbl = QFont("Special Elite", 9)
        p.setFont(font_lbl)
        p.setPen(QPen(fg))
        p.drawText(QPointF(ox - area_w/2, oy - area_h/2 - 8), "Autoritária")
        p.drawText(QPointF(ox - area_w/2, oy + area_h/2 + 18), "Libertária")
        p.drawText(QPointF(ox - area_w/2 - 10, oy + 5), "Esq.")
        p.drawText(QPointF(ox + area_w/2 + 4, oy + 5), "Dir.")

        font_q = QFont("IM Fell English", 9)
        font_q.setItalic(True)
        p.setFont(font_q)
        p.setPen(QPen(fg, 1))
        p.setOpacity(0.6)
        p.drawText(QPointF(ox - area_w/2 + 6, oy - area_h/2 + 18), "Esq. Autoritária")
        p.drawText(QPointF(ox + 6, oy - area_h/2 + 18), "Dir. Autoritária")
        p.drawText(QPointF(ox - area_w/2 + 6, oy + area_h/2 - 6), "Esq. Libertária")
        p.drawText(QPointF(ox + 6, oy + area_h/2 - 6), "Dir. Libertária")
        p.setOpacity(1.0)

        self._dot_map = []
        font_src = QFont("Special Elite", 8)
        p.setFont(font_src)

        # Calcula posições base
        base_positions = []
        for s in self.sources:
            ea = s.get("economic_axis") or 0.0
            aa = s.get("authority_axis") or 0.0
            cx = ox + ea * (area_w / 2)
            cy = oy - aa * (area_h / 2)
            base_positions.append([cx, cy, s])

        # Repulsão: se hover perto de um cluster, espalha os pontos sobrepostos
        REPULSE_RADIUS = 16  # px — distância mínima entre centros
        SPREAD_DIST    = 28  # px — quanto afastar ao detectar sobreposição

        display_positions = [list(bp) for bp in base_positions]

        if self._hovered_source:
            # Encontra o ponto hovered
            hov_idx = next(
                (i for i, bp in enumerate(base_positions)
                 if bp[2].get("id") == self._hovered_source.get("id")), None
            )
            if hov_idx is not None:
                hx, hy = display_positions[hov_idx][0], display_positions[hov_idx][1]
                # Detecta vizinhos sobrepostos
                cluster = [i for i, bp in enumerate(display_positions)
                           if i != hov_idx and math.hypot(bp[0]-hx, bp[1]-hy) < REPULSE_RADIUS * 2]
                if cluster:
                    # Repele em círculo ao redor do hovered
                    n = len(cluster)
                    for k, idx in enumerate(cluster):
                        angle = (2 * math.pi * k / n) + math.pi / 4
                        display_positions[idx][0] = hx + math.cos(angle) * SPREAD_DIST * 1.8
                        display_positions[idx][1] = hy + math.sin(angle) * SPREAD_DIST * 1.8

        for i, (cx, cy, s) in enumerate(display_positions):
            self._dot_map.append((cx, cy, s))
            is_hov = (self._hovered_source and self._hovered_source.get("id") == s.get("id"))

            ea = s.get("economic_axis") or 0.0
            aa = s.get("authority_axis") or 0.0
            if ea <= 0 and aa >= 0:   dot_c = QColor(220, 80, 80)
            elif ea >= 0 and aa >= 0: dot_c = QColor(60, 120, 220)
            elif ea <= 0 and aa <= 0: dot_c = QColor(60, 160, 60)
            else:                      dot_c = QColor(200, 180, 30)

            if self.night_mode:
                dot_c = dot_c.lighter(130)

            # Linha de conexão da posição repelida à posição original
            if (cx, cy) != (base_positions[i][0], base_positions[i][1]):
                p.setPen(QPen(dot_c.darker(140), 0.8, Qt.PenStyle.DotLine))
                p.drawLine(QPointF(base_positions[i][0], base_positions[i][1]),
                           QPointF(cx, cy))

            if is_hov:
                halo = QColor(dot_c); halo.setAlpha(60)
                p.setBrush(QBrush(halo)); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), 18, 18)

            p.setBrush(QBrush(dot_c))
            if is_hov:
                p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
            else:
                p.setPen(Qt.PenStyle.NoPen)

            radius = 9 if is_hov else 7
            p.drawEllipse(QPointF(cx, cy), radius, radius)

            name = s.get("name", "")[:14]
            p.setPen(QPen(fg))
            p.setOpacity(0.9 if is_hov else 0.75)
            lx = cx + 10 if cx < ox else cx - p.fontMetrics().horizontalAdvance(name) - 6
            ly = cy - 8 if cy > oy else cy + 16
            p.drawText(QPointF(lx, ly), name)
            p.setOpacity(1.0)


class PoliticalCompassDialog(QDialog):
    source_clicked = pyqtSignal(int, str)

    def __init__(self, sources, night_mode=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bússola Política Expandida")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        
        hint = QLabel("Utilize a roda do rato para fazer Zoom. Clique e arraste para mover o gráfico.")
        layout.addWidget(hint)

        self.compass = PoliticalCompassWidget(night_mode)
        self.compass.set_data(sources)
        self.compass.source_clicked.connect(self._on_click)
        layout.addWidget(self.compass, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def _on_click(self, sid, name):
        self.source_clicked.emit(sid, name)
        self.accept()