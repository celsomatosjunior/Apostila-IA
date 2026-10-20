"""Inicialização da interface gráfica."""
from __future__ import annotations

import sys
import traceback

from .. import APP_TITLE, logs


def run(argv) -> int:
    log = logs.setup()
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import theme
    from .main_window import MainWindow

    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.QSS)

    def excepthook(t, v, tb):
        log.error("Erro não tratado: %s", "".join(traceback.format_exception(t, v, tb)))
        QMessageBox.critical(None, APP_TITLE, f"Ocorreu um erro inesperado:\n{v}\n\nDetalhes no arquivo de log.")
    sys.excepthook = excepthook

    w = MainWindow()
    w.show()
    files = [a for a in argv if not a.startswith("-")]
    if files:
        w.add_paths(files)  # permite "Abrir com…" e arrastar arquivos sobre o ícone
    return app.exec()
