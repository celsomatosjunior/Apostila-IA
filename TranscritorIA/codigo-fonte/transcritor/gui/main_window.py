"""Janela principal."""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .. import APP_TITLE, audio, backend, checkpoint, hardware, logs, media, paths
from ..pipeline import Controller, FileTask, QueueRunner
from ..settings import Settings
from .dialogs import SettingsDialog, SetupDialog, open_path
from .widgets import LessonList, LessonRow
from .worker import Bridge, FuncThread, QueueThread

log = logs.get("gui")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.s = Settings.load()
        self.hw: Optional[hardware.HardwareInfo] = None
        self.mgr: Optional[backend.EngineManager] = None
        self.ctl: Optional[Controller] = None
        self.thread: Optional[QueueThread] = None
        self.tasks: List[FileTask] = []
        self.running = False
        self._resume_checked = False
        self.setWindowTitle(APP_TITLE)
        icon = paths.assets_dir() / "icone.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1040, 720)
        self.setMinimumSize(820, 560)
        self._build()
        self.bridge = Bridge()
        self._wire()
        QTimer.singleShot(50, self._detect_hardware)

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(14)

        head = QHBoxLayout()
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel("Transcritor IA Local")
        title.setObjectName("title")
        sub = QLabel("Aulas transcritas neste computador. Nenhum áudio sai da sua máquina.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox, 1)
        plab = QLabel("Uso do computador")
        plab.setObjectName("hwKey")
        self.profile = QComboBox()
        self.profile.addItem("Turbo", "turbo")
        self.profile.addItem("Trabalho (PC livre)", "trabalho")
        self.profile.setCurrentIndex(0 if self.s.profile == "turbo" else 1)
        self.profile.setMinimumWidth(170)
        self.profile.setToolTip("Turbo usa todos os recursos. Trabalho reserva CPU e GPU e reduz a prioridade, "
                                "para você continuar usando o computador.")
        self.btn_settings = QPushButton("Configurações")
        head.addWidget(plab)
        head.addWidget(self.profile)
        head.addSpacing(8)
        head.addWidget(self.btn_settings)
        v.addLayout(head)

        # painel de hardware — preenchido somente com dados detectados
        self.hw_panel = QFrame()
        self.hw_panel.setObjectName("hwPanel")
        g = QGridLayout(self.hw_panel)
        g.setContentsMargins(16, 10, 16, 10)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(4)
        self.hw_vals = {}
        keys = [("gpu", "GPU"), ("vram", "VRAM"), ("aceleracao", "Aceleração"),
                ("cpu", "CPU"), ("ram", "RAM"), ("modelo", "Modelo")]
        for n, (k, lab) in enumerate(keys):
            kl = QLabel(lab)
            kl.setObjectName("hwKey")
            vl = QLabel("detectando…")
            vl.setObjectName("hwVal")
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            r, c = divmod(n, 3)
            g.addWidget(kl, r, c * 2)
            g.addWidget(vl, r, c * 2 + 1)
            g.setColumnStretch(c * 2 + 1, 1)
            self.hw_vals[k] = vl
        v.addWidget(self.hw_panel)

        self.lessons = LessonList()
        v.addWidget(self.lessons, 1)

        self.notice = QLabel("")
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        v.addWidget(self.notice)

        dest = QHBoxLayout()
        dk = QLabel("Salvar os textos em")
        dk.setObjectName("hwKey")
        self.dest_lbl = QLabel(self.s.output_dir or "escolha uma pasta")
        self.dest_lbl.setObjectName("hwVal")
        self.btn_dest = QPushButton("Escolher pasta de destino")
        dest.addWidget(dk)
        dest.addWidget(self.dest_lbl, 1)
        dest.addWidget(self.btn_dest)
        v.addLayout(dest)

        prog = QHBoxLayout()
        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.overall.setTextVisible(False)
        self.overall.setFixedHeight(8)
        prog.addWidget(self.overall, 1)
        self.speed = QLabel("")
        self.speed.setObjectName("metric")
        self.eta = QLabel("")
        self.eta.setObjectName("metric")
        self.speed.setToolTip("Quantos minutos de aula são transcritos por minuto real")
        prog.addSpacing(12)
        prog.addWidget(self.speed)
        prog.addSpacing(12)
        prog.addWidget(self.eta)
        v.addLayout(prog)
        self.status = QLabel("Pronto.")
        self.status.setObjectName("statusLine")
        v.addWidget(self.status)

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Adicionar áudio ou vídeo")
        self.btn_clear = QPushButton("Limpar lista")
        self.btn_pause = QPushButton("Pausar")
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("danger")
        self.btn_start = QPushButton("Iniciar transcrição")
        self.btn_start.setObjectName("primary")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_clear)
        btns.addStretch()
        btns.addWidget(self.btn_pause)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_start)
        v.addLayout(btns)
        self._set_running(False)

    def _wire(self):
        self.btn_add.clicked.connect(self._pick_files)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_dest.clicked.connect(self._pick_dest)
        self.btn_start.clicked.connect(self._start)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_settings.clicked.connect(self._settings)
        self.profile.currentIndexChanged.connect(self._profile_changed)
        self.lessons.files_dropped.connect(self.add_paths)
        b = self.bridge
        b.status_sig.connect(self.status.setText)
        b.notice_sig.connect(self._show_notice)
        b.started_sig.connect(lambda i: self._row(i).set_status("preparando"))
        b.progress_sig.connect(lambda i, f: self._row(i).set_status("transcrevendo", f))
        b.eta_sig.connect(lambda i, e: self._row(i).set_eta(e))
        b.planned_sig.connect(lambda i, d, spans: self._row(i).strip.set_plan(d, spans))
        b.chunks_sig.connect(lambda i, ids: self._row(i).strip.mark(ids))
        b.done_sig.connect(lambda i: self._row(i).set_status("concluido"))
        b.error_sig.connect(lambda i, e: self._row(i).set_status("erro", detail=e))
        b.overall_sig.connect(self._overall)
        b.engine_sig.connect(self._engine_info)
        b.finished_sig.connect(self._finished)

    def _row(self, i) -> LessonRow:
        return self.lessons.rows[i]

    # ------------------------------------------------------------------ hardware
    def _detect_hardware(self):
        self.status.setText("Detectando o hardware…")
        self.hw_th = FuncThread(lambda progress, cancel: hardware.detect())
        self.hw_th.result.connect(self._hw_ready)
        self.hw_th.failed.connect(lambda m: self.status.setText(f"Falha ao detectar hardware: {m}"))
        self.hw_th.start()

    def _hw_ready(self, hw):
        self.hw = hw
        g = hw.best_gpu()
        self.hw_vals["cpu"].setText(f"{hw.cpu_name} ({hw.cores_physical} núcleos, {hw.threads} threads)")
        self.hw_vals["ram"].setText(f"{hw.ram_total_mb / 1024:.0f} GB")
        self.hw_vals["gpu"].setText(g.name if g else "nenhuma placa compatível")
        self.hw_vals["vram"].setText(f"{g.vram_total_mb / 1024:.0f} GB" if g and g.vram_total_mb else "—")
        cands = backend.build_candidates(hw, self.s.model, self.s.engine, self.s.profile)
        first = cands[0]
        from .. import models
        self.hw_vals["aceleracao"].setText(f"{first.accel} (será confirmada no primeiro uso)")
        self.hw_vals["modelo"].setText(models.MODELS[first.model_key].label.split(" (")[0])
        self.status.setText("Pronto. Adicione as aulas e escolha onde salvar os textos.")
        QTimer.singleShot(100, self._offer_resume)

    def _engine_info(self, info: dict):
        for k, w in self.hw_vals.items():
            if k in info and info[k]:
                w.setText(info[k])
        if info.get("gpu", "").startswith("não utilizada"):
            self.hw_vals["vram"].setText("—")

    # ------------------------------------------------------------------ fila
    def add_paths(self, items: List[str], tracks: Optional[dict] = None):
        if self.running:
            return
        files: List[Path] = []
        for i in items:
            p = Path(i)
            if p.is_dir():
                files += sorted(f for f in p.rglob("*") if f.suffix.lower() in media.MEDIA_EXTS)
            elif p.suffix.lower() in media.MEDIA_EXTS:
                files.append(p)
        known = {t.path.resolve() for t in self.tasks}
        unreadable, silent, added = [], [], []
        for f in files:
            if f.resolve() in known:
                continue
            try:
                info = media.probe(f)
            except media.MediaError:
                unreadable.append(f.name)
                continue
            if not info.tracks:
                silent.append(f.name)
                continue
            t = FileTask(f, info.duration, kind=info.kind, info=info)
            if tracks and str(f) in tracks and tracks[str(f)] is not None:
                t.track = int(tracks[str(f)])
            self.tasks.append(t)
            added.append(t)
            known.add(f.resolve())
            row = LessonRow(f, info.duration, info.kind, info)
            if row.track is not None and t.track is not None:
                row.track.setCurrentIndex(max(0, row.track.findData(t.track)))
            row.remove_requested.connect(self._remove_row)
            row.track_changed.connect(self._track_changed)
            self.lessons.add_row(row)
        if files:
            self.s.last_input_dir = str(files[0].parent)
            if not self.s.output_dir:
                self._set_dest(str(files[0].parent))
        msgs = []
        if silent:
            msgs.append(f"Sem trilha de áudio, não adicionado(s): {', '.join(silent[:3])}"
                        + ("…" if len(silent) > 3 else "") + ".")
        if unreadable:
            msgs.append(f"Arquivo(s) danificado(s) ou em formato não suportado: {', '.join(unreadable[:3])}"
                        + ("…" if len(unreadable) > 3 else "") + ".")
        amb = [t.path.name for t in added if t.info and t.info.ambiguous and t.track is None]
        if amb:
            msgs.append(f"{', '.join(amb[:2])}: há mais de uma trilha de áudio e nenhuma marcada como português. "
                        "Confira a trilha escolhida na lista.")
        if msgs:
            self._show_notice(" ".join(msgs))
        total = sum(t.duration for t in self.tasks)
        nv = sum(1 for t in self.tasks if t.kind == "video")
        tipo = f" ({nv} vídeo{'s' if nv != 1 else ''})" if nv else ""
        self.status.setText(f"{len(self.tasks)} aula(s) na fila{tipo}, {audio.fmt_hms(total)} de gravação.")

    def _track_changed(self, row: LessonRow, ordinal: int):
        i = self.lessons.rows.index(row)
        self.tasks[i].track = ordinal

    def _remove_row(self, row: LessonRow):
        if self.running:
            return
        i = self.lessons.rows.index(row)
        self.tasks.pop(i)
        self.lessons.remove_row(row)

    def _clear(self):
        for row in list(self.lessons.rows):
            self.lessons.remove_row(row)
        self.tasks.clear()
        self.overall.setValue(0)
        self.speed.setText("")
        self.eta.setText("")

    def _pick_files(self):
        allx = " ".join(f"*{e}" for e in sorted(media.MEDIA_EXTS))
        vid = " ".join(f"*{e}" for e in sorted(media.VIDEO_EXTS))
        aud = " ".join(f"*{e}" for e in sorted(media.AUDIO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Adicionar áudio ou vídeo", self.s.last_input_dir,
                                                f"Áudio e vídeo ({allx});;Vídeos ({vid});;Áudios ({aud});;"
                                                "Todos os arquivos (*)")
        if files:
            self.add_paths(files)

    def _pick_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta onde os textos serão salvos",
                                             self.s.output_dir or self.s.last_input_dir)
        if d:
            self._set_dest(d)

    def _set_dest(self, d: str):
        self.s.output_dir = d
        self.dest_lbl.setText(d)
        self.s.save()

    # ------------------------------------------------------------------ execução
    def _start(self):
        if not self.tasks or self.hw is None:
            self._show_notice("Adicione pelo menos uma aula para começar.")
            return
        if not self.s.output_dir or not Path(self.s.output_dir).is_dir():
            self._pick_dest()
            if not self.s.output_dir or not Path(self.s.output_dir).is_dir():
                return
        try:
            probe = Path(self.s.output_dir) / ".teste_escrita"
            probe.write_text("x")
            probe.unlink()
        except OSError:
            QMessageBox.warning(self, "Pasta sem permissão", "Não é possível gravar na pasta escolhida. Escolha outra.")
            return
        self.s.profile = self.profile.currentData()
        self.s.save()
        if self.mgr is None or self.mgr.model_pref != self.s.model or self.mgr.engine_pref != self.s.engine:
            if self.mgr:
                self.mgr.close()
            self.mgr = backend.EngineManager(self.hw, self.s.model, self.s.engine, self.s.profile)
        need = self.mgr.pending_downloads()
        if need:
            dlg = SetupDialog(need, self)
            if dlg.exec() != SetupDialog.Accepted:
                self.status.setText("Transcrição não iniciada: faltam componentes.")
                return
        for t, row in zip(self.tasks, self.lessons.rows):
            if t.status != "concluido":
                t.status, t.progress, t.error = "pendente", 0.0, ""
                row.set_status("pendente")
        self.ctl = Controller()
        runner = QueueRunner(self.tasks, Path(self.s.output_dir), self.s, self.mgr, self.bridge, self.ctl)
        self.thread = QueueThread(runner)
        self._t0 = time.monotonic()
        self._set_running(True)
        self.notice.hide()
        self.thread.start()

    def _toggle_pause(self):
        if not self.ctl:
            return
        if self.ctl.paused:
            self.ctl.resume()
            self.btn_pause.setText("Pausar")
            self.status.setText("Continuando…")
        else:
            self.ctl.pause()
            self.btn_pause.setText("Continuar")
            self.status.setText("Pausado. O trecho em andamento termina e o processamento aguarda.")

    def _cancel(self):
        if not self.ctl:
            return
        r = QMessageBox.question(self, "Cancelar transcrição",
                                 "Interromper agora? O que já foi transcrito fica guardado e poderá ser retomado "
                                 "depois, sem recomeçar do zero.")
        if r == QMessageBox.Yes:
            self.ctl.cancel.set()
            self.ctl.resume()
            self.status.setText("Interrompendo com segurança…")
            self.btn_cancel.setEnabled(False)

    def _profile_changed(self):
        self.s.profile = self.profile.currentData()
        self.s.save()
        if self.mgr:
            self.mgr.apply_profile(self.s.profile)

    def _set_running(self, on: bool):
        self.running = on
        self.btn_start.setEnabled(not on)
        self.btn_add.setEnabled(not on)
        self.btn_clear.setEnabled(not on)
        self.btn_dest.setEnabled(not on)
        self.btn_settings.setEnabled(not on)
        self.btn_pause.setEnabled(on)
        self.btn_cancel.setEnabled(on)
        self.btn_pause.setText("Pausar")
        for r in self.lessons.rows:
            r.set_busy(on)

    def _overall(self, frac: float, speed: float, eta):
        self.overall.setValue(int(frac * 1000))
        self.speed.setText(f"{speed:.1f}× tempo real")
        if eta is not None:
            m = int(eta // 60)
            self.eta.setText(f"faltam {m // 60} h {m % 60:02d} min" if m >= 60 else f"faltam {max(1, m)} min")

    def _show_notice(self, text: str):
        self.notice.setText(text)
        self.notice.show()

    def _finished(self, s: dict):
        self._set_running(False)
        self.overall.setValue(1000 if s.get("ok") and not s.get("erro") else self.overall.value())
        self.eta.setText("")
        elapsed = time.monotonic() - getattr(self, "_t0", time.monotonic())
        ok, err, canc = s.get("ok", 0), s.get("erro", 0), s.get("cancelado", 0)
        lines = [f"Aulas concluídas: {ok}"]
        if err:
            lines.append(f"Com erro: {err} (veja o motivo na lista)")
        if canc:
            lines.append(f"Interrompidas: {canc} (podem ser retomadas)")
        lines.append(f"Tempo total: {audio.fmt_hms(elapsed)}")
        lines.append(f"Textos em: {s.get('pasta', '')}")
        if s.get("fatal"):
            lines.append("\n" + s["fatal"])
        self.status.setText(f"Concluído: {ok} aula(s).")
        box = QMessageBox(self)
        box.setWindowTitle("Transcrição finalizada" if not canc else "Transcrição interrompida")
        box.setText("\n".join(lines))
        open_btn = box.addButton("Abrir pasta", QMessageBox.AcceptRole) if ok else None
        box.addButton("Fechar", QMessageBox.RejectRole)
        box.exec()
        if open_btn is not None and (box.clickedButton() == open_btn):
            open_path(s.get("pasta", self.s.output_dir))

    # ------------------------------------------------------------------ retomada
    def _offer_resume(self):
        if self.running or self._resume_checked:
            return
        self._resume_checked = True
        q = checkpoint.load_queue()
        if not q:
            return
        pend = [f for f in q.get("files", []) if f.get("status") not in ("concluido", "erro")
                and Path(f["path"]).exists()]
        if not pend:
            checkpoint.clear_queue()
            return
        r = QMessageBox.question(
            self, "Retomar trabalho interrompido",
            f"Há {len(pend)} aula(s) de uma transcrição anterior que não terminou.\n"
            "Retomar de onde parou? As partes já transcritas serão aproveitadas.")
        if r == QMessageBox.Yes:
            if q.get("output_dir"):
                self._set_dest(q["output_dir"])
            self.add_paths([f["path"] for f in pend], {f["path"]: f.get("track") for f in pend})
            self._start()
        else:
            checkpoint.clear_queue()

    def _settings(self):
        if self.hw is None:
            return
        dlg = SettingsDialog(self.s, self.hw, self)
        if dlg.exec():
            self._hw_ready(self.hw)

    def closeEvent(self, e):
        if self.running:
            r = QMessageBox.question(self, "Sair", "Há uma transcrição em andamento. Sair mesmo assim?\n"
                                     "O progresso fica salvo e poderá ser retomado ao abrir o programa.")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.ctl.cancel.set()
            self.ctl.resume()
            self.thread.wait(15000)
        if self.mgr:
            self.mgr.close()
        e.accept()
