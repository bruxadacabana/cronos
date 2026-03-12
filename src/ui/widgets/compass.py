"""
Cronos - PoliticalCompassWidget
Bussola politica 2D interativa com Zoom e Pan.
Repulsao force-directed permanente — calculada em espaco normalizado [-1,1].
Nome da fonte visivel apenas ao hover (inline na tela).
Particulas pequenas por padrao; ficam visiveis ao zoom.
"""
import math
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QPushButton,
    QHBoxLayout, QLabel, QToolTip
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont

QUADRANT_COLORS_DAY = {
    "tl": QColor(255, 235, 235),
    "tr": QColor(235, 240, 255),
    "bl": QColor(235, 250, 235),
    "br": QColor(255, 250, 235),
}
QUADRANT_COLORS_NIGHT = {
    "tl": QColor(60, 20, 20),
    "tr": QColor(20, 30, 60),
    "bl": QColor(20, 50, 20),
    "br": QColor(60, 50, 20),
}

# Distancia minima em espaco normalizado [-1, 1]
# 0.08 equivale a ~8% do semi-eixo — evita sobreposicao sem espalhar demais
MIN_DIST_NORM = 0.08
ITERATIONS    = 80

# Raio das particulas em pixels (zoom=1)
RADIUS_DEFAULT = 4
RADIUS_HOVER   = 7


def _force_layout_norm(positions_norm, min_dist=MIN_DIST_NORM, iterations=ITERATIONS):
    """
    Force-directed em coordenadas normalizadas [-1, 1].
    'positions_norm' = lista de [ea, aa] originais.
    Retorna lista de [dea, daa] — offsets a somar.
    O cache e valido independente de zoom/pan.
    """
    n = len(positions_norm)
    offsets = [[0.0, 0.0] for _ in range(n)]

    for _ in range(iterations):
        for i in range(n):
            for j in range(i + 1, n):
                xi = positions_norm[i][0] + offsets[i][0]
                yi = positions_norm[i][1] + offsets[i][1]
                xj = positions_norm[j][0] + offsets[j][0]
                yj = positions_norm[j][1] + offsets[j][1]
                dx = xi - xj
                dy = yi - yj
                d  = math.hypot(dx, dy)
                if 0.0001 < d < min_dist:
                    push = (min_dist - d) / 2.0
                    nx, ny = dx / d, dy / d
                    offsets[i][0] += nx * push
                    offsets[i][1] += ny * push
                    offsets[j][0] -= nx * push
                    offsets[j][1] -= ny * push
    return offsets


class PoliticalCompassWidget(QWidget):
    source_clicked = pyqtSignal(int, str)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode  = night_mode
        self.sources     = []
        self._dot_map    = []
        # Cache: chave = n_sources, valor = offsets norm
        # Invalida apenas quando os dados mudam, nao ao zoom/pan
        self._offsets_cache = None
        self._offsets_n     = -1
        self.setMinimumHeight(300)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hovered_source = None

        self._zoom           = 1.0
        self._pan_x          = 0.0
        self._pan_y          = 0.0
        self._is_panning     = False
        self._last_mouse_pos = None

    def set_data(self, sources: list):
        self.sources        = sources
        self._offsets_cache = None   # invalida cache ao mudar dados
        self._offsets_n     = -1
        self._dot_map       = []
        self.update()

    def set_night_mode(self, v):
        self.night_mode = v
        self.update()

    # ── Eventos ──────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        self._zoom = max(0.3, min(self._zoom * factor, 12.0))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            mx, my = event.position().x(), event.position().y()
            for (cx, cy, s) in self._dot_map:
                if math.hypot(mx - cx, my - cy) < max(10, RADIUS_HOVER * self._zoom):
                    self.source_clicked.emit(s["id"], s["name"])
                    return
            self._is_panning     = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning and self._last_mouse_pos is not None:
            delta        = event.position() - self._last_mouse_pos
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
            return

        mx, my = event.position().x(), event.position().y()
        found  = None
        for (cx, cy, s) in self._dot_map:
            if math.hypot(mx - cx, my - cy) < max(10, RADIUS_HOVER * self._zoom):
                found = s
                break
        if found != self._hovered_source:
            self._hovered_source = found
            self.update()
        if found:
            ea = found.get("economic_axis", 0)
            aa = found.get("authority_axis", 0)
            q  = self._quadrant_name(ea, aa)
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{found['name']}\n{q}\nEconomico: {ea:+.2f}  Autoritario: {aa:+.2f}",
                self
            )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning     = False
            self._last_mouse_pos = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().mouseReleaseEvent(event)

    def _quadrant_name(self, ea, aa):
        if ea <= 0 and aa >= 0: return "Esquerda Autoritaria"
        if ea >= 0 and aa >= 0: return "Direita Autoritaria"
        if ea <= 0 and aa <= 0: return "Esquerda Libertaria"
        return "Direita Libertaria"

    # ── Pintura ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        mg     = 55
        base_w = w - mg * 2
        base_h = h - mg * 2
        area_w = base_w * self._zoom
        area_h = base_h * self._zoom
        ox     = mg + base_w / 2.0 + self._pan_x
        oy     = mg + base_h / 2.0 + self._pan_y

        fg   = QColor("#e8d8ff") if self.night_mode else QColor("#2a1a08")
        grid = QColor("#8855cc") if self.night_mode else QColor("#c4a265")
        axis = QColor("#aa66ff") if self.night_mode else QColor("#8b6914")
        qc   = QUADRANT_COLORS_NIGHT if self.night_mode else QUADRANT_COLORS_DAY

        # Quadrantes
        for key, rect in {
            "tl": QRectF(ox - area_w/2, oy - area_h/2, area_w/2, area_h/2),
            "tr": QRectF(ox,            oy - area_h/2, area_w/2, area_h/2),
            "bl": QRectF(ox - area_w/2, oy,            area_w/2, area_h/2),
            "br": QRectF(ox,            oy,            area_w/2, area_h/2),
        }.items():
            p.fillRect(rect, qc[key])

        # Grade pontilhada
        p.setPen(QPen(grid, 0.5, Qt.PenStyle.DotLine))
        for i in range(1, 4):
            x = ox - area_w/2 + area_w * i / 4
            y = oy - area_h/2 + area_h * i / 4
            p.drawLine(QPointF(x, oy - area_h/2), QPointF(x, oy + area_h/2))
            p.drawLine(QPointF(ox - area_w/2, y),  QPointF(ox + area_w/2, y))

        # Eixos
        p.setPen(QPen(axis, 2.0))
        p.drawLine(QPointF(ox - area_w/2, oy), QPointF(ox + area_w/2, oy))
        p.drawLine(QPointF(ox, oy - area_h/2), QPointF(ox, oy + area_h/2))

        # Rotulos
        p.setFont(QFont("Special Elite", 9))
        p.setPen(QPen(fg))
        p.drawText(QPointF(ox - area_w/2,      oy - area_h/2 - 8),  "Autoritaria")
        p.drawText(QPointF(ox - area_w/2,      oy + area_h/2 + 18), "Libertaria")
        p.drawText(QPointF(ox - area_w/2 - 10, oy + 5), "Esq.")
        p.drawText(QPointF(ox + area_w/2 + 4,  oy + 5), "Dir.")

        font_q = QFont("IM Fell English", 9)
        font_q.setItalic(True)
        p.setFont(font_q)
        p.setOpacity(0.55)
        p.drawText(QPointF(ox - area_w/2 + 6, oy - area_h/2 + 18), "Esq. Autoritaria")
        p.drawText(QPointF(ox + 6,            oy - area_h/2 + 18), "Dir. Autoritaria")
        p.drawText(QPointF(ox - area_w/2 + 6, oy + area_h/2 - 6),  "Esq. Libertaria")
        p.drawText(QPointF(ox + 6,            oy + area_h/2 - 6),  "Dir. Libertaria")
        p.setOpacity(1.0)

        if not self.sources:
            return

        # ── Offsets em espaco normalizado (cache estavel, independe de zoom/pan) ──
        n = len(self.sources)
        if self._offsets_cache is None or self._offsets_n != n:
            positions_norm = [
                [s.get("economic_axis") or 0.0,
                 s.get("authority_axis") or 0.0]
                for s in self.sources
            ]
            self._offsets_cache = _force_layout_norm(positions_norm)
            self._offsets_n     = n

        offsets = self._offsets_cache

        # ── Raio escalado com zoom (fica menor sem zoom) ──
        r_base  = RADIUS_DEFAULT * min(self._zoom, 2.0)
        r_hover = RADIUS_HOVER   * min(self._zoom, 2.0)

        self._dot_map = []
        p.setFont(QFont("Special Elite", 8))

        for i, s in enumerate(self.sources):
            # Posicao base (normalizada) + offset da repulsao
            ea_raw = s.get("economic_axis") or 0.0
            aa_raw = s.get("authority_axis") or 0.0
            ea = ea_raw + offsets[i][0]
            aa = aa_raw + offsets[i][1]

            # Converte para pixels
            cx = ox + ea * (area_w / 2.0)
            cy = oy - aa * (area_h / 2.0)
            # Posicao original (sem offset) para linha de conexao
            bx = ox + ea_raw * (area_w / 2.0)
            by = oy - aa_raw * (area_h / 2.0)

            self._dot_map.append((cx, cy, s))
            is_hov = bool(
                self._hovered_source
                and self._hovered_source.get("id") == s.get("id")
            )

            # Cor por quadrante (usa posicao original)
            if   ea_raw <= 0 and aa_raw >= 0: dot_c = QColor(220, 80,  80)
            elif ea_raw >= 0 and aa_raw >= 0: dot_c = QColor(60,  120, 220)
            elif ea_raw <= 0 and aa_raw <= 0: dot_c = QColor(60,  160, 60)
            else:                              dot_c = QColor(200, 180, 30)
            if self.night_mode:
                dot_c = dot_c.lighter(130)

            # Linha pontilhada ao ponto original quando deslocado
            moved = math.hypot(offsets[i][0], offsets[i][1]) > 0.005
            if moved and self._zoom > 0.8:
                line_c = QColor(dot_c)
                line_c.setAlpha(100)
                p.setPen(QPen(line_c, 0.6, Qt.PenStyle.DotLine))
                p.drawLine(QPointF(bx, by), QPointF(cx, cy))

            # Halo de hover
            if is_hov:
                halo = QColor(dot_c)
                halo.setAlpha(50)
                p.setBrush(QBrush(halo))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), r_hover * 2.2, r_hover * 2.2)

            # Particula
            radius = r_hover if is_hov else r_base
            p.setBrush(QBrush(dot_c))
            p.setPen(
                QPen(QColor(255, 255, 255, 130), 1.2)
                if is_hov else Qt.PenStyle.NoPen
            )
            p.drawEllipse(QPointF(cx, cy), radius, radius)

            # Nome apenas no hover
            if is_hov:
                name = s.get("name", "")
                p.setFont(QFont("Special Elite", 9))
                fm  = p.fontMetrics()
                tw  = fm.horizontalAdvance(name)
                pad = 3
                lx = cx + radius + 5
                if lx + tw > ox + area_w / 2:
                    lx = cx - tw - radius - 5
                ly = cy - radius - 4
                if ly - fm.ascent() < oy - area_h / 2:
                    ly = cy + radius + fm.ascent() + 4

                bg = QColor("#0a0018" if self.night_mode else "#f0e8d5")
                bg.setAlpha(220)
                p.fillRect(
                    int(lx - pad),
                    int(ly - fm.ascent() - pad),
                    int(tw + pad * 2),
                    int(fm.height() + pad * 2),
                    bg
                )
                p.setPen(QPen(QColor("#cc88ff" if self.night_mode else "#2e1806")))
                p.drawText(QPointF(lx, ly), name)
                p.setFont(QFont("Special Elite", 8))


class PoliticalCompassDialog(QDialog):
    source_clicked = pyqtSignal(int, str)

    def __init__(self, sources, night_mode=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bussola Politica Expandida")
        self.resize(800, 600)
        layout = QVBoxLayout(self)

        hint = QLabel("Scroll: zoom  |  Clique e arraste: mover  |  Hover: nome")
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
