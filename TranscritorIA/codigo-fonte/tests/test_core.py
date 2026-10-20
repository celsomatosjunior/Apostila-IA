"""Testes automatizados do núcleo (sem modelo de IA — motor simulado).

Cobrem: divisão inteligente, sobreposição e junção sem perdas/duplicações,
checkpoints e retomada, cancelamento, fila com múltiplas aulas, nomes especiais,
silêncio prolongado, ruído, falta de memória de vídeo e falha de GPU.
"""
import threading
from pathlib import Path

import numpy as np
import pytest

from conftest import lecture, script_of
from transcritor import backend, checkpoint, exporter, hardware, metrics, segmenter, textproc
from transcritor.engines.base import ChunkResult, GpuFailure, Seg
from transcritor.engines.fake_engine import FakeEngine
from transcritor.pipeline import Callbacks, Controller, FileTask, QueueRunner
from transcritor.settings import Settings


def words(text):
    return metrics.normalize(text)


def body_of(txt_path):
    t = Path(txt_path).read_text(encoding="utf-8")
    return t.split("TRANSCRIÇÃO", 1)[1].split("—" * 40)[0]


class Rec(Callbacks):
    def __init__(self):
        self.notices, self.errors, self.done, self.summary = [], [], [], None

    def notice(self, t):
        self.notices.append(t)

    def file_error(self, i, task):
        self.errors.append(task.error)

    def file_done(self, i, task):
        self.done.append(i)

    def finished(self, s):
        self.summary = s


def make_manager(engine, batch=4):
    hw = hardware.HardwareInfo(cpu_name="teste", cores_physical=2, threads=4, ram_total_mb=8000, ram_free_mb=6000)
    m = backend.EngineManager(hw, "tiny", "cpu", "turbo")
    choice = backend.EngineChoice("ct2", "cpu", "tiny", batch_size=batch, validated=True)
    engine.set_batch_size(batch)
    m._set(choice, engine)
    return m


def run_queue(files, out, engine, settings=None, ctl=None, batch=4):
    s = settings or Settings()
    mgr = make_manager(engine, batch)
    rec = Rec()
    tasks = [FileTask(Path(f)) for f in files]
    QueueRunner(tasks, out, s, mgr, rec, ctl or Controller()).run()
    return tasks, rec, mgr


# ---------------------------------------------------------------- segmentação
def test_chunks_respect_whisper_window_and_cover_speech():
    speech = [(1.0, 4.0), (4.5, 9.0), (12.0, 60.0), (70.0, 71.0), (200.0, 230.0)]
    sr = 16000
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.1, 240 * sr).astype(np.float32)
    ch = segmenter.plan_chunks(speech, 240.0, a)
    assert all(c.duration <= 28.0 + 1e-6 for c in ch)
    for s, e in speech:  # toda fala coberta
        t = s
        while t < e:
            assert any(c.start <= t <= c.end for c in ch), t
            t += 0.25
    forced = [c for c in ch if c.overlap_prev > 0]
    assert forced, "fala contínua de 48 s deveria gerar sobreposição"
    assert [c.index for c in ch] == list(range(len(ch)))
    assert all(ch[i].start <= ch[i + 1].start for i in range(len(ch) - 1))


def test_long_silence_not_packed_into_chunk():
    ch = segmenter.plan_chunks([(0, 5), (40, 45)], 50.0)
    assert len(ch) == 2


def test_groups_cover_all_chunks_in_order():
    ch = segmenter.plan_chunks([(i * 10.0, i * 10.0 + 8) for i in range(100)], 1000.0)
    g = segmenter.plan_groups(ch, 8)
    flat = [i for grp in g for i in grp]
    assert flat == list(range(len(ch)))


# ---------------------------------------------------------------- sobreposição / junção
def _continuous_case(seconds=150.0, word=0.42):
    sr = 16000
    a = np.random.default_rng(1).normal(0, 0.2, int(seconds * sr)).astype(np.float32)
    script, t, k = [], 0.3, 0
    vocab = "a gestante apresenta pressao arterial elevada com proteinuria significativa".split()
    while t + word < seconds - 0.3:
        script.append((round(t, 3), round(t + word, 3), f"{vocab[k % len(vocab)]}{k}"))
        a[int((t + word) * sr):int((t + word + 0.03) * sr)] *= 0.05  # micro-pausa entre palavras
        t += word + 0.03
        k += 1
    return a, script


def test_overlap_merge_loses_and_duplicates_nothing():
    a, script = _continuous_case()
    ch = segmenter.plan_chunks([(0.0, len(a) / 16000)], len(a) / 16000, a)
    assert sum(1 for c in ch if c.overlap_prev > 0) >= 4
    eng = FakeEngine(script)
    res = {r.index: r for r in eng.transcribe(a, ch, None)}
    merged = textproc.merge(ch, res)
    got = " ".join(s.text for s in merged).split()
    expected = [w for _, _, w in script]
    assert got == expected


def test_merge_requires_every_chunk():
    ch = [segmenter.Chunk(0, 0, 10), segmenter.Chunk(1, 10, 20)]
    with pytest.raises(ValueError):
        textproc.merge(ch, {0: ChunkResult(0, [])})


# ---------------------------------------------------------------- limpeza
def test_hallucination_and_repetition_cleanup():
    segs = [
        Seg(0, 5, " Bom dia, pessoal.", -0.2, 0.01),
        Seg(5, 8, " Legendas pela comunidade Amara.org", -1.3, 0.8),
        Seg(8, 12, " o útero o útero o útero o útero o útero o útero", -0.3, 0.1),
        Seg(12, 14, " Vamos começar.", -0.2, 0.0),
        Seg(14, 16, " Vamos começar.", -0.2, 0.0),
        Seg(16, 18, " Vamos começar.", -0.2, 0.0),
        Seg(18, 20, " palavra duvidosa", -1.2, 0.2),
    ]
    out = textproc.clean(segs)
    txt = " ".join(s.text for s in out)
    assert "Amara" not in txt
    assert txt.count("o útero") == 2
    assert txt.count("Vamos começar.") == 2
    assert "[trecho incerto]" in txt
    # o professor dizendo "obrigado por assistir" com confiança alta é mantido
    keep = textproc.clean([Seg(0, 3, " Obrigado por assistir a aula de hoje com tanta atenção, pessoal", -0.1, 0.0)])
    assert keep


def test_paragraphs_split_on_pauses():
    segs = [Seg(0, 2, "Primeira frase."), Seg(2.2, 4, "Segunda."), Seg(9, 10, "Depois da pausa.")]
    p = textproc.paragraphs(segs)
    assert len(p) == 2 and p[0].text == "Primeira frase. Segunda."


# ---------------------------------------------------------------- exportação
def test_unique_names_and_special_characters(tmp_path):
    reserved = set()
    a = exporter.unique_path(tmp_path, 'Aula: Fisiologia/Cardio? "1"', ".txt", reserved)
    b = exporter.unique_path(tmp_path, 'Aula: Fisiologia/Cardio? "1"', ".txt", reserved)
    assert a != b and ":" not in a.name and "?" not in a.name
    exporter.atomic_write(a, "ção é ü")
    assert a.read_text(encoding="utf-8") == "ção é ü".replace("\n", "\r\n")
    assert not list(tmp_path.glob("*.tmp"))


def test_srt_format():
    s = exporter.build_srt([Seg(0.0, 1.5, "Olá"), Seg(3661.2, 3662.0, "fim")])
    assert "00:00:00,000 --> 00:00:01,500" in s and "01:01:01,200" in s


def test_wer():
    assert metrics.wer("a pré-eclâmpsia é grave", "A pre-eclampsia é grave.") == 0.0
    assert abs(metrics.wer("um dois tres quatro", "um tres quatro") - 0.25) < 1e-9


# ---------------------------------------------------------------- ponta a ponta (motor simulado)
def test_end_to_end_lecture_text_complete_and_ordered(tmp_path):
    f = lecture("aula_5min.mp3", 5)
    script = script_of(f)
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script))
    assert tasks[0].status == "concluido", rec.errors
    got = words(body_of(tasks[0].outputs[0]))
    exp = words(" ".join(w for _, _, w in script))
    assert metrics.wer(" ".join(exp), " ".join(got)) < 0.01, "texto perdido/duplicado na reconstrução"
    head = Path(tasks[0].outputs[0]).read_text(encoding="utf-8")
    assert head.startswith("AULA: AULA 5MIN") and "Duração original: 00:05:" in head


def test_noise_and_long_silence(tmp_path):
    f = lecture("aula_ruido_silencio.mp3", 3, "--ruido", "--silencio", "75")
    script = script_of(f)
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script))
    assert tasks[0].status == "concluido", rec.errors
    got = words(body_of(tasks[0].outputs[0]))
    exp = words(" ".join(w for _, _, w in script))
    assert metrics.wer(" ".join(exp), " ".join(got)) < 0.02


def test_multiple_files_same_name_and_special_chars(tmp_path):
    src = lecture("aula_5min.mp3", 5)
    d1, d2 = tmp_path / "turma A", tmp_path / "turma B"
    d1.mkdir()
    d2.mkdir()
    names = [d1 / "Aula 1 — Pré-eclâmpsia & HELLP (revisão).mp3", d2 / "Aula 1 — Pré-eclâmpsia & HELLP (revisão).mp3"]
    for n in names:
        n.write_bytes(src.read_bytes())
    out = tmp_path / "saída ç"
    out.mkdir()
    tasks, rec, _ = run_queue(names, out, FakeEngine(script_of(src)))
    assert [t.status for t in tasks] == ["concluido", "concluido"], rec.errors
    assert len({t.outputs[0] for t in tasks}) == 2
    assert all(Path(t.outputs[0]).exists() for t in tasks)


def test_bad_file_does_not_stop_queue(tmp_path):
    good = lecture("aula_5min.mp3", 5)
    bad = tmp_path / "corrompido.mp3"
    bad.write_bytes(b"isto nao e audio" * 100)
    tasks, rec, _ = run_queue([bad, good], tmp_path, FakeEngine(script_of(good)))
    assert tasks[0].status == "erro" and tasks[1].status == "concluido"


def test_crash_and_resume_from_checkpoint(tmp_path):
    f = lecture("aula_5min.mp3", 5)
    script = script_of(f)
    eng = FakeEngine(script, fail_after=10)
    tasks, rec, _ = run_queue([f], tmp_path, eng, batch=2)
    assert tasks[0].status == "erro"
    first = set(eng.chunks_seen)
    job = checkpoint.Job(f, "tiny")
    plan = job.load_plan()
    saved = job.load_groups(plan["groups"])
    assert saved, "nenhum grupo salvo antes da queda"
    eng2 = FakeEngine(script)
    tasks2, rec2, _ = run_queue([f], tmp_path, eng2, batch=2)
    assert tasks2[0].status == "concluido"
    assert tasks2[0].resumed_groups == len(saved)
    redone = set(eng2.chunks_seen)
    done_before = {i for g in saved.values() for i in g}
    assert not (redone & done_before), "blocos já salvos foram reprocessados"
    got = words(body_of(tasks2[0].outputs[0]))
    assert metrics.wer(" ".join(w for _, _, w in script), " ".join(got)) < 0.01
    assert not job.dir.exists(), "temporários não foram removidos ao concluir"


def test_corrupted_checkpoint_is_discarded(tmp_path):
    f = lecture("aula_5min.mp3", 5)
    script = script_of(f)
    run_queue([f], tmp_path, FakeEngine(script, fail_after=12), batch=2)
    job = checkpoint.Job(f, "tiny")
    g = sorted(job.dir.glob("grupo_*.json"))
    assert g
    g[0].write_text("{corrompido", encoding="utf-8")
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script), batch=2)
    assert tasks[0].status == "concluido"
    got = words(body_of(tasks[0].outputs[0]))
    assert metrics.wer(" ".join(w for _, _, w in script), " ".join(got)) < 0.01


def test_cancel_then_resume(tmp_path):
    f = lecture("aula_5min.mp3", 5)
    script = script_of(f)
    ctl = Controller()
    eng = FakeEngine(script, delay=0.05)
    timer = threading.Timer(0.8, ctl.cancel.set)
    timer.start()
    tasks, rec, _ = run_queue([f], tmp_path, eng, ctl=ctl, batch=2)
    assert tasks[0].status == "cancelado"
    assert not list(tmp_path.glob("*.txt")), "texto incompleto não pode ser salvo como final"
    assert checkpoint.load_queue() is not None, "fila pendente deve ficar registrada para retomada"
    tasks2, _, _ = run_queue([f], tmp_path, FakeEngine(script), batch=2)
    assert tasks2[0].status == "concluido"


def test_pause_and_continue(tmp_path):
    f = lecture("aula_5min.mp3", 5)
    ctl = Controller()
    ctl.pause()
    eng = FakeEngine(script_of(f))
    th = threading.Thread(target=run_queue, args=([f], tmp_path, eng), kwargs={"ctl": ctl})
    th.start()
    th.join(2.5)
    assert th.is_alive() and not eng.chunks_seen, "processou durante a pausa"
    ctl.resume()
    th.join(30)
    assert not th.is_alive() and eng.chunks_seen


def test_gpu_out_of_memory_reduces_batch(tmp_path):
    f = lecture("aula_5min.mp3", 5)
    eng = FakeEngine(script_of(f), oom_above_batch=2)
    tasks, rec, mgr = run_queue([f], tmp_path, eng, batch=8)
    assert tasks[0].status == "concluido"
    assert eng.batch_size <= 2
    assert any("lote reduzido" in n for n in rec.notices)


def test_gpu_failure_falls_back_to_cpu(tmp_path, monkeypatch):
    f = lecture("aula_5min.mp3", 5)
    script = script_of(f)

    class BrokenGpu(FakeEngine):
        def transcribe(self, *a, **k):
            raise GpuFailure("CUDA failed: no kernel image is available")

    hw = hardware.HardwareInfo(cpu_name="teste", cores_physical=2, threads=4, ram_total_mb=8000)
    mgr = backend.EngineManager(hw, "tiny", "auto", "turbo")
    mgr._set(backend.EngineChoice("ct2", "cuda", "tiny", batch_size=8, gpu_name="RTX teste"), BrokenGpu(script))
    monkeypatch.setattr(backend, "make_engine", lambda choice, work_dir=None: FakeEngine(script))
    rec = Rec()
    tasks = [FileTask(f)]
    QueueRunner(tasks, tmp_path, Settings(), mgr, rec, Controller()).run()
    assert tasks[0].status == "concluido"
    assert mgr.choice.device == "cpu"
    assert mgr.info()["gpu"].startswith("não utilizada"), "nunca indicar GPU quando roda na CPU"
    assert any("CPU" in n for n in rec.notices)


def test_insufficient_ram_reports_error(tmp_path, monkeypatch):
    f = lecture("aula_5min.mp3", 5)
    import transcritor.pipeline as pl

    class VM:
        available = 50 * 2**20
    monkeypatch.setattr(pl.psutil, "virtual_memory", lambda: VM())
    tasks, rec, _ = run_queue([f], tmp_path, FakeEngine(script_of(f)))
    assert tasks[0].status == "erro" and "Memória RAM insuficiente" in tasks[0].error


def test_hardware_detection_runs():
    hw = hardware.detect()
    assert hw.threads >= 1 and hw.ram_total_mb > 0 and hw.cpu_name
    assert len(hw.fingerprint()) == 16


def test_candidates_never_claim_gpu_without_gpu():
    hw = hardware.HardwareInfo(cpu_name="x", cores_physical=4, threads=8, ram_total_mb=32000)
    c = backend.build_candidates(hw)
    assert [x.device for x in c] == ["cpu"]
    hw.gpus = [hardware.GPUInfo("nvidia", "NVIDIA GeForce RTX 3070", 8192, 7000)]
    c = backend.build_candidates(hw)
    assert c[0].device == "cuda" and c[0].model_key == "large-v3" and c[-1].device == "cpu"
    hw.gpus = [hardware.GPUInfo("amd", "AMD Radeon RX 9070 XT", 16304)]
    c = backend.build_candidates(hw)
    assert c[0].device in ("vulkan", "cpu")


def test_single_long_word_overlap_removed_but_short_kept():
    ch = [segmenter.Chunk(0, 0, 10), segmenter.Chunk(1, 8.5, 20, overlap_prev=1.5, forced=True)]
    res = {0: ChunkResult(0, [Seg(0, 9.8, " restrição de crescimento fetal.")]),
           1: ChunkResult(1, [Seg(9.0, 15, " fetal. O sulfato de magnésio")])}
    txt = " ".join(s.text.strip() for s in textproc.merge(ch, res))
    assert txt.count("fetal") == 1
    res[0] = ChunkResult(0, [Seg(0, 9.8, " o uso de")])
    res[1] = ChunkResult(1, [Seg(9.0, 15, " de magnésio")])
    txt = " ".join(s.text.strip() for s in textproc.merge(ch, res))
    assert txt.split().count("de") == 2  # palavra funcional curta: não remove sem evidência
