"""Testes da versão 2.0 — vídeos como fonte de áudio.

Usam vídeos reais gerados com FFmpeg (PyAV): áudio de uma aula sintética com partitura
conhecida + uma trilha de vídeo mínima. A transcrição usa o motor simulado (texto fiel ao
que foi falado em cada bloco), o que permite conferir perda/duplicação de trechos.
Os testes com FFprobe/FFmpeg do pacote usam TRANSCRITOR_FFMPEG_DIR (pulados sem ele).
"""
import hashlib
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from conftest import FIXT, ROOT, lecture, script_of
from test_core import body_of, run_queue
from transcritor import audio, checkpoint, media, metrics
from transcritor.engines.fake_engine import FakeEngine
from transcritor.pipeline import Controller

sys.path.insert(0, str(ROOT / "tools"))
from gerar_video_teste import PROFILES, Trilha, make_video  # noqa: E402

HAS_FF = bool(os.environ.get("TRANSCRITOR_FFMPEG_DIR")) and media.tool("ffprobe") is not None
needs_ff = pytest.mark.skipif(not HAS_FF, reason="FFprobe/FFmpeg do pacote não indicados (TRANSCRITOR_FFMPEG_DIR)")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def words(t):
    return " ".join(metrics.normalize(t))


def ref_text(script):
    return " ".join(w for _, _, w in script)


_cache = {}


def lecture_audio(name="aula_5min.mp3", minutes=5, *extra):
    key = (name, minutes) + extra
    if key not in _cache:
        f = lecture(name, minutes, *extra)
        _cache[key] = (audio.decode(f), script_of(f), f)
    return _cache[key]


def video(name, tracks, **kw):
    out = FIXT / "videos" / name
    if not out.exists():
        make_video(out, tracks, **kw)
    return out


def five_min_video(ext, name=None):
    a, script, _ = lecture_audio()
    return video(name or f"aula_5min{ext}", [Trilha(a, "por", "Português", True)]), script


# ------------------------------------------------------------------ 2–5 contêineres
@pytest.mark.parametrize("ext", list(PROFILES))
def test_video_containers_transcribed_like_audio(tmp_path, ext):
    f, script = five_min_video(ext)
    before = sha(f)
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script))
    t = tasks[0]
    assert t.status == "concluido", rec.errors
    assert t.kind == "video"
    out = Path(t.outputs[0])
    assert out.name == "aula_5min.txt", "TXT deve ter o mesmo nome-base do vídeo"
    w = metrics.wer(ref_text(script), body_of(out))
    assert w < 0.02, f"{ext}: WER {w:.3f}"
    assert sha(f) == before, "o arquivo original não pode ser alterado"


# ------------------------------------------------------------------ 6 sem trilha de áudio
def test_video_without_audio_track(tmp_path):
    f = video("sem_audio.mp4", [], video=True)
    info = media.probe(f)
    assert info.kind == "video" and info.tracks == []
    a, script, mp3 = lecture_audio()
    tasks, rec, _ = run_queue([f, mp3], tmp_path, FakeEngine(script))
    assert tasks[0].status == "erro" and "sem trilha de áudio" in tasks[0].error.lower()
    assert tasks[1].status == "concluido", "a fila deve continuar após o vídeo sem áudio"


# ------------------------------------------------------------------ 7 múltiplas trilhas
def test_multiple_tracks_prefers_portuguese(tmp_path):
    a, script, _ = lecture_audio()
    other, _, _ = lecture_audio("aula_ruido_silencio.mp3", 3, "--ruido", "--silencio", "75")
    f = video("multitrilha.mkv", [Trilha(other, "eng", "English", True), Trilha(a, "por", "Português", False),
                                  Trilha(other, "spa", "Español", False)])
    info = media.probe(f)
    assert len(info.tracks) == 3
    assert info.selected == 1 and "português" in info.reason and not info.ambiguous
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script))
    assert tasks[0].status == "concluido", rec.errors
    assert metrics.wer(ref_text(script), body_of(tasks[0].outputs[0])) < 0.02


def test_multiple_tracks_without_language_is_flagged_and_manual_choice_works(tmp_path):
    a, script, _ = lecture_audio()
    other, script_other, _ = lecture_audio("aula_ruido_silencio.mp3", 3, "--ruido", "--silencio", "75")
    f = video("multitrilha_sem_idioma.mp4", [Trilha(other), Trilha(a)])
    info = media.probe(f)
    assert info.ambiguous and info.selected == 0
    from test_core import make_manager
    from transcritor.pipeline import FileTask, QueueRunner
    from transcritor.settings import Settings
    from test_core import Rec
    t = FileTask(f, track=1)  # escolha manual da 2ª trilha
    QueueRunner([t], tmp_path, Settings(), make_manager(FakeEngine(script)), Rec(), Controller()).run()
    assert t.status == "concluido"
    assert metrics.wer(ref_text(script), body_of(t.outputs[0])) < 0.02
    # a outra trilha é outro trabalho (checkpoint separado)
    assert checkpoint.job_id(f, "x", 0) != checkpoint.job_id(f, "x", 1)


# ------------------------------------------------------------------ 8 vídeo com mais de 2 horas
def test_video_longer_than_two_hours(tmp_path):
    a, script, mp3 = lecture_audio("aula_150min.mp3", 150)
    f = video("aula_150min.mp4", [Trilha(a, "por", "", True)])
    before = sha(f)
    tmp_before = set(os.listdir(tempfile.gettempdir()))
    t0 = time.perf_counter()
    va = media.decode(f)
    t_video = time.perf_counter() - t0
    t0 = time.perf_counter()
    aa = media.decode(mp3)
    t_audio = time.perf_counter() - t0
    assert abs(len(va) - len(aa)) / 16000 < 1.0
    # mesmo áudio: leitura do vídeo não pode ser muito mais lenta que a do MP3 equivalente
    assert t_video < max(3 * t_audio, t_audio + 20), (t_video, t_audio)
    del va, aa
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script), batch=16)
    assert tasks[0].status == "concluido", rec.errors
    assert metrics.wer(ref_text(script), body_of(tasks[0].outputs[0])) < 0.005
    assert sha(f) == before
    new_tmp = set(os.listdir(tempfile.gettempdir())) - tmp_before
    big = [n for n in new_tmp if (Path(tempfile.gettempdir()) / n).is_file()
           and (Path(tempfile.gettempdir()) / n).stat().st_size > 50e6]
    assert not big, f"arquivo temporário grande criado: {big}"
    (FIXT / "videos" / "tempos_leitura_150min.txt").write_text(
        f"leitura MP4 (150 min): {t_video:.1f} s\nleitura MP3 equivalente: {t_audio:.1f} s\n", encoding="utf-8")


# ------------------------------------------------------------------ 9 + 10 fila mista e acentos
def test_mixed_queue_mp3_and_mp4_with_accented_names(tmp_path):
    a, script, mp3 = lecture_audio()
    src_v, _ = five_min_video(".mp4")
    d = tmp_path / "Aulas de Obstetrícia — 2º semestre"
    d.mkdir()
    v = d / "Aula de Cardiologia — Pré-eclâmpsia e síndrome HELLP (revisão nº 2).mp4"
    m = d / "Aula de Cardiologia — Pré-eclâmpsia e síndrome HELLP (revisão nº 2).mp3"
    shutil.copy(src_v, v)
    shutil.copy(mp3, m)
    out = tmp_path / "Transcrições ç"
    out.mkdir()
    tasks, rec, _ = run_queue([m, v], out, FakeEngine(script))
    assert [t.status for t in tasks] == ["concluido", "concluido"], rec.errors
    assert [t.kind for t in tasks] == ["audio", "video"]
    names = sorted(Path(t.outputs[0]).name for t in tasks)
    assert names == ["Aula de Cardiologia — Pré-eclâmpsia e síndrome HELLP (revisão nº 2) (2).txt",
                     "Aula de Cardiologia — Pré-eclâmpsia e síndrome HELLP (revisão nº 2).txt"]
    for t in tasks:
        assert metrics.wer(ref_text(script), body_of(t.outputs[0])) < 0.02


# ------------------------------------------------------------------ 11 interrupção e retomada
def test_video_interrupt_and_resume(tmp_path):
    f, script = five_min_video(".mp4", "retomada.mp4")
    eng = FakeEngine(script, fail_after=10)
    tasks, _, _ = run_queue([f], tmp_path, eng, batch=2)
    assert tasks[0].status == "erro"
    job = checkpoint.Job(f, "tiny", 0)
    saved = job.load_groups(job.load_plan()["groups"])
    assert saved
    eng2 = FakeEngine(script)
    tasks2, _, _ = run_queue([f], tmp_path, eng2, batch=2)
    assert tasks2[0].status == "concluido" and tasks2[0].resumed_groups == len(saved)
    assert not (set(eng2.chunks_seen) & {i for g in saved.values() for i in g})
    assert metrics.wer(ref_text(script), body_of(tasks2[0].outputs[0])) < 0.02

    # cancelamento pelo usuário no meio de um vídeo, depois retomada
    g, _ = five_min_video(".mkv", "cancelado.mkv")
    ctl = Controller()
    threading.Timer(0.8, ctl.cancel.set).start()
    t3, _, _ = run_queue([g], tmp_path, FakeEngine(script, delay=0.05), ctl=ctl, batch=2)
    assert t3[0].status == "cancelado" and not (tmp_path / "cancelado.txt").exists()
    t4, _, _ = run_queue([g], tmp_path, FakeEngine(script), batch=2)
    assert t4[0].status == "concluido"


# ------------------------------------------------------------------ 12 arquivos danificados
def test_corrupted_and_incomplete_videos(tmp_path):
    f, script = five_min_video(".mkv")
    data = f.read_bytes()
    trunc = tmp_path / "incompleto.mkv"
    trunc.write_bytes(data[: int(len(data) * 0.6)])
    damaged = tmp_path / "danificado.mkv"
    b = bytearray(data)
    rng = np.random.default_rng(3)
    for pos in rng.integers(len(b) // 4, len(b) - 1000, 40):
        b[pos:pos + 200] = bytes(200)
    damaged.write_bytes(bytes(b))
    junk = tmp_path / "lixo.mp4"
    junk.write_bytes(b"\x00\x01nao e video" * 5000)
    empty = tmp_path / "vazio.mp4"
    empty.write_bytes(b"")
    mp4 = five_min_video(".mp4")[0].read_bytes()
    no_moov = tmp_path / "mp4_cortado.mp4"
    no_moov.write_bytes(mp4[: len(mp4) // 2])

    tasks, rec, _ = run_queue([trunc, damaged, junk, empty, no_moov], tmp_path, FakeEngine(script))
    st = {t.path.name: t for t in tasks}
    # incompleto: transcreve a parte legível e avisa
    assert st["incompleto.mkv"].status == "concluido"
    assert any("incompleto" in n for n in rec.notices)
    got = words(body_of(st["incompleto.mkv"].outputs[0]))
    assert len(got.split()) > 0.4 * len(ref_text(script).split())
    # danificado no meio: continua e recupera a maior parte
    assert st["danificado.mkv"].status == "concluido"
    assert metrics.wer(ref_text(script), body_of(st["danificado.mkv"].outputs[0])) < 0.5
    # ilegíveis: erro claro, sem travar a fila
    for n in ("lixo.mp4", "vazio.mp4"):
        assert st[n].status == "erro" and st[n].error
    assert st["mp4_cortado.mp4"].status == "erro" and "moov" in st["mp4_cortado.mp4"].error


# ------------------------------------------------------------------ 13 sem internet
def test_video_offline(tmp_path, monkeypatch):
    f, script = five_min_video(".mov")

    def no_net(*a, **k):
        raise AssertionError("tentativa de acesso à rede durante a transcrição")
    monkeypatch.setattr(socket.socket, "connect", no_net)
    monkeypatch.setattr(socket, "create_connection", no_net)
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script))
    assert tasks[0].status == "concluido", rec.errors


# ------------------------------------------------------------------ FFprobe/FFmpeg do pacote
@needs_ff
def test_ffprobe_used_and_ffmpeg_fallback(monkeypatch):
    f, _ = five_min_video(".avi")
    info = media.probe(f)
    assert info.prober == "ffprobe"
    a = media.decode(f, info=info)

    def broken(*args, **kw):
        raise RuntimeError("simulação: leitor principal falhou")
    monkeypatch.setattr(media, "_decode_pyav", broken)
    b = media.decode(f, info=info)
    assert abs(len(a) - len(b)) < 16000
    n = min(len(a), len(b))
    assert np.corrcoef(a[:n], b[:n])[0, 1] > 0.98


@needs_ff
def test_ffprobe_and_pyav_agree_on_tracks():
    a, _, _ = lecture_audio()
    f = video("multitrilha.mkv", [])  # já criado pelo teste de múltiplas trilhas, ou cria vazio
    if not media.probe(f).tracks:
        pytest.skip("depende do vídeo multitrilha")
    i1 = media._probe_ffprobe(f, media.tool("ffprobe"))
    i2 = media._probe_pyav(f)
    assert [(t.language, t.ordinal) for t in i1.tracks] == [(t.language, t.ordinal) for t in i2.tracks]
    assert i1.has_video and i2.has_video


def test_mp3_cover_art_is_not_a_video(tmp_path):
    """MP3 com capa (imagem anexada, que o FFmpeg expõe como 'vídeo') continua sendo áudio."""
    import av
    import av.stream as avs
    _, _, mp3 = lecture_audio()
    out = tmp_path / "com_capa.mp3"
    with av.open(str(mp3)) as src, av.open(str(out), "w") as dst:
        ins = src.streams.audio[0]
        o = dst.add_stream_from_template(ins)
        v = dst.add_stream("png", rate=1)
        v.width, v.height, v.pix_fmt = 32, 32, "rgb24"
        v.disposition = avs.Disposition.attached_pic
        fr = av.VideoFrame.from_ndarray(np.zeros((32, 32, 3), np.uint8), format="rgb24")
        fr.pts = 0
        for p in list(v.encode(fr)) + list(v.encode(None)):
            p.stream = v
            dst.mux(p)
        for p in src.demux(ins):
            if p.dts is None:
                continue
            p.stream = o
            dst.mux(p)
    with av.open(str(out)) as c:
        assert any(st.type == "video" for st in c.streams), "o arquivo de teste deve conter a capa"
    info = media.probe(out)
    assert info.kind == "audio" and not info.has_video and len(info.tracks) == 1
    assert media._probe_pyav(out).has_video is False
