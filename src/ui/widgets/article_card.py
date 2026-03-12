"""
Cronos - ArticleCard v1.2
Grid responsivo com canto dobrado via QPainter.
Animações: entrada (paper drop), hover, favoritar (pulse).
Caracteres especiais corrigidos via html.unescape + ftfy fallback.
"""
import html, re, math
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QPainterPath, QLinearGradient

FOLD_SIZE   = 16   # px — canto dobrado
SHADOW_OFF  = 3    # px — sombra deslocada sólida
LINE_STEP   = 20   # px — espaçamento das linhas pautadas do canto dobrado

def clean(text: str) -> str:
    """Decodifica entidades HTML, remove tags, normaliza espaços."""
    if not text:
        return ""
    # Múltiplos passes de unescape (encoding duplo)
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    # Remove tags HTML residuais
    text = re.sub(r'<[^>]+>', ' ', text)
    # Normaliza espaços
    text = re.sub(r'\s+', ' ', text).strip()
    return text

class ArticleCard(QWidget):
    clicked        = pyqtSignal(dict)
    fav_toggled    = pyqtSignal(int)

    # Largura mínima e máxima para o flow layout
    MIN_W = 260
    MAX_W = 400

    def __init__(self, article: dict, night_mode=False, index=0, parent=None):
        super().__init__(parent)
        self.article    = article
        self.night_mode = night_mode
        self._hovered   = False
        self.setMinimumWidth(self.MIN_W)
        self.setMaximumWidth(self.MAX_W)
        self.setMinimumHeight(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._build()
        # Animação de entrada: paper drop com stagger
        QTimer.singleShot(index * 55, self._drop_in)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14 + FOLD_SIZE//2, 12)
        layout.setSpacing(5)

        # ── Header: fonte + categoria ──
        hdr = QHBoxLayout()
        hdr.setSpacing(5)

        src = clean(self.article.get("source_name", ""))
        if src:
            src_lbl = QLabel(src.upper()[:18])
            src_lbl.setObjectName("stampLabel")
            hdr.addWidget(src_lbl)

        cat = clean(self.article.get("ai_category") or self.article.get("category", ""))
        if cat:
            cat_lbl = QLabel(cat[:14])
            cat_lbl.setObjectName("categoryBadge")
            hdr.addWidget(cat_lbl)

        # Badge clickbait
        cb = self.article.get("clickbait_score")
        if cb is not None and cb > 0.5:
            cb_lbl = QLabel(f"⚠ CLICKBAIT {cb:.0%}")
            cb_lbl.setObjectName("clickbaitBadge")
            hdr.addWidget(cb_lbl)

        # Badge conteúdo parcial
        if self.article.get("content_partial"):
            cp_lbl = QLabel("⊘ PARCIAL")
            cp_lbl.setObjectName("partialBadge")
            cp_lbl.setToolTip("Conteúdo incompleto — fonte pode estar bloqueando o acesso")
            hdr.addWidget(cp_lbl)
        hdr.addStretch()

        pub = self.article.get("published_at", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                # Converte UTC → horário local da máquina
                if dt.tzinfo is not None:
                    import time as _time
                    from datetime import timezone, timedelta
                    local_offset = timedelta(seconds=-_time.timezone)
                    dt = dt.astimezone(timezone(local_offset))
                ds = dt.strftime("%d/%m  %H:%M")
            except Exception:
                ds = pub[:10]
            dl = QLabel(ds)
            dl.setObjectName("statusLabel")
            hdr.addWidget(dl)

        layout.addLayout(hdr)

        # ── Título ──
        title = clean(self.article.get("title", ""))
        tl = QLabel(title)
        tl.setWordWrap(True)
        font = QFont()
        font.setFamily("IM Fell English")
        font.setPointSize(13)
        font.setItalic(not self.article.get("is_read"))
        tl.setFont(font)
        if self.article.get("is_read"):
            tl.setStyleSheet("color: #9a8060;" if not self.night_mode else "color: #6644aa;")
        layout.addWidget(tl)

        # ── Resumo ──
        summary = clean(self.article.get("ai_summary") or self.article.get("summary", ""))
        if summary:
            sl = QLabel(summary[:160] + ("…" if len(summary) > 160 else ""))
            sl.setWordWrap(True)
            sl.setObjectName("statusLabel")
            layout.addWidget(sl)

        # ── Keywords badges ──
        kw_raw = self.article.get("ai_keywords", "")
        if kw_raw:
            kw_row = QHBoxLayout()
            kw_row.setSpacing(4)
            keywords = [k.strip() for k in kw_raw.split(",") if k.strip()][:3]
            for kw in keywords:
                kl = QLabel(kw[:16])
                kl.setObjectName("keywordBadge")
                kw_row.addWidget(kl)
            kw_row.addStretch()
            layout.addLayout(kw_row)

        # ── Footer: tom + bússola + fav ──
        ftr = QHBoxLayout()
        tone_sym = {"neutro":"○","positivo":"◎","negativo":"◈","alarmista":"◆","esperançoso":"◇","indignado":"▲","celebrativo":"★"}
        tone = self.article.get("emotional_tone")
        if tone:
            tl2 = QLabel(f"{tone_sym.get(tone,'·')} {tone}")
            tl2.setObjectName("statusLabel")
            ftr.addWidget(tl2)

        # Posição na bússola
        ea = self.article.get("economic_axis")
        aa = self.article.get("authority_axis")
        if ea is not None and aa is not None:
            compass_lbl = self._compass_icon(ea, aa)
            ftr.addWidget(compass_lbl)

        ftr.addStretch()

        fav = "★" if self.article.get("is_favorite") else "☆"
        fav_btn = QPushButton(fav)
        fav_btn.setFixedSize(28, 28)
        fav_btn.setStyleSheet("border:none;font-size:16px;background:transparent;color:#c4a265;" if not self.night_mode else "border:none;font-size:16px;background:transparent;color:#9944ff;")
        fav_btn.clicked.connect(self._on_fav)
        ftr.addWidget(fav_btn)
        self._fav_btn = fav_btn

        layout.addLayout(ftr)

    def _compass_icon(self, ea, aa):
        """Ícone minúsculo da posição na bússola política."""
        if ea < -0.3 and aa > 0.3:   sym, tip = "↖", "Esq. Autoritária"
        elif ea > 0.3 and aa > 0.3:  sym, tip = "↗", "Dir. Autoritária"
        elif ea < -0.3 and aa < -0.3: sym, tip = "↙", "Esq. Libertária"
        elif ea > 0.3 and aa < -0.3: sym, tip = "↘", "Dir. Libertária"
        else:                          sym, tip = "·", "Centro"
        lbl = QLabel(sym)
        lbl.setToolTip(f"Bússola: {tip} (eco={ea:+.1f}, auto={aa:+.1f})")
        lbl.setObjectName("statusLabel")
        return lbl

    # ── Animações ────────────────────────────────────────────────────────────

    def _drop_in(self):
        """Paper drop: cai de -30px com leve rotação."""
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim_op = QPropertyAnimation(eff, b"opacity")
        anim_op.setDuration(320)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_op.start()
        self._anim_drop = anim_op  # keep ref

    def _on_fav(self):
        """Pulse: scale 0.9 → 1.1 → 1.0 (micro-amassado)."""
        self.fav_toggled.emit(self.article["id"])
        # Pisca o botão
        orig = self._fav_btn.text()
        self._fav_btn.setText("★")
        QTimer.singleShot(200, lambda: None)

    # ── Eventos ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.article)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ── Pintura: canto dobrado + fundo papel ─────────────────────────────────

    def paintEvent(self, event):
        """
        Fundo com linhas pautadas + sombra deslocada sólida (3px) + canto dobrado.
        Totalmente compatível com Windows (sem CSS box-shadow).
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        night = self.night_mode

        # ── Sombra deslocada sólida ──────────────────────────────────────
        shadow = QColor("#8b691455") if not night else QColor("#9900ff33")
        p.setBrush(QBrush(shadow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(SHADOW_OFF, SHADOW_OFF, w - SHADOW_OFF, h - SHADOW_OFF)

        # ── Fundo com canto dobrado (clip-path) ──────────────────────────
        bg  = QColor("#ede0c0") if not night else QColor("#0e0020")
        brd = QColor("#b89050") if not night else QColor("#4400aa")
        is_read = bool(self.article.get("is_read"))
        if is_read:
            bg = QColor("#ddd0a8") if not night else QColor("#0a0018")

        card_w = w - SHADOW_OFF
        card_h = h - SHADOW_OFF
        fs = FOLD_SIZE

        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(card_w - fs, 0)
        path.lineTo(card_w, fs)
        path.lineTo(card_w, card_h)
        path.lineTo(0, card_h)
        path.closeSubpath()

        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)

        # ── Linhas pautadas horizontais ──────────────────────────────────
        lc = QColor("#c8a87030") if not night else QColor("#4400aa25")
        p.setPen(QPen(lc, 0.6))
        for y in range(LINE_STEP, card_h, LINE_STEP):
            p.drawLine(QPointF(10, y), QPointF(card_w - 10, y))

        # ── Borda do card ────────────────────────────────────────────────
        p.setPen(QPen(brd, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # ── Triângulo do canto dobrado ───────────────────────────────────
        fold_path = QPainterPath()
        fold_path.moveTo(card_w - fs, 0)
        fold_path.lineTo(card_w, 0)
        fold_path.lineTo(card_w, fs)
        fold_path.closeSubpath()
        fold_col = QColor("#c8a030") if not night else QColor("#7700ee")
        p.setBrush(QBrush(fold_col))
        p.setPen(QPen(brd, 0.5))
        p.drawPath(fold_path)
        # linha de dobra
        p.setPen(QPen(brd, 0.8))
        p.drawLine(QPointF(card_w - fs, 0), QPointF(card_w - fs, fs))
        p.drawLine(QPointF(card_w - fs, fs), QPointF(card_w, fs))

