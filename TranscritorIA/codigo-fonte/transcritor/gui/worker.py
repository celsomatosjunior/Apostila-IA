"""Ponte entre o núcleo (threads Python) e a interface (sinais Qt)."""
from __future__ import annotations

import threading
from PySide6.QtCore import QObject, QThread, Signal

from .. import logs
from ..pipeline import Callbacks, QueueRunner

log = logs.get("gui")


class Bridge(QObject, Callbacks):
    status_sig = Signal(str)
    notice_sig = Signal(str)
    started_sig = Signal(int)
    progress_sig = Signal(int, float)
    eta_sig = Signal(int, object)
    planned_sig = Signal(int, float, list)
    chunks_sig = Signal(int, list)
    done_sig = Signal(int)
    error_sig = Signal(int, str)
    overall_sig = Signal(float, float, object)
    engine_sig = Signal(dict)
    finished_sig = Signal(dict)

    def status(self, t): self.status_sig.emit(t)
    def notice(self, t): self.notice_sig.emit(t)
    def file_started(self, i): self.started_sig.emit(i)
    def file_progress(self, i, f): self.progress_sig.emit(i, f)
    def file_eta(self, i, e): self.eta_sig.emit(i, e)
    def file_planned(self, i, d, spans): self.planned_sig.emit(i, d, spans)
    def chunks_done(self, i, ids): self.chunks_sig.emit(i, ids)
    def file_done(self, i, task): self.done_sig.emit(i)
    def file_error(self, i, task): self.error_sig.emit(i, task.error)
    def overall(self, f, s, eta): self.overall_sig.emit(f, s, eta)
    def engine_ready(self, info): self.engine_sig.emit(info)
    def finished(self, s): self.finished_sig.emit(s)


class QueueThread(QThread):
    def __init__(self, runner: QueueRunner):
        super().__init__()
        self.runner = runner

    def run(self):
        try:
            self.runner.run()
        except Exception as e:  # noqa: BLE001
            log.exception("Falha na fila")
            self.runner.cb.finished({"fatal": str(e), "ok": 0, "erro": len(self.runner.tasks),
                                     "cancelado": 0, "tempo_total": 0, "pasta": str(self.runner.output_dir),
                                     "eventos": []})


class FuncThread(QThread):
    """Executa uma função em segundo plano (downloads, testes)."""
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int, int)

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
