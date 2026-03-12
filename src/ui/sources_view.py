"""Cronos - SourcesView v1.2 com Pesquisa e Configurações"""
import html
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QDialogButtonBox,
    QMessageBox, QGroupBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from core.database import get_setting, set_setting

def _c(t):
    return html.unescape(t) if t else ""

def _days_since(iso_str):
    """Retorna há quantos dias foi a data ISO, ou None se inválida."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, delta.days)
    except Exception:
        return None

class SourcesView(QWidget):
    open_source_feed = pyqtSignal(int, str)
    fetch_now = pyqtSignal() # Sinal para o botão "Atualizar Agora"

    def __init__(self, night_mode=False, parent=None):
        super().__init__(parent)
        self.night_mode = night_mode
        self._build()
        self._load_feed_settings()
        self._check_first_run_date_limit()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16,16,16,16)
        layout.setSpacing(10)

        # ── Área de Configurações da Fonte ──
        config_group = QGroupBox("Regras de Atualização")
        cf_layout = QFormLayout(config_group)
        
        self.fetch_interval = QSpinBox()
        self.fetch_interval.setRange(5, 1440)
        self.fetch_interval.setSuffix(" minutos")
        cf_layout.addRow("Intervalo de atualização:", self.fetch_interval)

        self.fetch_on_startup = QCheckBox("Baixar notícias automaticamente ao abrir o Cronos")
        cf_layout.addRow("", self.fetch_on_startup)


        btn_layout = QHBoxLayout()
        save_cfg_btn = QPushButton("💾 Salvar Regras")
        save_cfg_btn.clicked.connect(self._save_feed_settings)
        fetch_now_btn = QPushButton("↻ Forçar Atualização Agora")
        fetch_now_btn.setObjectName("btnPrimary")
        fetch_now_btn.clicked.connect(self.fetch_now.emit)
        
        btn_layout.addWidget(save_cfg_btn)
        btn_layout.addWidget(fetch_now_btn)
        btn_layout.addStretch()
        cf_layout.addRow("", btn_layout)

        layout.addWidget(config_group)

        # ── Gerenciamento da Lista de Fontes ──
        title = QLabel("Gerenciar Suas Fontes")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText("Filtrar sua lista...")
        self.search.textChanged.connect(self._filter)
        bar.addWidget(self.search, 2)
        
        search_web_btn = QPushButton("🔍 Pesquisar Novas Fontes")
        search_web_btn.clicked.connect(self._open_search_dialog)
        bar.addWidget(search_web_btn)
        
        add_btn = QPushButton("+ Adicionar Manual")
        add_btn.setObjectName("btnPrimary")
        add_btn.clicked.connect(self._add_dialog)
        bar.addWidget(add_btn)
        layout.addLayout(bar)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._edit_item)
        layout.addWidget(self.list)

        btns = QHBoxLayout()
        edit_btn = QPushButton("✏ Editar")
        edit_btn.clicked.connect(self._edit_selected)
        del_btn = QPushButton("✕ Desativar")
        del_btn.setObjectName("btnDanger")
        del_btn.clicked.connect(self._remove)
        period_btn = QPushButton("📅 Período")
        period_btn.setToolTip("Baixar notícias de um período específico desta fonte")
        period_btn.clicked.connect(self._period_dialog)
        open_btn = QPushButton("📰 Ver notícias desta fonte")
        open_btn.setObjectName("btnPrimary")
        open_btn.clicked.connect(self._open_feed)

        btns.addWidget(edit_btn)
        btns.addWidget(del_btn)
        btns.addWidget(period_btn)
        btns.addStretch()
        btns.addWidget(open_btn)
        layout.addLayout(btns)
        self.reload()

    def _load_feed_settings(self):
        self.fetch_interval.setValue(int(get_setting("fetch_interval", "30")))
        self.fetch_on_startup.setChecked(get_setting("fetch_on_startup", "1") == "1")

    def _save_feed_settings(self):
        set_setting("fetch_interval", str(self.fetch_interval.value()))
        set_setting("fetch_on_startup", "1" if self.fetch_on_startup.isChecked() else "0")
        QMessageBox.information(self, "Salvo", "Regras de atualização salvas com sucesso!")

    def reload(self):
        self.list.clear()
        from core.database import get_sources
        self._all = get_sources(active_only=False)
        for s in self._all:
            active = "✓" if s["active"] else "○"
            ea = s.get("economic_axis", 0) or 0
            aa = s.get("authority_axis", 0) or 0
            text = f"{active}  [{_c(s['category'])}]  {_c(s['name'])}  (eco:{ea:+.1f} aut:{aa:+.1f})"

            # Badge de inatividade
            days = _days_since(s.get("last_fetched"))
            if days is None:
                text += "  ⚠ nunca atualizada"
            elif days >= 7:
                text += f"  ⚠ sem notícias há {days}d"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, s)
            if not s["active"]:
                item.setForeground(QColor("#9a8060" if not self.night_mode else "#6644aa"))
            elif days is not None and days >= 7:
                item.setForeground(QColor("#c04020" if not self.night_mode else "#ff6644"))
            self.list.addItem(item)

    def _filter(self, text):
        for i in range(self.list.count()):
            self.list.item(i).setHidden(text.lower() not in self.list.item(i).text().lower())

    def _cur(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_feed(self):
        s = self._cur()
        if s: self.open_source_feed.emit(s["id"], s["name"])

    def _open_search_dialog(self):
        dlg = _SearchSourceDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _add_dialog(self):
        dlg = _SourceDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.get_data()
            if not d["name"] or not d["url"]:
                QMessageBox.warning(self, "Erro", "Nome e URL são obrigatórios.")
                return
            from core.fetcher import add_custom_source
            from core.database import add_source
            # Tenta validar como RSS; se falhar, adiciona diretamente com aviso
            result = add_custom_source(d["name"], d["url"], d["category"])
            if result.get("success"):
                QMessageBox.information(self, "Cronos",
                    f"Fonte adicionada com sucesso!\n{result.get('entries',0)} artigos encontrados no feed.")
                self.reload()
            else:
                # Oferece adicionar mesmo assim
                msg = result.get("error","Erro desconhecido")
                resp = QMessageBox.question(self, "Feed não validado",
                    f"Não foi possível validar o feed RSS:\n{msg}\n\nAdicionar mesmo assim?")
                if resp == QMessageBox.StandardButton.Yes:
                    add_source(d["name"], d["url"], d["category"])
                    self.reload()

    def _edit_item(self, item):
        self._edit_source(item.data(Qt.ItemDataRole.UserRole))

    def _edit_selected(self):
        s = self._cur()
        if s: self._edit_source(s)

    def _edit_source(self, source):
        dlg = _SourceDialog(source=source, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.get_data()
            from core.database import get_connection
            conn = get_connection()
            conn.execute("UPDATE sources SET name=?,url=?,category=?,active=?,economic_axis=?,authority_axis=? WHERE id=?",
                (d["name"],d["url"],d["category"],d.get("active",1),d.get("economic_axis",0.0),d.get("authority_axis",0.0),source["id"]))
            conn.commit(); conn.close()
            self.reload()

    def _remove(self):
        s = self._cur()
        if not s: return
        if QMessageBox.question(self,"Confirmar",f"Desativar '{s['name']}'?") == QMessageBox.StandardButton.Yes:
            from core.database import get_connection
            conn = get_connection()
            conn.execute("UPDATE sources SET active=0 WHERE id=?", (s["id"],))
            conn.commit(); conn.close()
            self.reload()


    def _check_first_run_date_limit(self):
        """Pergunta ao usuário o limite de data na primeira execução."""
        from core.database import get_setting, set_setting
        if get_setting("date_limit_asked", "0") == "1":
            return
        dlg = _DateLimitFirstRunDialog(self)
        dlg.exec()

    def _period_dialog(self):
        """Abre diálogo para baixar notícias de um período específico desta fonte."""
        s = self._cur()
        if not s:
            QMessageBox.information(self, "Cronos", "Selecione uma fonte primeiro.")
            return
        dlg = _SourcePeriodDialog(s, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            date_from, date_to, limit_days = dlg.get_data()
            if date_from or date_to:
                self._fetch_source_period(s, date_from, date_to)
            if limit_days is not None:
                from core.database import set_source_date_limit
                set_source_date_limit(s["id"], limit_days)
                QMessageBox.information(self, "Cronos",
                    f"Limite configurado: {limit_days if limit_days > 0 else 'sem limite'} dias para '{s['name']}'.")

    def _fetch_source_period(self, source, date_from, date_to):
        """Dispara download histórico para uma fonte num intervalo de datas."""
        from PyQt6.QtWidgets import QApplication
        from core.fetcher import fetch_source
        from core.database import save_articles
        QMessageBox.information(self, "Cronos",
            f"Baixando notícias de '{source['name']}' no período selecionado…\n"
            "Isso pode levar alguns segundos.")
        QApplication.processEvents()
        try:
            articles = fetch_source(source, date_from=date_from, date_to=date_to)
            if articles:
                save_articles(articles)
                QMessageBox.information(self, "Cronos",
                    f"{len(articles)} artigos encontrados e salvos.")
            else:
                QMessageBox.information(self, "Cronos",
                    "Nenhum artigo encontrado no período selecionado.\n"
                    "O feed RSS pode não ter histórico tão antigo.")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao baixar: {e}")


class _SourceDialog(QDialog):
    """Diálogo para adicionar ou editar uma fonte RSS."""

    def __init__(self, source=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Fonte" if source else "Adicionar Fonte Manual")
        self.setMinimumWidth(480)
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_input = QLineEdit(source["name"] if source else "")
        self.name_input.setPlaceholderText("Ex: BBC Brasil")

        self.url_input = QLineEdit(source["url"] if source else "")
        self.url_input.setPlaceholderText("https://feeds.exemplo.com/rss")

        self.cat_input = QLineEdit(source.get("category", "") if source else "")
        self.cat_input.setPlaceholderText("ex: tecnologia, ciência, política")

        from PyQt6.QtWidgets import QDoubleSpinBox
        self.ea_spin = QDoubleSpinBox()
        self.ea_spin.setRange(-1, 1)
        self.ea_spin.setSingleStep(0.1)
        self.ea_spin.setValue(source.get("economic_axis", 0.0) if source else 0.0)

        self.aa_spin = QDoubleSpinBox()
        self.aa_spin.setRange(-1, 1)
        self.aa_spin.setSingleStep(0.1)
        self.aa_spin.setValue(source.get("authority_axis", 0.0) if source else 0.0)

        self.active_check = QCheckBox("Fonte ativa")
        self.active_check.setChecked(bool(source.get("active", 1)) if source else True)

        layout.addRow("Nome:", self.name_input)
        layout.addRow("URL RSS:", self.url_input)
        layout.addRow("Categorias:", self.cat_input)
        layout.addRow("Eixo Econômico (-1=esq, +1=dir):", self.ea_spin)
        layout.addRow("Eixo Autoritário (-1=lib, +1=aut):", self.aa_spin)
        layout.addRow("", self.active_check)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_data(self):
        return {
            "name":          self.name_input.text().strip(),
            "url":           self.url_input.text().strip(),
            "category":      self.cat_input.text().strip() or "geral",
            "active":        int(self.active_check.isChecked()),
            "economic_axis": self.ea_spin.value(),
            "authority_axis": self.aa_spin.value(),
        }


class _DateLimitFirstRunDialog(QDialog):
    """Diálogo exibido na primeira execução para configurar o limite de data."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cronos — Configuração Inicial")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "<b>Por quanto tempo atrás você quer baixar notícias?</b><br><br>"
            "O padrão é 30 dias. Você pode alterar isso a qualquer momento\n"
            "em Configurações → Período de Notícias."
        ))

        form = QFormLayout()
        self.days_spin = QSpinBox()
        self.days_spin.setRange(0, 3650)
        self.days_spin.setValue(30)
        self.days_spin.setSuffix(" dias")
        self.days_spin.setSpecialValueText("Sem limite")
        form.addRow("Baixar notícias dos últimos:", self.days_spin)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self._save_and_accept)
        layout.addWidget(btns)

    def _save_and_accept(self):
        from core.database import set_setting
        set_setting("article_max_age_days", str(self.days_spin.value()))
        set_setting("date_limit_asked", "1")
        self.accept()


class _SourcePeriodDialog(QDialog):
    """Diálogo para baixar notícias de um intervalo de datas de uma fonte."""
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Período — {source['name']}")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "<b>Baixar notícias de um período específico</b><br>"
            "O feed RSS pode ter histórico limitado dependendo da fonte."
        ))

        from PyQt6.QtWidgets import QDateEdit
        from PyQt6.QtCore import QDate
        form = QFormLayout()

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        form.addRow("De:", self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Até:", self.date_to)

        layout.addLayout(form)

        # Limite permanente por fonte
        from core.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT date_limit_days FROM sources WHERE id=?", (source["id"],)).fetchone()
        conn.close()
        current_limit = row["date_limit_days"] if row and row["date_limit_days"] is not None else None

        layout.addWidget(QLabel("<br><b>Limite permanente para esta fonte:</b>"))
        form2 = QFormLayout()
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 3650)
        self.limit_spin.setSuffix(" dias  (0 = sem limite)")
        self.limit_spin.setSpecialValueText("Usar limite global")
        if current_limit is not None:
            self.limit_spin.setValue(current_limit)
        form2.addRow("Máximo de dias a baixar:", self.limit_spin)
        layout.addLayout(form2)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        from datetime import datetime, timezone
        from PyQt6.QtCore import QDate

        qf = self.date_from.date()
        qt = self.date_to.date()
        date_from = datetime(qf.year(), qf.month(), qf.day(), tzinfo=timezone.utc)
        date_to   = datetime(qt.year(), qt.month(), qt.day(), 23, 59, 59, tzinfo=timezone.utc)

        limit = self.limit_spin.value()
        # -1 = não alterar o limite permanente (valor "Usar limite global" = 0 no spinbox com min=-1)
        return date_from, date_to, limit
    def __init__(self, source=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Fonte" if source else "Adicionar Fonte Manual")
        self.setMinimumWidth(460)
        layout = QFormLayout(self)
        layout.setSpacing(10)
        
        self.name_input = QLineEdit(source["name"] if source else "")
        self.url_input  = QLineEdit(source["url"] if source else "")
        
        # NOVO: Campo de texto livre para múltiplas categorias
        self.cat_input = QLineEdit(source["category"] if source else "")
        self.cat_input.setPlaceholderText("ex: tecnologia, ciência, centro-esquerda")
            
        from PyQt6.QtWidgets import QDoubleSpinBox
        self.ea_spin = QDoubleSpinBox(); self.ea_spin.setRange(-1,1); self.ea_spin.setSingleStep(0.1); self.ea_spin.setValue(source.get("economic_axis",0.0) if source else 0.0)
        self.aa_spin = QDoubleSpinBox(); self.aa_spin.setRange(-1,1); self.aa_spin.setSingleStep(0.1); self.aa_spin.setValue(source.get("authority_axis",0.0) if source else 0.0)
        
        self.active_check = QCheckBox("Fonte ativa")
        self.active_check.setChecked(bool(source.get("active",1)) if source else True)
        
        layout.addRow("Nome:", self.name_input)
        layout.addRow("URL RSS:", self.url_input)
        layout.addRow("Categorias (separadas por vírgula):", self.cat_input)
        layout.addRow("Eixo Econômico (-1=esq, +1=dir):", self.ea_spin)
        layout.addRow("Eixo Autoritário (-1=lib, +1=aut):", self.aa_spin)
        if source: layout.addRow("", self.active_check)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_data(self):
        active = int(self.active_check.isChecked()) if hasattr(self, "active_check") else 1
        return {"name":self.name_input.text().strip(),"url":self.url_input.text().strip(),
                "category":self.cat_input.text().strip() or "geral","active":active,
                "economic_axis":self.ea_spin.value(),"authority_axis":self.aa_spin.value()}


class _SearchSourceDialog(QDialog):
    """Buscador Inteligente de Fontes RSS conectado à API pública do Feedly"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buscador de Fontes na Internet")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)
        
        layout = QVBoxLayout(self)
        
        # Barra de Pesquisa
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Digite um tema (ex: astronomia, culinária, política)... e tecle Enter")
        self.search_input.returnPressed.connect(self._search_web)
        
        self.search_btn = QPushButton("Pesquisar na Web")
        self.search_btn.clicked.connect(self._search_web)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)
        
        # Resultados
        self.results_list = QListWidget()
        self.results_list.setWordWrap(True)
        self.results_list.setSpacing(4)
        layout.addWidget(self.results_list)
        
        # Botões inferiores
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("+ Adicionar Fonte Selecionada")
        self.add_btn.setObjectName("btnPrimary")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._add_selected)
        
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addWidget(self.add_btn)
        layout.addLayout(btn_layout)
        
        self.results_list.itemSelectionChanged.connect(
            lambda: self.add_btn.setEnabled(bool(self.results_list.selectedItems()))
        )

    def _search_web(self):
        query = self.search_input.text().strip()
        if not query:
            return

        from PyQt6.QtWidgets import QApplication
        import httpx

        # Atualiza a interface instantaneamente para mostrar que está carregando
        self.results_list.clear()
        self.results_list.addItem("Buscando na internet... ⏳")
        QApplication.processEvents() 
        
        try:
            # NOVO: Limite aumentado de 20 para 100 resultados na API do Feedly
            url = f"https://cloud.feedly.com/v3/search/feeds?query={query}&count=100"
            resp = httpx.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            self.results_list.clear()
            results = data.get("results", [])
            
            if not results:
                self.results_list.addItem("Nenhuma fonte RSS encontrada para este tema na internet.")
                return
                
            for item in results:
                name = item.get("title", "Sem Nome")
                feed_id = item.get("feedId", "")
                
                if feed_id.startswith("feed/"):
                    feed_url = feed_id[5:]
                else:
                    continue
                
                description = item.get("description", "")[:100]
                desc_text = f" - {description}..." if description else ""
                
                list_item = QListWidgetItem(f"📰 {name}{desc_text}\n🔗 {feed_url}")
                
                # Associa a categoria principal pesquisada ao item
                list_item.setData(Qt.ItemDataRole.UserRole, {
                    "name": name,
                    "url": feed_url,
                    "cat": query 
                })
                self.results_list.addItem(list_item)
                
        except Exception as e:
            self.results_list.clear()
            self.results_list.addItem(f"Erro ao buscar na internet. Verifique sua conexão.\nDetalhe: {e}")

    def _add_selected(self):
        selected = self.results_list.currentItem()
        if not selected or not selected.data(Qt.ItemDataRole.UserRole):
            return
            
        data = selected.data(Qt.ItemDataRole.UserRole)
        from core.fetcher import add_custom_source
        
        self.add_btn.setText("Adicionando...")
        self.add_btn.setEnabled(False)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        result = add_custom_source(data["name"], data["url"], data["cat"])
        if result.get("success"):
            QMessageBox.information(self, "Sucesso", f"'{data['name']}' adicionado à sua lista!")
            
            # NOVO: Restaura o botão e NÃO fecha a janela, permitindo continuar adicionando
            self.add_btn.setText("+ Adicionar Fonte Selecionada")
            self.add_btn.setEnabled(True)
            
            # Avisa a tela de fontes (que está atrás) para recarregar a lista silenciosamente
            if hasattr(self.parent(), 'reload'):
                self.parent().reload()
        else:
            QMessageBox.warning(self, "Aviso", f"Não foi possível adicionar o feed:\n{result.get('error')}")
            self.add_btn.setText("+ Adicionar Fonte Selecionada")
            self.add_btn.setEnabled(True)