"""Janelas auxiliares: preparação inicial (download com consentimento) e configurações avançadas."""
from __future__ import annotations

import os
import shutil
import sys
from typing import List

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

from .. import paths, preparo
from ..llm import modelos
from ..settings import Settings
from .worker import FuncThread


def _gb(b: int) -> str:
    return f"{b / 2**30:.1f}".replace(".", ",") + " GB"


class SetupDialog(QDialog):
    """Consentimento + download do que falta (uma única vez). Depois, tudo offline."""

    def __init__(self, hw, settings: Settings, parent=None):
        super().__init__(parent)
        self.hw, self.s = hw, settings
        self.setWindowTitle("Preparação inicial — modelos de IA locais")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel("Para gerar apostilas neste computador, é preciso baixar os modelos de IA uma única vez.")
        t.setWordWrap(True)
        t.setStyleSheet("font-size: 11.5pt; font-weight: 600;")
        lay.addWidget(t)
        rec = modelos.recomendar(hw)
        form = QFormLayout()
        self.conj = QComboBox()
        for k in ("A", "B", "C"):
            c = modelos.conjunto(k)
            rotulo = f"{c.label}: {', '.join(m.label for m in c.modelos)} — {_gb(c.size)}"
            if k == rec.key:
                rotulo += "  (recomendado)"
            self.conj.addItem(rotulo, k)
        pref = settings.conjunto_modelos if settings.conjunto_modelos in ("A", "B", "C") else rec.key
        self.conj.setCurrentIndex(max(0, self.conj.findData(pref)))
        form.addRow("Modelos", self.conj)
        lay.addLayout(form)
        why = QLabel(f"Recomendação para este computador: {rec.motivo}.")
        why.setObjectName("subtitle")
        why.setWordWrap(True)
        lay.addWidget(why)
        self.cuda = QCheckBox("")
        self.cuda.setChecked(True)
        lay.addWidget(self.cuda)
        self.lista = QLabel("")
        self.lista.setWordWrap(True)
        lay.addWidget(self.lista)
        info = QLabel("Os arquivos vêm das fontes oficiais (Hugging Face e GitHub do llama.cpp) e são conferidos por "
                      "SHA-256. Nenhuma transcrição, PDF ou apostila é enviada: todo o processamento acontece aqui. "
                      "Depois do download o programa funciona sem internet.")
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
        self.btn_go = QPushButton("Baixar")
        self.btn_go.setObjectName("primary")
        self.btn_go.setDefault(True)
        row.addWidget(self.btn_no)
        row.addWidget(self.btn_go)
        lay.addLayout(row)
        self.btn_no.clicked.connect(self._cancel)
        self.btn_go.clicked.connect(self._start)
        self.conj.currentIndexChanged.connect(self._refresh)
        self.cuda.toggled.connect(self._refresh)
        self.th = None
        self._refresh()

    def _itens(self) -> List[dict]:
        itens = preparo.itens_faltando(self.hw, modelos.conjunto(self.conj.currentData()))
        return [i for i in itens if i["tipo"] != "cuda" or self.cuda.isChecked()]

    def _refresh(self):
        todos = preparo.itens_faltando(self.hw, modelos.conjunto(self.conj.currentData()))
        cuda = [i for i in todos if i["tipo"] == "cuda"]
        self.cuda.setVisible(bool(cuda))
        if cuda:
            self.cuda.setText(f"Baixar também a aceleração NVIDIA CUDA ({_gb(cuda[0]['size'])}) — mais rápida que Vulkan")
        itens = self._itens()
        if not itens:
            self.lista.setText("Tudo já está instalado.")
            self.btn_go.setText("Fechar")
            return
        self.lista.setText("\n".join(f"• {i['label']} — {_gb(i['size'])}" for i in itens))
        total = sum(i["size"] for i in itens)
        livre = shutil.disk_usage(paths.models_dir()).free
        self.btn_go.setText(f"Baixar {_gb(total)}")
        if livre < total * 1.05:
            self.lista.setText(self.lista.text() + f"\n\nEspaço livre insuficiente no disco ({_gb(livre)}).")
            self.btn_go.setEnabled(False)
        else:
            self.btn_go.setEnabled(True)

    def _start(self):
        itens = self._itens()
        self.s.conjunto_modelos = self.conj.currentData()
        self.s.consent_downloads = True
        self.s.save()
        if not itens:
            self.accept()
            return
        self.btn_go.setEnabled(False)
        self.conj.setEnabled(False)
        self.cuda.setEnabled(False)
        self.btn_no.setText("Cancelar download")
        self.bar.show()
        self.th = FuncThread(preparo.instalar, itens)
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
        self.setWindowTitle("Configurações avançadas")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        aviso = QLabel("O funcionamento padrão é automático. Altere apenas se souber o motivo.")
        aviso.setObjectName("subtitle")
        lay.addWidget(aviso)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.conj = QComboBox()
        self.conj.addItem("Automático (pelo hardware)", "auto")
        for k in ("A", "B", "C"):
            c = modelos.conjunto(k)
            self.conj.addItem(f"{c.label} — {', '.join(m.label for m in c.modelos)}", k)
        self.conj.setCurrentIndex(max(0, self.conj.findData(s.conjunto_modelos)))
        self.backend = QComboBox()
        for label, key in (("Automático", "auto"), ("NVIDIA CUDA", "cuda"), ("Vulkan (NVIDIA, AMD, Intel)", "vulkan"),
                           ("Somente CPU", "cpu")):
            self.backend.addItem(label, key)
        self.backend.setCurrentIndex(max(0, self.backend.findData(s.backend)))
        self.titulo = QLineEdit(s.titulo_manual)
        self.titulo.setPlaceholderText("automático (a partir dos slides)")
        form.addRow("Modelos", self.conj)
        form.addRow("Aceleração", self.backend)
        form.addRow("Título da apostila", self.titulo)
        lay.addLayout(form)
        self.chk = {}
        for key, txt in (("usar_visao", "Ler slides em imagem com o modelo de visão (recomendado)"),
                         ("incluir_figuras", "Incluir figuras dos slides"),
                         ("incluir_esquemas", "Criar esquemas quando sustentados pela aula"),
                         ("incluir_pontos_conferir", "Incluir apêndice “Termos e pontos a conferir”"),
                         ("mostrar_fontes_na_apostila", "Mostrar as fontes (parágrafos/slides) ao fim de cada seção"),
                         ("remover_sem_suporte", "Remover frases sem sustentação nas fontes (auditoria)"),
                         ("abrir_pasta_ao_concluir", "Abrir a pasta ao concluir")):
            c = QCheckBox(txt)
            c.setChecked(bool(getattr(s, key)))
            self.chk[key] = c
            lay.addWidget(c)
        row = QHBoxLayout()
        b1 = QPushButton("Preparar / trocar modelos")
        b1.clicked.connect(lambda: SetupDialog(self.hw, self.s, self).exec())
        b2 = QPushButton("Abrir pasta de dados")
        b2.clicked.connect(lambda: open_path(paths.data_dir()))
        b3 = QPushButton("Abrir logs")
        b3.clicked.connect(lambda: open_path(paths.logs_dir()))
        b4 = QPushButton("Apagar projetos em andamento")
        b4.clicked.connect(self._limpar)
        for b in (b1, b2, b3, b4):
            row.addWidget(b)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Salvar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _limpar(self):
        if QMessageBox.question(self, "Apagar projetos", "Apagar os checkpoints de todos os projetos? "
                                "As apostilas já geradas e os arquivos originais não são afetados.") == QMessageBox.Yes:
            shutil.rmtree(paths.jobs_dir(), ignore_errors=True)
            paths.jobs_dir()

    def _save(self):
        self.s.conjunto_modelos = self.conj.currentData()
        self.s.backend = self.backend.currentData()
        self.s.titulo_manual = self.titulo.text().strip()
        for k, c in self.chk.items():
            setattr(self.s, k, c.isChecked())
        self.s.save()
        self.accept()


def open_path(p):
    if sys.platform == "win32":
        os.startfile(str(p))  # noqa: S606
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
