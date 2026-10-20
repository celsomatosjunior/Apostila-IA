"""Execução em segundo plano com sinais Qt."""
from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from .. import logs

log = logs.get("gui")


class GerarThread(QThread):
    progresso = Signal(dict)
    status = Signal(str)
    memoria = Signal(object)
    concluido = Signal(object)
    falhou = Signal(str)
    cancelado = Signal()

    def __init__(self, txts, pdfs, destino, settings, hw, controle):
        super().__init__()
        self.args = (txts, pdfs, destino, settings, hw)
        self.ctl = controle

    def run(self):
        from .. import servico
        from ..pipeline.orquestrador import Cancelado
        txts, pdfs, destino, s, hw = self.args
        try:
            r = servico.gerar(txts, pdfs, destino, s, hw=hw, on_progress=self.progresso.emit,
                              on_status=self.status.emit, on_memoria=self.memoria.emit, controle=self.ctl)
            self.concluido.emit(r)
        except Cancelado:
            self.cancelado.emit()
        except Exception as e:  # noqa: BLE001
            log.exception("Falha na geração")
            self.falhou.emit(str(e))


class FuncThread(QThread):
    """Executa uma função em segundo plano (downloads, diagnóstico)."""
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(str, object, object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.fn(*self.args, self.progress.emit, self.cancel))
        except Exception as e:  # noqa: BLE001
            log.exception("Tarefa em segundo plano falhou")
            self.failed.emit(str(e))
