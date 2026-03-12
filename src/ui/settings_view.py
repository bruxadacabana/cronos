"""
Cronos - Tela de Configurações
Gerencia preferências visuais, IA e sistema do aplicativo.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QGroupBox,
    QFormLayout, QScrollArea, QFrame, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.database import get_setting, set_setting, get_connection, get_alert_rules, add_alert_rule
from core.ai import get_available_models

class SettingsView(QWidget):
    theme_changed = pyqtSignal(str)

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Configurações do Sistema")
        title.setObjectName("titleLabel")
        main.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(20)

        # ── Aparência ──
        appearance = QGroupBox("Aparência e Tema")
        af = QFormLayout(appearance)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dia (Papel & Máquina)", "Noite (Cyberpunk)"])
        self.theme_combo.currentIndexChanged.connect(self._on_theme_change)
        af.addRow("Tema:", self.theme_combo)

        self.auto_theme = QCheckBox("Trocar tema automaticamente por horário")
        af.addRow("", self.auto_theme)

        self.day_start = QLineEdit()
        self.day_start.setPlaceholderText("07:00")
        self.day_start.setMaximumWidth(80)
        af.addRow("Início do dia (HH:MM):", self.day_start)

        self.night_start = QLineEdit()
        self.night_start.setPlaceholderText("19:00")
        self.night_start.setMaximumWidth(80)
        af.addRow("Início da noite (HH:MM):", self.night_start)

        self.font_size = QSpinBox()
        self.font_size.setRange(10, 24)
        self.font_size.setValue(15)
        af.addRow("Tamanho da fonte (leitor):", self.font_size)

        layout.addWidget(appearance)

        # ── Ollama / IA ──
        ai_group = QGroupBox("Inteligência Artificial (Ollama)")
        aif = QFormLayout(ai_group)

        self.ollama_url = QLineEdit()
        self.ollama_url.setPlaceholderText("http://localhost:11434")
        aif.addRow("URL do Ollama:", self.ollama_url)

        self.ollama_model = QComboBox()
        self.ollama_model.setEditable(True)
        aif.addRow("Modelo:", self.ollama_model)

        refresh_models_btn = QPushButton("↻ Carregar modelos disponíveis")
        refresh_models_btn.clicked.connect(self._load_models)
        aif.addRow("", refresh_models_btn)

        self.ollama_enabled = QCheckBox("Usar Ollama para análise e tradução")
        aif.addRow("", self.ollama_enabled)

        self.ollama_android_url = QLineEdit()
        self.ollama_android_url.setPlaceholderText("http://192.168.1.x:11434")
        aif.addRow("URL Ollama (Android via rede local):", self.ollama_android_url)

        layout.addWidget(ai_group)

        # ── Tradução ──
        trans_group = QGroupBox("Tradução")
        tf = QFormLayout(trans_group)

        self.default_language = QComboBox()
        from core.translator import get_supported_languages
        for code, name in get_supported_languages().items():
            self.default_language.addItem(name, code)
        tf.addRow("Idioma padrão:", self.default_language)

        self.translate_fallback = QCheckBox("Usar Google Translate como fallback")
        tf.addRow("", self.translate_fallback)

        layout.addWidget(trans_group)

        # ── Notificações / Alertas ──
        notif_group = QGroupBox("Alertas e Notificações")
        nl = QVBoxLayout(notif_group)

        self.notif_enabled = QCheckBox("Ativar notificações do sistema")
        nl.addWidget(self.notif_enabled)

        nl.addWidget(QLabel("Regras de alerta ativas:"))
        self.alerts_list = QListWidget()
        self.alerts_list.setMaximumHeight(120)
        nl.addWidget(self.alerts_list)
        self._load_alerts()

        alert_btns = QHBoxLayout()
        add_kw_btn = QPushButton("+ Palavra-chave")
        add_kw_btn.clicked.connect(lambda: self._add_alert("keyword"))
        add_src_alert_btn = QPushButton("+ Fonte")
        add_src_alert_btn.clicked.connect(lambda: self._add_alert("source"))
        alert_btns.addWidget(add_kw_btn)
        alert_btns.addWidget(add_src_alert_btn)
        nl.addLayout(alert_btns)

        layout.addWidget(notif_group)

        # ── Dados ──
        data_group = QGroupBox("Dados e Privacidade")
        dl = QVBoxLayout(data_group)

        dl.addWidget(QLabel("Todos os dados são armazenados localmente em /data/"))

        data_btns = QHBoxLayout()
        clear_read_btn = QPushButton("Limpar artigos lidos antigos")
        clear_read_btn.clicked.connect(self._clear_old_articles)
        clear_cache_btn = QPushButton("Limpar cache de imagens")
        clear_cache_btn.clicked.connect(self._clear_cache)
        data_btns.addWidget(clear_read_btn)
        data_btns.addWidget(clear_cache_btn)
        dl.addLayout(data_btns)

        layout.addWidget(data_group)

        # ── Período de Notícias ──
        period_group = QGroupBox("Período de Notícias")
        pf = QFormLayout(period_group)

        self.article_max_age = QSpinBox()
        self.article_max_age.setRange(0, 3650)
        self.article_max_age.setSuffix(" dias  (0 = sem limite)")
        self.article_max_age.setSpecialValueText("Sem limite")
        pf.addRow("Baixar notícias dos últimos:", self.article_max_age)

        pf.addRow("", QLabel(
            "Padrão: 30 dias. Cada fonte pode ter seu próprio limite\n"
            "(configure na tela Fontes → botão 'Período')."
        ))

        layout.addWidget(period_group)

        # Botão salvar
        save_btn = QPushButton("💾 Salvar configurações")
        save_btn.setObjectName("btnPrimary")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        layout.addStretch()
        scroll.setWidget(container)
        main.addWidget(scroll)

    def _load_settings(self):
        self.theme_combo.setCurrentIndex(0 if get_setting("theme", "day") == "day" else 1)
        self.auto_theme.setChecked(get_setting("theme_auto", "1") == "1")
        self.day_start.setText(get_setting("theme_day_start", "07:00"))
        self.night_start.setText(get_setting("theme_night_start", "19:00"))
        self.font_size.setValue(int(get_setting("reader_font_size", "15")))
        self.ollama_url.setText(get_setting("ollama_url", "http://localhost:11434"))
        self.ollama_enabled.setChecked(get_setting("ollama_enabled", "1") == "1")
        self.ollama_android_url.setText(get_setting("ollama_android_url", ""))
        self.translate_fallback.setChecked(get_setting("translate_fallback", "1") == "1")
        self.notif_enabled.setChecked(get_setting("notifications_enabled", "1") == "1")
        self.article_max_age.setValue(int(get_setting("article_max_age_days", "30")))

        default_lang = get_setting("default_language", "pt")
        for i in range(self.default_language.count()):
            if self.default_language.itemData(i) == default_lang:
                self.default_language.setCurrentIndex(i)
                break

    def _save(self):
        set_setting("theme", "day" if self.theme_combo.currentIndex() == 0 else "night")
        set_setting("theme_auto", "1" if self.auto_theme.isChecked() else "0")
        set_setting("theme_day_start", self.day_start.text() or "07:00")
        set_setting("theme_night_start", self.night_start.text() or "19:00")
        set_setting("reader_font_size", str(self.font_size.value()))
        set_setting("ollama_url", self.ollama_url.text() or "http://localhost:11434")
        set_setting("ollama_model", self.ollama_model.currentText())
        set_setting("ollama_enabled", "1" if self.ollama_enabled.isChecked() else "0")
        set_setting("ollama_android_url", self.ollama_android_url.text())
        set_setting("translate_fallback", "1" if self.translate_fallback.isChecked() else "0")
        set_setting("default_language", self.default_language.currentData())
        set_setting("notifications_enabled", "1" if self.notif_enabled.isChecked() else "0")
        set_setting("article_max_age_days", str(self.article_max_age.value()))
        set_setting("date_limit_asked", "1")  # marca que o usuário já configurou
        QMessageBox.information(self, "Cronos", "Configurações salvas com sucesso!")

    def _on_theme_change(self, index):
        self.theme_changed.emit("day" if index == 0 else "night")

    def _load_models(self):
        models = get_available_models()
        current = self.ollama_model.currentText()
        self.ollama_model.clear()
        if models:
            self.ollama_model.addItems(models)
            if current in models:
                self.ollama_model.setCurrentText(current)
        else:
            self.ollama_model.addItem(get_setting("ollama_model", "llama3"))
            QMessageBox.information(self, "Ollama", "Ollama não está disponível ou nenhum modelo instalado.")

    def _load_alerts(self):
        self.alerts_list.clear()
        for rule in get_alert_rules():
            icon = "🔑" if rule["type"] == "keyword" else "📰"
            self.alerts_list.addItem(f"{icon} [{rule['type']}] {rule['value']}")

    def _add_alert(self, rule_type: str):
        prompt = "Digite a palavra-chave:" if rule_type == "keyword" else "Nome da fonte:"
        text, ok = QInputDialog.getText(self, "Novo alerta", prompt)
        if ok and text.strip():
            add_alert_rule(rule_type, text.strip())
            self._load_alerts()

    def _clear_old_articles(self):
        reply = QMessageBox.question(self, "Confirmar", "Remover artigos lidos com mais de 30 dias?")
        if reply == QMessageBox.StandardButton.Yes:
            conn = get_connection()
            conn.execute("DELETE FROM articles WHERE is_read=1 AND is_favorite=0 AND published_at < datetime('now', '-30 days')")
            conn.commit(); conn.close()
            QMessageBox.information(self, "Cronos", "Artigos antigos removidos.")

    def _clear_cache(self):
        import shutil
        from pathlib import Path
        cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
        try:
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(exist_ok=True)
            QMessageBox.information(self, "Cronos", "Cache limpo com sucesso.")
        except Exception as e:
            QMessageBox.warning(self, "Erro", str(e))