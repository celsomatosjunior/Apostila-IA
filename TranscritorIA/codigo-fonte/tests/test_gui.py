"""Interface gráfica: fila real em thread, sinais, faixa da aula e mensagem final (motor simulado)."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from conftest import lecture, script_of  # noqa: E402
from test_core import make_manager  # noqa: E402
from transcritor.engines.fake_engine import FakeEngine  # noqa: E402


def test_gui_full_queue(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from transcritor.gui.main_window import MainWindow

    shown = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.setdefault("text", self.text()) and 0)
    f = lecture("aula_5min.mp3", 5)
    w = MainWindow()
    import time
    t0 = time.time()
    while w.hw is None and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.05)
    assert w.hw is not None
    mgr = make_manager(FakeEngine(script_of(f), delay=0.01), batch=4)
    mgr.pending_downloads = lambda: []
    w.mgr = mgr
    w.mgr.model_pref, w.mgr.engine_pref = w.s.model, w.s.engine
    w.add_paths([str(f)])
    w._set_dest(str(tmp_path))
    w._start()
    assert w.running
    for _ in range(600):
        app.processEvents()
        if not w.running:
            break
        w.thread.wait(50)
    app.processEvents()
    assert not w.running
    assert "Aulas concluídas: 1" in shown.get("text", "")
    row = w.lessons.rows[0]
    assert row.strip.state == "concluido" and len(row.strip.done) == len(row.strip.spans)
    assert list(Path(tmp_path).glob("*.txt"))


def test_gui_accepts_audio_and_video_and_refuses_silent_video(tmp_path):
    app = QApplication.instance() or QApplication([])
    import sys as _s
    from conftest import ROOT
    _s.path.insert(0, str(ROOT / "tools"))
    from gerar_video_teste import Trilha, make_video
    from transcritor import audio as au
    from transcritor.gui.main_window import MainWindow

    mp3 = lecture("aula_5min.mp3", 5)
    a = au.decode(mp3)
    vid = make_video(tmp_path / "Aula de Cardiologia.mp4", [Trilha(a[:16000 * 20], "por", "", True)])
    multi = make_video(tmp_path / "dupla.mkv", [Trilha(a[:16000 * 20], "eng", "", True),
                                                Trilha(a[:16000 * 20], "por", "", False)])
    mute = make_video(tmp_path / "mudo.mp4", [], video=True)
    w = MainWindow()
    assert w.btn_add.text() == "Adicionar áudio ou vídeo"
    w.add_paths([str(mp3), str(vid), str(multi), str(mute)])
    assert [t.kind for t in w.tasks] == ["audio", "video", "video"]
    assert [r.kind.text() for r in w.lessons.rows] == ["Áudio", "Vídeo", "Vídeo"]
    assert "mudo.mp4" in w.notice.text()
    row = w.lessons.rows[2]
    assert row.track is not None and row.track.currentData() == 1  # português escolhido
    row.track.setCurrentIndex(0)
    assert w.tasks[2].track == 0
    assert w.lessons.rows[0].track is None and w.lessons.rows[1].track is None
    w.close()
