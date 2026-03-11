"""
Cronos - DashboardView v1.3
Bússola política, timeline emocional, nuvem de palavras,
radar de temas, termômetro de polarização, ranking, clickbait.
"""
import math, json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QGridLayout, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QLinearGradient

from .widgets.compass import PoliticalCompassWidget, PoliticalCompassDialog
from .widgets.dashboard_widgets import (
    WordCloudWidget, EmotionTimelineWidget, RadarWidget,
    PolarizationThermometerWidget, SourceRankingWidget
)


class DashboardView(QWidget):
    open_source_feed = pyqtSignal(int, str)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._build()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(60000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        title = QLabel("Dashboard de Análise")
        title.setObjectName("sectionHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self.last_updated = QLabel()
        self.last_updated.setObjectName("statusLabel")
        hdr.addWidget(self.last_updated)
        refresh_btn = QPushButton("↻ Atualizar")
        refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(refresh_btn)
        layout.addLayout(hdr)

        # Tabs para organizar os painéis
        self.tabs = QTabWidget()

        # ── Tab 1: Viés & Bússola ──
        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)

        # Bússola
        compass_group = QFrame()
        cg_layout = QVBoxLayout(compass_group)
        ch = QHBoxLayout()
        cg_lbl = QLabel("Bússola Política das Fontes")
        cg_lbl.setObjectName("sectionHeader")
        ch.addWidget(cg_lbl)
        ch.addStretch()
        expand_btn = QPushButton("⛶  Expandir")
        expand_btn.clicked.connect(self._expand_compass)
        ch.addWidget(expand_btn)
        cg_layout.addLayout(ch)
        hint = QLabel("Scroll = zoom  ·  Arrastar = mover  ·  Clique numa fonte = ver notícias  ·  Hover = afasta sobrepostos")
        hint.setObjectName("statusLabel")
        cg_layout.addWidget(hint)
        self.compass = PoliticalCompassWidget(self.night_mode)
        self.compass.setMinimumHeight(320)
        self.compass.source_clicked.connect(self.open_source_feed)
        cg_layout.addWidget(self.compass)
        t1.addWidget(compass_group)

        # Termômetro de polarização
        pol_group = QFrame()
        pl = QVBoxLayout(pol_group)
        pol_lbl = QLabel("Termômetro de Polarização da Sua Leitura")
        pol_lbl.setObjectName("sectionHeader")
        pl.addWidget(pol_lbl)
        hint2 = QLabel("Média ponderada do viés econômico das notícias que você leu esta semana.")
        hint2.setObjectName("statusLabel")
        pl.addWidget(hint2)
        self.polarization = PolarizationThermometerWidget(self.night_mode)
        pl.addWidget(self.polarization)
        t1.addWidget(pol_group)
        t1.addStretch()
        self.tabs.addTab(tab1, "🧭 Viés")

        # ── Tab 2: Palavras & Temas ──
        tab2 = QWidget()
        t2 = QVBoxLayout(tab2)

        # Nuvem de palavras
        wc_group = QFrame()
        wc_layout = QVBoxLayout(wc_group)
        wc_lbl = QLabel("Nuvem de Palavras (últimas 24h)")
        wc_lbl.setObjectName("sectionHeader")
        wc_layout.addWidget(wc_lbl)
        self.word_cloud = WordCloudWidget(self.night_mode)
        self.word_cloud.setMinimumHeight(180)
        wc_layout.addWidget(self.word_cloud)
        t2.addWidget(wc_group)

        # Radar de temas
        radar_group = QFrame()
        rg_layout = QHBoxLayout(radar_group)
        rl = QVBoxLayout()
        radar_lbl = QLabel("Radar de Categorias")
        radar_lbl.setObjectName("sectionHeader")
        rl.addWidget(radar_lbl)
        hint3 = QLabel("Equilíbrio das categorias nas notícias das últimas 24h.")
        hint3.setObjectName("statusLabel")
        rl.addWidget(hint3)
        self.radar = RadarWidget(self.night_mode)
        self.radar.setMinimumHeight(220)
        self.radar.setMinimumWidth(220)
        rl.addStretch()
        rg_layout.addLayout(rl)
        rg_layout.addWidget(self.radar, 1)
        t2.addWidget(radar_group)
        t2.addStretch()
        self.tabs.addTab(tab2, "📊 Palavras")

        # ── Tab 3: Fontes & Emoções ──
        tab3 = QWidget()
        t3 = QVBoxLayout(tab3)

        # Ranking de fontes
        rank_group = QFrame()
        rk_layout = QVBoxLayout(rank_group)
        rk_lbl = QLabel("Ranking de Fontes Mais Ativas (7 dias)")
        rk_lbl.setObjectName("sectionHeader")
        rk_layout.addWidget(rk_lbl)
        self.source_ranking = SourceRankingWidget(self.night_mode)
        self.source_ranking.setMinimumHeight(200)
        rk_layout.addWidget(self.source_ranking)
        t3.addWidget(rank_group)

        # Timeline emocional
        tl_group = QFrame()
        tl_layout = QVBoxLayout(tl_group)
        tl_label = QLabel("Linha do Tempo de Tom Emocional")
        tl_label.setObjectName("sectionHeader")
        tl_layout.addWidget(tl_label)
        self.emotion_timeline = EmotionTimelineWidget(self.night_mode)
        self.emotion_timeline.setMinimumHeight(180)
        tl_layout.addWidget(self.emotion_timeline)
        t3.addWidget(tl_group)
        t3.addStretch()
        self.tabs.addTab(tab3, "📰 Fontes")

        # ── Tab 4: Clickbait & Categorias ──
        tab4 = QWidget()
        t4 = QVBoxLayout(tab4)

        row3 = QHBoxLayout()
        cb_group = QFrame()
        cb_layout = QVBoxLayout(cb_group)
        cb_label = QLabel("Índice de Clickbait por Fonte")
        cb_label.setObjectName("sectionHeader")
        cb_layout.addWidget(cb_label)
        self.clickbait_chart = _HBarChart(self.night_mode)
        cb_layout.addWidget(self.clickbait_chart)
        row3.addWidget(cb_group)

        cat_group = QFrame()
        cat_layout = QVBoxLayout(cat_group)
        cat_label = QLabel("Distribuição por Categoria")
        cat_label.setObjectName("sectionHeader")
        cat_layout.addWidget(cat_label)
        self.category_chart = _HBarChart(self.night_mode, show_pct=True)
        cat_layout.addWidget(self.category_chart)
        row3.addWidget(cat_group)
        t4.addLayout(row3)

        # Bias timeline (legado)
        tl2_group = QFrame()
        tl2_layout = QVBoxLayout(tl2_group)
        tl2_label = QLabel("Evolução do Viés Econômico (30 dias)")
        tl2_label.setObjectName("sectionHeader")
        tl2_layout.addWidget(tl2_label)
        self.bias_timeline = _BiasTimelineWidget(self.night_mode)
        self.bias_timeline.setMinimumHeight(180)
        tl2_layout.addWidget(self.bias_timeline)
        t4.addWidget(tl2_group)
        t4.addStretch()
        self.tabs.addTab(tab4, "⚠ Clickbait")

        layout.addWidget(self.tabs)

    def refresh(self):
        from core.database import get_dashboard_data, get_articles, get_connection
        data = get_dashboard_data()

        # Tab 1
        self.compass.set_data(data.get("sources_political", []))
        # Termômetro: média das leituras
        conn = get_connection()
        row = conn.execute(
            "SELECT AVG(a.economic_axis) as avg_eco FROM articles a "
            "WHERE a.is_read=1 AND a.economic_axis IS NOT NULL "
            "AND a.fetched_at >= datetime('now','-7 days')"
        ).fetchone()
        # Diversidade: fontes únicas lidas / total fontes ativas
        r2 = conn.execute("SELECT COUNT(DISTINCT source_id) as uniq FROM articles WHERE is_read=1 AND fetched_at>=datetime('now','-7 days')").fetchone()
        r3 = conn.execute("SELECT COUNT(*) as tot FROM sources WHERE active=1").fetchone()
        conn.close()
        avg_eco = (row["avg_eco"] or 0.0) if row else 0.0
        uniq = (r2["uniq"] or 0) if r2 else 0
        tot  = (r3["tot"] or 1) if r3 else 1
        self.polarization.set_data(avg_eco, uniq / tot)

        # Tab 2: nuvem de palavras
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(hours=24)).isoformat()
        recent = get_articles(limit=500, date_from=since)
        import re as _re
        word_counts = {}
        STOP = {"de","da","do","das","dos","em","no","na","nos","nas","um","uma","uns","umas","o","a","os","as","e","é","para","por","com","que","se","the","of","in","to","is","for","and","or","this","with","on","at","by","from","an","be"}
        for art in recent:
            kws = art.get("ai_keywords", "") or ""
            for kw in kws.split(","):
                kw = kw.strip().lower()
                if kw and len(kw) > 3 and kw not in STOP:
                    word_counts[kw] = word_counts.get(kw, 0) + 1
        words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:35]
        self.word_cloud.set_data(words)

        # Radar
        cats_raw = data.get("by_category", [])
        max_c = max((r.get("count",0) for r in cats_raw), default=1) or 1
        radar_data = [(r.get("cat","?")[:10], r.get("count",0)/max_c) for r in cats_raw[:8]]
        self.radar.set_data(radar_data)

        # Tab 3: Ranking e timeline emocional
        sp = data.get("sources_political", [])
        ranking = sorted(sp, key=lambda s: s.get("article_count",0), reverse=True)
        self.source_ranking.set_data([(s["name"], s.get("article_count",0)) for s in ranking[:10]])

        # Emotion timeline
        conn2 = get_connection()
        tl_rows = conn2.execute(
            "SELECT date(a.published_at) as day, a.emotional_tone as tone, COUNT(*) as count "
            "FROM articles a WHERE a.emotional_tone IS NOT NULL "
            "AND a.published_at >= datetime('now','-14 days') "
            "GROUP BY day, tone ORDER BY day"
        ).fetchall()
        conn2.close()
        self.emotion_timeline.set_data([dict(r) for r in tl_rows])

        # Tab 4: Clickbait e categorias
        cb = [(r.get("name","?"), r.get("avg_score") or 0.0) for r in data.get("clickbait", [])]
        self.clickbait_chart.set_data(cb)
        cats = [(r.get("cat") or "geral", r.get("count") or 0) for r in cats_raw]
        self.category_chart.set_data(cats)
        self.bias_timeline.set_data(data.get("bias_timeline", []))

        from datetime import datetime as _dt
        self.last_updated.setText(f"atualizado {_dt.now().strftime('%H:%M')}")

    def _expand_compass(self):
        from core.database import get_dashboard_data
        data = get_dashboard_data()
        dlg = PoliticalCompassDialog(data.get("sources_political",[]), self.night_mode, self)
        dlg.source_clicked.connect(self.open_source_feed)
        dlg.exec()

    def set_night_mode(self, v):
        self.night_mode = v
        self.compass.set_night_mode(v)
        self.bias_timeline.set_night_mode(v)
        self.clickbait_chart.set_night_mode(v)
        self.category_chart.set_night_mode(v)
        self.word_cloud.set_night_mode(v)
        self.radar.set_night_mode(v)
        self.emotion_timeline.set_night_mode(v)
        self.source_ranking.set_night_mode(v)
        self.polarization.set_night_mode(v)


# ── Widgets legados ────────────────────────────────────────────────────────────

class _BiasTimelineWidget(QWidget):
    def __init__(self, night=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.data = []

    def set_data(self, data): self.data = data; self.update()
    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mg = 40
        fg   = QColor("#e0d0ff") if self.night else QColor("#2a1a08")
        grid = QColor("#4400aa") if self.night else QColor("#b89040")
        p.setPen(QPen(fg)); p.setFont(QFont("Special Elite", 9))
        p.drawText(0, 15, "Viés Econômico ao longo do tempo")
        if not self.data:
            p.setPen(QPen(QColor("#888"), 1, Qt.PenStyle.DotLine))
            p.drawText(w//2-60, h//2, "Aguardando análises…")
            return
        by_date = {}
        for r in self.data:
            d = r.get("day","")
            if d not in by_date: by_date[d] = []
            by_date[d].append(r.get("avg_economic",0) or 0)
        dates = sorted(by_date.keys())
        avgs  = [sum(by_date[d])/len(by_date[d]) for d in dates]
        if len(avgs) < 2: return
        p.setPen(QPen(grid, 0.5, Qt.PenStyle.DotLine))
        for i in range(5):
            y = mg + (h-mg*2)*i//4
            p.drawLine(mg, y, w-mg, y)
        p.drawLine(mg, mg, mg, h-mg); p.drawLine(mg, h//2, w-mg, h//2)
        dx = (w-mg*2)/(len(dates)-1)
        pen = QPen(QColor("#7b00ff") if self.night else QColor("#8b6020"), 2)
        p.setPen(pen)
        pts = [(mg+i*dx, h//2-(avgs[i]*(h-mg*2)//2)) for i in range(len(avgs))]
        for i in range(len(pts)-1):
            p.drawLine(QPointF(*pts[i]), QPointF(*pts[i+1]))
        p.setBrush(QBrush(QColor("#7b00ff") if self.night else QColor("#8b6020")))
        p.setPen(Qt.PenStyle.NoPen)
        for x,y in pts:
            p.drawEllipse(QPointF(x,y),3,3)


class _HBarChart(QWidget):
    def __init__(self, night=False, show_pct=False, parent=None):
        super().__init__(parent)
        self.night = night
        self.show_pct = show_pct
        self.data = []
        self.setMinimumHeight(180)

    def set_data(self, data): self.data = data[:10]; self.update()
    def set_night_mode(self, v): self.night = v; self.update()

    def paintEvent(self, event):
        if not self.data: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        fg  = QColor("#e0d0ff") if self.night else QColor("#2a1a08")
        bar = QColor("#7b00ff") if self.night else QColor("#8b6020")
        p.setFont(QFont("Special Elite", 9))
        n = len(self.data)
        row_h = h // max(1, n)
        max_v = max((v for _,v in self.data), default=1) or 1
        label_w = 120
        for i,(name,val) in enumerate(self.data):
            y = i * row_h + 2
            p.setPen(QPen(fg))
            p.drawText(QRectF(0, y, label_w, row_h-4), Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignRight, str(name)[:16])
            bw = int((val/max_v)*(w-label_w-40))
            p.fillRect(QRectF(label_w+6, y+4, bw, row_h-10), QBrush(bar))
            txt = f"{int(val)}" if self.show_pct else (f"{val:.0%}" if val <= 1 else f"{val:.1f}")
            p.drawText(QRectF(label_w+bw+10, y, 40, row_h), Qt.AlignmentFlag.AlignVCenter, txt)
