#!/usr/bin/env python3
"""
Cronos — Leitor de Notícias v1.2
Ponto de entrada principal.
"""
import sys
import os
import traceback
import datetime
from pathlib import Path

# Adiciona src ao path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

def global_exception_handler(exc_type, exc_value, exc_tb):
    """Captura erros fatais e salva em um arquivo de log."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    log_path = BASE_DIR / "error_log.txt"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n" + "="*50 + "\n")
        f.write(f"CRASH EM: {datetime.datetime.now()}\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    
    # Imprime no terminal também para garantir
    traceback.print_exception(exc_type, exc_value, exc_tb)

def main():
    sys.excepthook = global_exception_handler
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    app = QApplication(sys.argv)
    # Ícone da janela (evita aviso QSystemTrayIcon::setVisible: No Icon set)
    try:
        from pathlib import Path as _Path
        _icon_path = _Path(__file__).parent / "src" / "assets" / "icons" / "cronos.png"
        if _icon_path.exists():
            from PyQt6.QtGui import QIcon as _QIcon
            app.setWindowIcon(_QIcon(str(_icon_path)))
        else:
            from assets.icon_data import get_icon_path as _gip
            from PyQt6.QtGui import QIcon as _QIcon
            app.setWindowIcon(_QIcon(_gip("png")))
    except Exception:
        pass
    app.setApplicationName("Cronos")
    app.setApplicationVersion("1.2")
    app.setOrganizationName("Cronos")

    # Escala HiDPI
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
