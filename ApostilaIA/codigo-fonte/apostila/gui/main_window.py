"""Janela principal do ApostilaIA."""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from .. import APP_TITLE, __version__, hardware, logs, paths
from ..llm import modelos, runtime
from ..llm.cliente import Controle
from ..pipeline.projeto import projetos_pendentes
from ..settings import PERFIS, Settings
from ..util import natural_key
from .dialogs import SettingsDialog, SetupDialog, open_path
from .worker import FuncThread, GerarThread

log = logs.get("gui")


class ArquivoLista(QListWidget):
    def __init__(self, vazio: str):
        super().__init__()
        self.vazio = vazio
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setMinimumHeight(110)
        self.setAcceptDrops(False)

    def paths(self) -> List[Path]:
        return [Path(self.item(i).data(Qt.UserRole)) for i in range(self.count())]

    def add(self, p: Path, meta: str = ""):
        if any(x == p for x in self.paths()):
            return
        it = QListWidgetItem(f"{p.name}" + (f"   —   {meta}" if meta else ""))
        it.setData(Qt.UserRole, str(p))
        it.setToolTip(str(p))
        self.addItem(it)
        self.sortItems()

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count() == 0:
            from PySide6.QtGui import QPainter
            p = QPainter(self.viewport())
            p.setPen(Qt.gray)
            p.drawText(self.viewport().rect(), Qt.AlignCenter | Qt.TextWordWrap, self.vazio)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.s = Settings.load()
        self.hw: Optional[hardware.HardwareInfo] = None
        self.ctl: Optional[Controle] = None
        self.th: Optional[GerarThread] = None
        self.t_start = 0.0
        self.setWindowTitle(f"{APP_TITLE} {__version__}")
        icon = paths.assets_dir() / "icone.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1060, 760)
        self.setMinimumSize(860, 620)
        self.setAcceptDrops(True)
        self._build()
        QTimer.singleShot(50, self._detect_hardware)

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        head = QHBoxLayout()
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel("ApostilaIA")
        title.setObjectName("title")
        sub = QLabel("Transcrição + slides da aula → apostila de estudo fiel, em PDF e DOCX. "
                     "Tudo processado neste computador.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox, 1)
        lk = QLabel("Uso do computador")
        lk.setObjectName("hwKey")
        self.modo = QComboBox()
        self.modo.addItem("Turbo", "turbo")
        self.modo.addItem("Trabalho (PC livre)", "trabalho")
        self.modo.setCurrentIndex(0 if self.s.modo == "turbo" else 1)
        self.modo.setToolTip("Turbo usa todos os recursos. Trabalho reduz a prioridade, usa metade dos núcleos e "
                             "deixa mais memória de vídeo livre para você continuar usando o computador.")
        self.btn_cfg = QPushButton("Configurações")
        head.addWidget(lk)
        head.addWidget(self.modo)
        head.addSpacing(8)
        head.addWidget(self.btn_cfg)
        v.addLayout(head)

        self.hw_panel = QFrame()
        self.hw_panel.setObjectName("hwPanel")
        g = QGridLayout(self.hw_panel)
        g.setContentsMargins(16, 10, 16, 10)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(4)
        self.hw_vals = {}
        keys = [("gpu", "GPU"), ("vram", "VRAM"), ("acel", "Aceleração em uso"),
                ("cpu", "CPU"), ("ram", "RAM"), ("modelos", "Modelos")]
        for n, (k, lab) in enumerate(keys):
            kl = QLabel(lab)
            kl.setObjectName("hwKey")
            vl = QLabel("detectando…")
            vl.setObjectName("hwVal")
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            r, c = divmod(n, 3)
            g.addWidget(kl, r, c * 2)
            g.addWidget(vl, r, c * 2 + 1)
            g.setColumnStretch(c * 2 + 1, 1)
            self.hw_vals[k] = vl
        v.addWidget(self.hw_panel)

        listas = QHBoxLayout()
        listas.setSpacing(14)
        col1 = QVBoxLayout()
        t1 = QLabel("1. Transcrição da aula (TXT)")
        t1.setObjectName("boxTitle")
        self.lst_txt = ArquivoLista("Arraste aqui os TXT do TranscritorIA\n(vários arquivos = partes da aula, em ordem)")
        b1 = QHBoxLayout()
        self.btn_add_txt = QPushButton("Adicionar transcrição")
        self.btn_rm_txt = QPushButton("Remover")
        b1.addWidget(self.btn_add_txt)
        b1.addWidget(self.btn_rm_txt)
        b1.addStretch()
        col1.addWidget(t1)
        col1.addWidget(self.lst_txt, 1)
        col1.addLayout(b1)
        col2 = QVBoxLayout()
        t2 = QLabel("2. Slides da aula (PDF)")
        t2.setObjectName("boxTitle")
        self.lst_pdf = ArquivoLista("Arraste aqui os PDFs dos slides\n(opcional, mas recomendado)")
        b2 = QHBoxLayout()
        self.btn_add_pdf = QPushButton("Adicionar PDFs da aula")
        self.btn_rm_pdf = QPushButton("Remover")
        b2.addWidget(self.btn_add_pdf)
        b2.addWidget(self.btn_rm_pdf)
        b2.addStretch()
        col2.addWidget(t2)
        col2.addWidget(self.lst_pdf, 1)
        col2.addLayout(b2)
        listas.addLayout(col1, 1)
        listas.addLayout(col2, 1)
        v.addLayout(listas, 1)

        opts = QHBoxLayout()
        dk = QLabel("3. Salvar em")
        dk.setObjectName("boxTitle")
        self.dest_lbl = QLabel(self.s.output_dir or "escolha uma pasta")
        self.dest_lbl.setObjectName("hwVal")
        self.btn_dest = QPushButton("Escolher pasta de destino")
        pk = QLabel("Extensão")
        pk.setObjectName("hwKey")
        self.perfil = QComboBox()
        for k, lab in PERFIS.items():
            self.perfil.addItem(lab + (" (padrão)" if k == "equilibrada" else ""), k)
        self.perfil.setCurrentIndex(max(0, self.perfil.findData(self.s.perfil)))
        self.perfil.setToolTip("Compacta: mais condensada, com tópicos e esquemas.\n"
                               "Equilibrada: todas as explicações relevantes, sem redundâncias.\n"
                               "Fiel e detalhada: mais exemplos e comentários orais, sem nada externo.")
        opts.addWidget(dk)
        opts.addWidget(self.dest_lbl, 1)
        opts.addWidget(self.btn_dest)
        opts.addSpacing(16)
        opts.addWidget(pk)
        opts.addWidget(self.perfil)
        v.addLayout(opts)

        self.notice = QLabel("")
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        v.addWidget(self.notice)

        st = QHBoxLayout()
        self.stage = QLabel("Pronto.")
        self.stage.setObjectName("stage")
        self.eta = QLabel("")
        self.eta.setObjectName("metric")
        st.addWidget(self.stage, 1)
        st.addWidget(self.eta)
        v.addLayout(st)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        v.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setObjectName("statusLine")
        self.mem = QLabel("")
        self.mem.setObjectName("statusLine")
        dl = QHBoxLayout()
        dl.addWidget(self.detail, 1)
        dl.addWidget(self.mem)
        v.addLayout(dl)

        acts = QHBoxLayout()
        self.btn_go = QPushButton("Gerar apostila")
        self.btn_go.setObjectName("primary")
        self.btn_pause = QPushButton("Pausar")
        self.btn_resume = QPushButton("Continuar")
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("danger")
        for b in (self.btn_pause, self.btn_resume, self.btn_cancel):
            b.setEnabled(False)
        acts.addStretch()
        acts.addWidget(self.btn_pause)
        acts.addWidget(self.btn_resume)
        acts.addWidget(self.btn_cancel)
        acts.addSpacing(10)
        acts.addWidget(self.btn_go)
        v.addLayout(acts)

        self.btn_add_txt.clicked.connect(self._pick_txt)
        self.btn_add_pdf.clicked.connect(self._pick_pdf)
        self.btn_rm_txt.clicked.connect(self.lst_txt.remove_selected)
        self.btn_rm_pdf.clicked.connect(self.lst_pdf.remove_selected)
        self.btn_dest.clicked.connect(self._pick_dest)
        self.btn_cfg.clicked.connect(self._settings)
        self.btn_go.clicked.connect(self._start)
        self.btn_pause.clicked.connect(self._pause)
        self.btn_resume.clicked.connect(self._resume)
        self.btn_cancel.clicked.connect(self._cancel)
        self.modo.currentIndexChanged.connect(self._save_opts)
        self.perfil.currentIndexChanged.connect(self._save_opts)

    # ------------------------------------------------------------------ arquivos
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def add_paths(self, items):
        ign = []
        for raw in items:
            p = Path(raw)
            cands = sorted(p.rglob("*"), key=lambda x: natural_key(x.name)) if p.is_dir() else [p]
            for f in cands:
                ext = f.suffix.lower()
                if ext == ".txt" and f.is_file():
                    self.lst_txt.add(f, f"{f.stat().st_size / 1024:.0f} KB")
                elif ext == ".pdf" and f.is_file():
                    self.lst_pdf.add(f, self._pdf_meta(f))
                elif f.is_file() and not p.is_dir():
                    ign.append(f.name)
        if ign:
            self._notice("Ignorados (só TXT e PDF são aceitos): " + ", ".join(ign[:6]))
        if self.lst_txt.count() and not self.s.output_dir:
            self.s.output_dir = str(self.lst_txt.paths()[0].parent)
            self.dest_lbl.setText(self.s.output_dir)

    @staticmethod
    def _pdf_meta(f: Path) -> str:
        try:
            import pymupdf
            with pymupdf.open(str(f)) as d:
                return f"{d.page_count} páginas"
        except Exception:  # noqa: BLE001
            return "PDF ilegível?"

    def _pick_txt(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Transcrições da aula", self.s.last_input_dir,
                                             "Transcrições (*.txt)")
        if fs:
            self.s.last_input_dir = str(Path(fs[0]).parent)
            self.add_paths(fs)

    def _pick_pdf(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "PDFs dos slides", self.s.last_input_dir, "PDF (*.pdf)")
        if fs:
            self.s.last_input_dir = str(Path(fs[0]).parent)
            self.add_paths(fs)

    def _pick_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta de destino", self.s.output_dir or self.s.last_input_dir)
        if d:
            self.s.output_dir = d
            self.dest_lbl.setText(d)
            self.s.save()

    def _save_opts(self):
        self.s.modo = self.modo.currentData()
        self.s.perfil = self.perfil.currentData()
        self.s.save()

    def _notice(self, txt: str):
        self.notice.setText(txt)
        self.notice.setVisible(bool(txt))

    # ------------------------------------------------------------------ hardware
    def _detect_hardware(self):
        th = FuncThread(lambda p, c: hardware.detect())
        th.result.connect(self._hw_ready)
        th.failed.connect(lambda m: self._notice("Falha ao detectar o hardware: " + m))
        self._hwth = th
        th.start()

    def _hw_ready(self, hw):
        self.hw = hw
        g = hw.best_gpu()
        if g:
            self.hw_vals["gpu"].setText(g.name + (" (integrada)" if g.integrated else ""))
            vr = f"{g.vram_total_mb / 1024:.0f} GB" if g.vram_total_mb else "n/d"
            if g.vram_free_mb is not None:
                vr += f" ({g.vram_free_mb / 1024:.1f} GB livres)"
            self.hw_vals["vram"].setText(vr)
        else:
            self.hw_vals["gpu"].setText("nenhuma GPU compatível")
            self.hw_vals["vram"].setText("—")
        self.hw_vals["cpu"].setText(f"{hw.cpu_name} — {hw.cores_physical} núcleos / {hw.threads} threads")
        self.hw_vals["ram"].setText(f"{hw.ram_total_mb / 1024:.0f} GB ({hw.ram_free_mb / 1024:.1f} GB livres)")
        self.hw_vals["acel"].setText("verificada ao carregar o modelo")
        self._update_models_label()
        QTimer.singleShot(300, self._first_run_checks)

    def _update_models_label(self):
        if not self.hw:
            return
        conj = modelos.escolher(self.hw, self.s.conjunto_modelos)
        falt = conj.faltando()
        self.hw_vals["modelos"].setText(f"{conj.label}: " + " + ".join(m.label.split(" (")[0] for m in conj.modelos)
                                        + (" — não instalado" if falt else " — instalado"))

    def _first_run_checks(self):
        conj = modelos.escolher(self.hw, self.s.conjunto_modelos)
        if conj.faltando():
            if SetupDialog(self.hw, self.s, self).exec():
                self._update_models_label()
        pend = projetos_pendentes()
        if pend:
            m = pend[0]
            nomes = ", ".join(Path(p).name for p in m["txts"])
            r = QMessageBox.question(self, "Continuar trabalho interrompido",
                                     f"Há uma apostila interrompida ({nomes}).\nDeseja carregar esses arquivos para "
                                     "continuar de onde parou? As etapas concluídas não serão refeitas.")
            if r == QMessageBox.Yes:
                self.add_paths(m["txts"] + m["pdfs"])
                if m.get("perfil"):
                    self.perfil.setCurrentIndex(max(0, self.perfil.findData(m["perfil"])))

    def _settings(self):
        if self.hw is None:
            return
        if SettingsDialog(self.s, self.hw, self).exec():
            self._update_models_label()

    # ------------------------------------------------------------------ execução
    def _running(self, on: bool):
        for w in (self.btn_go, self.btn_add_txt, self.btn_add_pdf, self.btn_rm_txt, self.btn_rm_pdf, self.btn_dest,
                  self.perfil, self.modo, self.btn_cfg):
            w.setEnabled(not on)
        self.btn_pause.setEnabled(on)
        self.btn_cancel.setEnabled(on)
        self.btn_resume.setEnabled(False)
        self.setAcceptDrops(not on)

    def _start(self):
        if self.hw is None:
            return
        txts = self.lst_txt.paths()
        if not txts:
            QMessageBox.information(self, APP_TITLE, "Adicione ao menos um arquivo TXT da transcrição.")
            return
        if not self.s.output_dir:
            self._pick_dest()
            if not self.s.output_dir:
                return
        conj = modelos.escolher(self.hw, self.s.conjunto_modelos)
        if conj.faltando():
            if not SetupDialog(self.hw, self.s, self).exec():
                return
        if not self.lst_pdf.count():
            if QMessageBox.question(self, APP_TITLE, "Nenhum PDF de slides foi adicionado. A apostila será feita só "
                                    "com a transcrição (sem figuras). Continuar?") != QMessageBox.Yes:
                return
        self._save_opts()
        self.ctl = Controle()
        self.th = GerarThread(txts, self.lst_pdf.paths(), Path(self.s.output_dir), self.s, self.hw, self.ctl)
        self.th.progresso.connect(self._on_progress)
        self.th.status.connect(self._notice)
        self.th.memoria.connect(lambda a: self.mem.setText(a.texto()))
        self.th.concluido.connect(self._done)
        self.th.falhou.connect(self._failed)
        self.th.cancelado.connect(self._cancelled)
        self._notice("")
        self._running(True)
        self.t_start = time.monotonic()
        self.stage.setText("Iniciando…")
        self.th.start()

    def _on_progress(self, d: dict):
        if "pausado" in d:
            self.stage.setText(("Pausado — " if d["pausado"] else "") + d.get("etapa", ""))
            return
        self.stage.setText(d.get("etapa", ""))
        self.detail.setText(d.get("detalhe", ""))
        self.bar.setValue(int(d.get("frac", 0) * 1000))
        eta = d.get("eta_s")
        if eta is None:
            self.eta.setText("calculando tempo…")
        else:
            m = int(round(eta / 60))
            self.eta.setText("menos de 1 min" if m < 1 else (f"faltam ~{m // 60} h {m % 60:02d} min" if m >= 60
                                                           else f"faltam ~{m} min"))
        if d.get("gpu") and d["gpu"] != "—":
            self.hw_vals["acel"].setText(d["gpu"])

    def _pause(self):
        if self.ctl:
            self.ctl.pause.set()
            self.btn_pause.setEnabled(False)
            self.btn_resume.setEnabled(True)
            self.stage.setText("Pausando… (o progresso fica salvo)")

    def _resume(self):
        if self.ctl:
            self.ctl.pause.clear()
            self.btn_pause.setEnabled(True)
            self.btn_resume.setEnabled(False)

    def _cancel(self):
        if self.ctl and QMessageBox.question(self, APP_TITLE, "Cancelar a geração? As etapas concluídas ficam salvas "
                                             "e podem ser retomadas depois.") == QMessageBox.Yes:
            self.ctl.pause.clear()
            self.ctl.cancel.set()
            self.stage.setText("Cancelando…")

    def _done(self, r):
        self._running(False)
        self.bar.setValue(1000)
        mins = (time.monotonic() - self.t_start) / 60
        self.stage.setText(f"Apostila pronta em {mins:.0f} min — {r.paginas} páginas")
        self.eta.setText("")
        msg = (f"Apostila gerada ({r.paginas} páginas, {r.palavras} palavras).\n\n"
               f"PDF: {r.pdf.name}\nDOCX: {r.docx.name}\nRelatório de fidelidade: {r.relatorio.name}")
        if r.avisos:
            msg += "\n\nAvisos:\n- " + "\n- ".join(r.avisos)
        box = QMessageBox(self)
        box.setWindowTitle(APP_TITLE)
        box.setText(msg)
        b_pdf = box.addButton("Abrir PDF", QMessageBox.AcceptRole)
        b_dir = box.addButton("Abrir pasta", QMessageBox.ActionRole)
        box.addButton("Fechar", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is b_pdf:
            open_path(r.pdf)
        elif box.clickedButton() is b_dir or self.s.abrir_pasta_ao_concluir:
            open_path(r.pdf.parent)

    def _failed(self, msg: str):
        self._running(False)
        self.stage.setText("Falha — o progresso concluído foi preservado")
        QMessageBox.warning(self, APP_TITLE, f"Não foi possível concluir:\n\n{msg}\n\nAo tentar de novo, o programa "
                            "continua de onde parou. Detalhes no log (Configurações → Abrir logs).")

    def _cancelled(self):
        self._running(False)
        self.stage.setText("Cancelado. Para continuar depois, clique em Gerar apostila com os mesmos arquivos.")
        self.eta.setText("")

    def closeEvent(self, e):
        if self.th and self.th.isRunning():
            if QMessageBox.question(self, APP_TITLE, "Há uma apostila em geração. Fechar mesmo assim? "
                                    "O progresso fica salvo para continuar depois.") != QMessageBox.Yes:
                e.ignore()
                return
            self.ctl.cancel.set()
            self.th.wait(20000)
        e.accept()
