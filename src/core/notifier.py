"""
Cronos - Módulo de Notificações
Dispara alertas por palavras-chave e por fonte específica.
"""

import logging
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QObject, pyqtSignal
from pathlib import Path
from .database import get_alert_rules, get_connection

logger = logging.getLogger("cronos.notifier")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ICON_PATH = BASE_DIR / "src" / "assets" / "icons" / "cronos.png"


def check_alerts(new_articles: list) -> list:
    """
    Verifica se algum novo artigo dispara algum alerta.
    Retorna lista de (article, rule) que fazem match.
    """
    rules = get_alert_rules()
    if not rules:
        return []

    matches = []
    for article in new_articles:
        title_lower = (article.get("title") or "").lower()
        source_name = (article.get("source_name") or "").lower()
        summary_lower = (article.get("summary") or "").lower()

        for rule in rules:
            value_lower = rule["value"].lower()
            if rule["type"] == "keyword":
                if value_lower in title_lower or value_lower in summary_lower:
                    matches.append((article, rule))
            elif rule["type"] == "source":
                if value_lower in source_name:
                    matches.append((article, rule))

    # Salva notificações no banco
    if matches:
        conn = get_connection()
        for article, rule in matches:
            conn.execute(
                "INSERT OR IGNORE INTO notifications (article_id, alert_rule_id) VALUES (?,?)",
                (article["id"], rule["id"])
            )
        conn.commit()
        conn.close()

    return matches


class NotificationManager(QObject):
    """Gerencia notificações do sistema via system tray."""
    notification_clicked = pyqtSignal(int)  # article_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray = None
        self._pending_articles = {}

    def setup_tray(self, app: QApplication):
        """Configura o ícone na bandeja do sistema."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray não disponível")
            return

        self.tray = QSystemTrayIcon(parent=app)

        # Ícone (fallback para ícone padrão se não existir)
        if ICON_PATH.exists():
            self.tray.setIcon(QIcon(str(ICON_PATH)))

        self.tray.setToolTip("Cronos — Leitor de Notícias")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.show()
        logger.info("System tray configurado")

    def notify_new_articles(self, matches: list):
        """Exibe notificação para artigos que fizeram match com alertas."""
        if not self.tray or not matches:
            return

        if len(matches) == 1:
            article, rule = matches[0]
            title = f"📰 Alerta: {rule['value']}"
            message = article["title"]
            self._pending_articles["last"] = article.get("id")
        else:
            title = f"📰 {len(matches)} alertas disparados"
            message = "\n".join([a["title"][:60] for a, _ in matches[:3]])
            self._pending_articles["last"] = matches[0][0].get("id")

        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def notify_fetch_complete(self, count: int):
        """Notificação discreta quando fetch completa."""
        if not self.tray or count == 0:
            return
        self.tray.setToolTip(f"Cronos — {count} novas notícias")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Emite sinal para janela principal aparecer
            pass

    def _on_message_clicked(self):
        article_id = self._pending_articles.get("last")
        if article_id:
            self.notification_clicked.emit(article_id)

    def get_unread_count(self) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM notifications WHERE is_read=0"
        ).fetchone()
        conn.close()
        return row["c"] if row else 0

    def mark_all_read(self):
        conn = get_connection()
        conn.execute("UPDATE notifications SET is_read=1")
        conn.commit()
        conn.close()
