"""Componentes visuais: lista de aulas com a faixa do tempo de cada aula."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import audio
from . import theme

STATUS_TXT = {"pendente": "Na fila", "preparando": "Lendo o áudio", "transcrevendo": "Transcrevendo",
              "concluido": "Concluída", "erro": "Erro", "cancelado": "Interrompida"}


class TimelineStrip(QWidget):
    """Faixa horizontal = duração da aula. Blocos de fala aparecem em cinza e
    ganham a cor de acento quando já foram transcritos; silêncio fica vazio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.duration = 0.0
        self.spans: Dict[int, Tuple[float, float]] = {}
        self.done: set = set()
        self.state = "pendente"

    def set_plan(self, duration: float, spans: List[tuple]):
        self.duration = duration
        self.spans = {i: (s, e) for i, s, e in spans}
        self.update()

    def mark(self, ids):
        self.done.update(ids)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 3, 0, -3)
        clip = QPainterPath()
        clip.addRoundedRect(r, 4, 4)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#E7ECF1"))
        if self.state == "concluido":
            p.fillRect(r, QColor(theme.DONE))
            return
        if not self.duration or not self.spans:
            return
        k = r.width() / self.duration
        for i, (s, e) in self.spans.items():
            col = theme.STAIN if i in self.done else theme.SPEECH
            if self.state == "erro" and i not in self.done:
                col = "#E9C9C6"
            p.fillRect(QRectF(r.left() + s * k, r.top(), max(1.0, (e - s) * k), r.height()), QColor(col))


class LessonRow(QFrame):
    remove_requested = Signal(object)

    track_changed = Signal(object, int)

    def __init__(self, path: Path, duration: float, kind: str = "audio", info=None):
        super().__init__()
        self.path = path
        self.duration = duration
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(6)
        top = QHBoxLayout()
        self.name = QLabel(path.name)
        self.name.setObjectName("lessonName")
        self.name.setToolTip(str(path))
        self.name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.kind = QLabel("Vídeo" if kind == "video" else "Áudio")
        self.kind.setObjectName("kindVideo" if kind == "video" else "kindAudio")
        self.kind.setAlignment(Qt.AlignCenter)
        self.kind.setFixedSize(52, 20)
        self.kind.setToolTip("Vídeo: somente o áudio é lido; a imagem não é processada." if kind == "video"
                             else "Arquivo de áudio")
        self.meta = QLabel(audio.fmt_hms(duration) if duration else "duração desconhecida")
        self.meta.setObjectName("lessonMeta")
        self.eta = QLabel("")
        self.eta.setObjectName("lessonMeta")
        self.eta.setMinimumWidth(96)
        self.eta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.track = None
        if info is not None and len(info.tracks) > 1:
            # escolha manual só quando há mais de uma trilha de áudio
            self.track = QComboBox()
            for t in info.tracks:
                self.track.addItem(t.label(short=True), t.ordinal)
                self.track.setItemData(self.track.count() - 1, t.label(), Qt.ToolTipRole)
            self.track.setCurrentIndex(max(0, self.track.findData(info.selected)))
            self.track.setToolTip(f"Escolhida automaticamente: {info.reason}. Troque se for outra.")
            self.track.setAccessibleName(f"Trilha de áudio de {path.name}")
            self.track.setMaximumWidth(230)
            self.track.currentIndexChanged.connect(lambda _i: self.track_changed.emit(self, self.track.currentData()))
        self.state = QLabel(STATUS_TXT["pendente"])
        self.state.setObjectName("lessonMeta")
        self.state.setMinimumWidth(150)
        self.state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.btn_rm = QPushButton("Remover")
        self.btn_rm.setFlat(True)
        self.btn_rm.setCursor(Qt.PointingHandCursor)
        self.btn_rm.setAccessibleName(f"Remover {path.name} da fila")
        self.btn_rm.clicked.connect(lambda: self.remove_requested.emit(self))
        top.addWidget(self.kind)
        top.addSpacing(6)
        top.addWidget(self.name, 1)
        if self.track is not None:
            top.addWidget(self.track)
        top.addWidget(self.meta)
        top.addWidget(self.eta)
        top.addSpacing(12)
        top.addWidget(self.state)
        top.addWidget(self.btn_rm)
        lay.addLayout(top)
        self.strip = TimelineStrip()
        lay.addWidget(self.strip)
        self.setStyleSheet(f"LessonRow {{ border-bottom: 1px solid {theme.LINE}; }}")

    def set_status(self, st: str, frac: Optional[float] = None, detail: str = ""):
        txt = STATUS_TXT.get(st, st)
        if st == "transcrevendo" and frac is not None:
            txt = f"Transcrevendo {frac:.0%}"
        if detail:
            txt = f"{txt}: {detail}"
        self.state.setText(txt[:90])
        self.state.setToolTip(detail or "")
        color = {"concluido": theme.DONE, "erro": theme.ERROR, "transcrevendo": theme.STAIN}.get(st, theme.MUTED)
        self.state.setStyleSheet(f"color: {color}; font-weight: {600 if st in ('concluido', 'erro') else 400};")
        self.strip.state = st
        self.strip.update()
        if st in ("concluido", "erro", "cancelado", "pendente"):
            self.eta.setText("")

    def set_eta(self, eta):
        if eta is None:
            self.eta.setText("")
            return
        m = int(round(eta / 60))
        self.eta.setText("menos de 1 min" if m < 1 else (f"faltam {m // 60} h {m % 60:02d} min" if m >= 60
                                                       else f"faltam {m} min"))

    def set_busy(self, busy: bool):
        self.btn_rm.setVisible(not busy)
        if self.track is not None:
            self.track.setEnabled(not busy)


class LessonList(QScrollArea):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("lessons")
        self.setWidgetResizable(True)
        self.setAcceptDrops(True)
        self.inner = QWidget()
        self.inner.setObjectName("lessonsInner")
        self.inner.setStyleSheet(f"#lessonsInner {{ background: {theme.SURFACE}; }}")
        self.vbox = QVBoxLayout(self.inner)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.addStretch()
        a = QLabel("Arraste as aulas em áudio ou vídeo para cá")
        a.setObjectName("dropHintStrong")
        a.setAlignment(Qt.AlignCenter)
        b = QLabel("Áudio: MP3, M4A, WAV, OGG, FLAC, AAC, WMA. Vídeo: MP4, MKV, AVI, MOV, WMV, WEBM, MPG, M4V, FLV.\n"
                   "Aceita pastas inteiras. Dos vídeos, somente o áudio é lido.\n"
                   "Ou use o botão “Adicionar áudio ou vídeo”.")
        b.setObjectName("dropHint")
        b.setAlignment(Qt.AlignCenter)
        el.addWidget(a)
        el.addSpacing(6)
        el.addWidget(b)
        el.addStretch()
        self.vbox.addWidget(self.empty, 1)
        self.vbox.addStretch(0)
        self.setWidget(self.inner)
        self.rows: List[LessonRow] = []

    def add_row(self, row: LessonRow):
        self.empty.hide()
        self.vbox.insertWidget(len(self.rows), row)
        self.rows.append(row)

    def remove_row(self, row: LessonRow):
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.empty.setVisible(not self.rows)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(f"#lessons {{ border: 2px dashed {theme.STAIN}; }}")

    def dragLeaveEvent(self, e):
        self.setStyleSheet("")

    def dropEvent(self, e):
        self.setStyleSheet("")
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
