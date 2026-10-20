"""Janelas auxiliares: preparação inicial (download com consentimento) e configurações."""
from __future__ import annotations

import os
import sys
from typing import List

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from .. import backend, benchmark, glossary, models, paths
from ..settings import Settings
from .worker import FuncThread


class SetupDialog(QDialog):
    """Consentimento + download dos componentes que faltam (uma única vez)."""

    def __init__(self, items: List[dict], parent=None):
        super().__init__(parent)
        self.items = items
        self.setWindowTitle("Preparação inicial")
        self.setMinimumWidth(560)
        total = sum(i["size_mb"] for i in items)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel("Para transcrever neste computador, falta baixar:")
        t.setStyleSheet("font-size: 12pt; font-weight: 600;")
        lay.addWidget(t)
        for it in items:
            lab = QLabel(f"• {it['label']} — cerca de {it['size_mb'] / 1024:.1f} GB")
            lab.setWordWrap(True)
            lay.addWidget(lab)
        info = QLabel(
            "O download é feito uma única vez, das fontes oficiais (Hugging Face e NVIDIA/PyPI), com "
            "verificação de integridade. Depois disso o programa funciona sem internet.\n"
            "Nenhum áudio, texto ou dado seu é enviado — a transcrição acontece inteiramente aqui.")
        info.setWordWrap(True)
        info.setObjectName("notice")
        lay.addWidget(info)
        self.cur = QLabel("")
        self.cur.setObjectName("statusLine")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.cur)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        row.addStretch()
        self.btn_no = QPushButton("Agora não")
        self.btn_go = QPushButton(f"Baixar {total / 1024:.1f} GB")
        self.btn_go.setObjectName("primary")
        self.btn_go.setDefault(True)
        row.addWidget(self.btn_no)
        row.addWidget(self.btn_go)
        lay.addLayout(row)
        self.btn_no.clicked.connect(self._cancel)
        self.btn_go.clicked.connect(self._start)
        self.th = None

    def _start(self):
        self.btn_go.setEnabled(False)
        self.btn_no.setText("Cancelar download")
        self.bar.show()
        self.th = FuncThread(backend.install_components, self.items)
        self.th.progress.connect(self._prog)
        self.th.result.connect(lambda _: self.accept())
        self.th.failed.connect(self._fail)
        self.th.start()

    def _prog(self, name, done, total):
        self.bar.setValue(int(1000 * done / max(1, total)))
        self.cur.setText(f"Baixando {name}: {done / 2**20:,.0f} de {total / 2**20:,.0f} MB".replace(",", "."))

    def _fail(self, msg):
        if self.th and self.th.cancel.is_set():
            self.reject()
            return
        QMessageBox.warning(self, "Download interrompido",
                            f"O download não foi concluído:\n{msg}\n\nVerifique a internet e tente de novo — "
                            "o que já foi baixado é aproveitado.")
        self.btn_go.setEnabled(True)
        self.btn_no.setText("Agora não")

    def _cancel(self):
        if self.th and self.th.isRunning():
            self.th.cancel.set()
            self.cur.setText("Cancelando…")
        else:
            self.reject()


class SettingsDialog(QDialog):
    def __init__(self, s: Settings, hw, parent=None):
        super().__init__(parent)
        self.s, self.hw = s, hw
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.model = QComboBox()
        self.model.addItem("Automático (recomendado para este computador)", "auto")
        for k in models.USER_MODELS:
            self.model.addItem(models.MODELS[k].label, k)
        self.model.setCurrentIndex(max(0, self.model.findData(s.model)))
        self.engine = QComboBox()
        for label, key in (("Automático", "auto"), ("NVIDIA CUDA", "cuda"), ("Vulkan (AMD, Intel, NVIDIA)", "vulkan"),
                           ("Somente CPU", "cpu")):
            self.engine.addItem(label, key)
        self.engine.setCurrentIndex(max(0, self.engine.findData(s.engine)))
        form.addRow("Modelo", self.model)
        form.addRow("Aceleração", self.engine)
        lay.addLayout(form)
        self.srt = QCheckBox("Gerar também legenda SRT")
        self.srt.setChecked(s.export_srt)
        self.ts = QCheckBox("Gerar também TXT com marcações de tempo por parágrafo")
        self.ts.setChecked(s.export_txt_timestamps)
        self.unc = QCheckBox("Sinalizar [trecho incerto] e [inaudível]")
        self.unc.setChecked(s.mark_uncertain)
        self.glo = QCheckBox("Usar o glossário médico para orientar a grafia dos termos")
        self.glo.setChecked(s.use_glossary)
        self.openf = QCheckBox("Abrir a pasta dos textos ao terminar")
        self.openf.setChecked(s.open_folder_when_done)
        for w in (self.srt, self.ts, self.unc, self.glo, self.openf):
            lay.addWidget(w)
        row = QHBoxLayout()
        b1 = QPushButton("Editar glossário")
        b1.clicked.connect(lambda: _open_path(glossary.user_file()))
        b2 = QPushButton("Recalibrar desempenho")
        b2.clicked.connect(self._recal)
        b3 = QPushButton("Teste de desempenho completo")
        b3.clicked.connect(self._bench)
        b4 = QPushButton("Abrir pasta de dados")
        b4.clicked.connect(lambda: _open_path(paths.data_dir()))
        for b in (b1, b2, b3, b4):
            row.addWidget(b)
        lay.addLayout(row)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumHeight(170)
        self.out.hide()
        lay.addWidget(self.out)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Salvar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _recal(self):
        backend.forget_profiles()
        QMessageBox.information(self, "Recalibrar", "A calibração será refeita na próxima transcrição.")

    def _bench(self):
        self.out.show()
        self.out.setPlainText("Executando testes reais neste computador (alguns minutos)…")

        def job(progress, cancel):
            return benchmark.run(self.hw, self.model.currentData(), lambda m: progress(m, 0, 0), cancel)
        self.th = FuncThread(job)
        self.th.progress.connect(lambda m, *_: self.out.appendPlainText(m))
        self.th.result.connect(lambda rep: self.out.setPlainText(benchmark.format_report(rep)))
        self.th.failed.connect(lambda m: self.out.appendPlainText("Falha: " + m))
        self.th.start()

    def _save(self):
        self.s.model = self.model.currentData()
        self.s.engine = self.engine.currentData()
        self.s.export_srt = self.srt.isChecked()
        self.s.export_txt_timestamps = self.ts.isChecked()
        self.s.mark_uncertain = self.unc.isChecked()
        self.s.use_glossary = self.glo.isChecked()
        self.s.open_folder_when_done = self.openf.isChecked()
        self.s.save()
        self.accept()


def _open_path(p):
    if sys.platform == "win32":
        os.startfile(str(p))  # noqa: S606
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


open_path = _open_path
