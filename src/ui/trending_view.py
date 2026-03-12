"""
Cronos - TrendingView
Visão expandida dos assuntos mais cobertos pela mídia.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, 
                             QLabel, QFrame, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .widgets.article_card import ArticleCard

class TrendingView(QWidget):
    article_selected = pyqtSignal(dict)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Cabeçalho
        hdr = QHBoxLayout()
        title = QLabel("🔥 Em Alta (Cobertura Simultânea)")
        title.setObjectName("sectionHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        
        ref_btn = QPushButton("↻ Atualizar")
        ref_btn.clicked.connect(self.refresh)
        hdr.addWidget(ref_btn)
        layout.addLayout(hdr)

        # Scroll principal
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.container = QWidget()
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setSpacing(20)
        self.main_layout.addStretch()
        
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

    def set_night_mode(self, night: bool):
        self.night_mode = night
        self.refresh()

    def refresh(self):
        from core.database import get_articles
        from core.trending import detect_trending
        from datetime import datetime, timedelta
        
        # Limpa o layout atual (mantendo o stretch final)
        while self.main_layout.count() > 1:
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Busca artigos das últimas 24h para um trending mais denso
        since = (datetime.now() - timedelta(hours=24)).isoformat()
        recent = get_articles(limit=600, date_from=since)
        
        # Pega agrupamentos com pelo menos 2 fontes diferentes
        clusters = detect_trending(recent, threshold=0.22, min_sources=2)

        if not clusters:
            lbl = QLabel("Nenhum assunto em destaque no momento.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.main_layout.insertWidget(0, lbl)
            return

        for i, cl in enumerate(clusters):
            cluster_frame = QFrame()
            cluster_frame.setObjectName("articleCard") # Usa o estilo de fundo dos cards
            cf_layout = QVBoxLayout(cluster_frame)
            cf_layout.setContentsMargins(16, 16, 16, 16)
            
            # Título do Cluster e Quantidade de Fontes
            ch = QHBoxLayout()
            lbl_text = cl.get("label", "Assunto em destaque")
            c_title = QLabel(f"#{i+1} — {lbl_text}")
            font = QFont("IM Fell English", 16)
            font.setItalic(True)
            c_title.setFont(font)
            ch.addWidget(c_title)
            ch.addStretch()
            
            sc = cl.get("source_count", 0)
            c_meta = QLabel(f"Coberto por {sc} fontes diferentes")
            c_meta.setObjectName("stampLabel")
            ch.addWidget(c_meta)
            cf_layout.addLayout(ch)
            
            # Palavras-chave
            kws = cl.get("keywords", [])[:6]
            if kws:
                kw_lbl = QLabel("Tags: " + ", ".join(kws))
                kw_lbl.setObjectName("statusLabel")
                cf_layout.addWidget(kw_lbl)

            # Lista horizontal com os artigos (máx 3 para não poluir)
            cards_widget = QWidget()
            h_box = QHBoxLayout(cards_widget)
            h_box.setContentsMargins(0, 10, 0, 0)
            h_box.setSpacing(10)
            
            for art in cl.get("articles", [])[:3]:
                card = ArticleCard(art, self.night_mode)
                card.clicked.connect(self.article_selected.emit)
                h_box.addWidget(card)
            h_box.addStretch()
                
            cf_layout.addWidget(cards_widget)
            self.main_layout.insertWidget(self.main_layout.count() - 1, cluster_frame)