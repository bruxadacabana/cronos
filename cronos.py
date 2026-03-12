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
    """Captura erros fatais, salva no log e no error_log.txt legado."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    import traceback as _tb
    tb_str = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))

    # Salva no error_log.txt (compatibilidade com versões anteriores)
    log_path = BASE_DIR / "error_log.txt"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n" + "="*50 + "\n")
        f.write(f"CRASH EM: {datetime.datetime.now()}\n")
        f.write(tb_str)

    # Tenta também usar o logger estruturado se já foi configurado
    try:
        import logging
        logging.getLogger("cronos").critical(
            f"CRASH NÃO CAPTURADO\n{tb_str}"
        )
    except Exception:
        pass

    # Imprime no terminal
    print(tb_str, file=sys.stderr)

def main():
    sys.excepthook = global_exception_handler

    # Logging centralizado — deve vir antes de qualquer import Cronos
    from core.log_setup import setup_logging
    debug_mode = "--debug" in sys.argv
    setup_logging(debug=debug_mode)

    import logging
    logger = logging.getLogger("cronos")

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    app = QApplication(sys.argv)
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
