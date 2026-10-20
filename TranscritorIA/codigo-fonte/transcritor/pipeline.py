"""Fila de aulas: preparação (CPU) em paralelo com a transcrição (GPU), checkpoints,
pausa/continuação/cancelamento e exportação final.

Fluxo por aula (áudio OU vídeo — 2.0):
  0. analisa o arquivo (contêiner, trilhas de áudio, idioma); vídeos são tratados como
     fonte de áudio: só a trilha escolhida é decodificada, os quadros de imagem não;
  1. decodifica o áudio e detecta a fala (CPU) — a PRÓXIMA aula é preparada em
     segundo plano enquanto a atual está na GPU;
  2. divide em blocos/grupos (ou reaproveita o plano salvo, se for retomada);
  3. transcreve grupo a grupo, salvando cada grupo em disco;
  4. une, limpa, organiza em parágrafos e grava o TXT de forma atômica;
  5. apaga os temporários daquela aula.
"""
from __future__ import annotations

import concurrent.futures as cf
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import psutil

from . import audio as audio_mod
from . import checkpoint, exporter, glossary, logs, media, models, segmenter, textproc
from .backend import EngineManager
from .engines.base import Cancelled, ChunkResult, DecodeOptions, EngineError
from .settings import Settings

log = logs.get("pipeline")


@dataclass
class FileTask:
    path: Path
    duration: float = 0.0
    status: str = "pendente"   # pendente|preparando|transcrevendo|concluido|erro|cancelado
    progress: float = 0.0
    outputs: List[str] = field(default_factory=list)
    error: str = ""
    elapsed: float = 0.0
    resumed_groups: int = 0
    kind: str = "audio"                      # "audio" | "video"
    track: Optional[int] = None              # trilha de áudio escolhida (None = automática)
    info: Optional[media.MediaInfo] = None   # resultado da análise do arquivo
    eta: Optional[float] = None              # segundos restantes desta aula

    def analyze(self) -> media.MediaInfo:
        if self.info is None:
            self.info = media.probe(self.path)
            self.kind = self.info.kind
            self.duration = self.info.duration
        return self.info

    @property
    def track_used(self) -> Optional[int]:
        if self.track is not None:
            return self.track
        return self.info.selected if self.info else None


@dataclass
class Prepared:
    audio: np.ndarray
    duration: float
    chunks: List[segmenter.Chunk]
    groups: List[List[int]]
    speech_s: float
    job: checkpoint.Job


class Callbacks:
    """Sobrescreva no GUI (sinais Qt) ou na linha de comando."""

    def status(self, text: str) -> None: ...
    def file_started(self, idx: int) -> None: ...
    def file_progress(self, idx: int, frac: float) -> None: ...
    def file_eta(self, idx: int, eta_s: Optional[float]) -> None: ...
    def file_planned(self, idx: int, duration: float, spans: list) -> None: ...
    def chunks_done(self, idx: int, chunk_ids: list) -> None: ...
    def file_done(self, idx: int, task: FileTask) -> None: ...
    def file_error(self, idx: int, task: FileTask) -> None: ...
    def overall(self, frac: float, speed_x: float, eta_s: Optional[float]) -> None: ...
    def engine_ready(self, info: Dict[str, str]) -> None: ...
    def notice(self, text: str) -> None: ...
    def finished(self, summary: dict) -> None: ...


class Controller:
    def __init__(self):
        self.cancel = threading.Event()
        self._running = threading.Event()
        self._running.set()

    def pause(self):
        self._running.clear()

    def resume(self):
        self._running.set()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def wait_if_paused(self):
        while not self._running.wait(0.2):
            if self.cancel.is_set():
                break


class QueueRunner:
    def __init__(self, tasks: List[FileTask], output_dir: Path, settings: Settings,
                 manager: EngineManager, cb: Callbacks, ctl: Controller):
        self.tasks = tasks
        self.output_dir = Path(output_dir)
        self.s = settings
        self.mgr = manager
        self.cb = cb
        self.ctl = ctl
        self.reserved: set = set()
        # velocidade observada (segundos de áudio / segundo real)
        self._audio_done = 0.0
        self._t_busy = 0.0
        self._model_key = ""

    # ------------------------------------------------------------ preparação
    def _prepare(self, task: FileTask) -> Prepared:
        info = task.analyze()
        if not info.tracks:
            raise media.NoAudioError(f"{'Vídeo' if info.kind == 'video' else 'Arquivo'} sem trilha de áudio: "
                                     "não há o que transcrever.")
        track = task.track_used or 0
        job = checkpoint.Job(task.path, self._model_key, track)
        need = audio_mod.estimated_ram_mb(task.duration or info.duration)
        free = psutil.virtual_memory().available // (1024 * 1024)
        if need > free * 0.9:
            raise MemoryError(f"Memória RAM insuficiente para esta aula: necessário ~{need} MB, "
                              f"livre {free} MB. Feche outros programas e tente novamente.")
        try:
            a = media.decode(task.path, track=track, cancel=self.ctl.cancel, info=info)
        except media.MediaError as e:
            if str(e) == "cancelado":
                raise Cancelled() from e
            raise
        duration = len(a) / audio_mod.SR
        if info.duration > 30 and duration < info.duration * 0.97 - 2:
            self.cb.notice(f"{task.path.name}: arquivo incompleto ou danificado — foi possível ler "
                           f"{audio_mod.fmt_hms(duration)} de {audio_mod.fmt_hms(info.duration)}. "
                           "O texto cobrirá apenas a parte legível.")
            log.warning("%s: lido %.0f s de %.0f s", task.path.name, duration, info.duration)
        plan = job.load_plan()
        if plan and abs(plan["duration"] - duration) < 0.5:
            return Prepared(a, duration, plan["chunks"], plan["groups"], plan["speech_s"], job)
        speech = segmenter.detect_speech(a)
        chunks = segmenter.plan_chunks(speech, duration, a)
        bs = max(1, self.mgr.full_batch)
        groups = segmenter.plan_groups(chunks, bs)
        speech_s = sum(e - s for s, e in speech)
        job.save_plan(duration, chunks, groups, speech_s)
        log.info("%s: %.0f s, fala %.0f s, %d blocos, %d grupos", task.path.name, duration, speech_s,
                 len(chunks), len(groups))
        return Prepared(a, duration, chunks, groups, speech_s, job)

    # ------------------------------------------------------------ execução
    def run(self) -> dict:
        t_start = time.monotonic()
        summary = {"ok": 0, "erro": 0, "cancelado": 0, "arquivos": [], "eventos": []}
        try:
            for t in self.tasks:
                try:
                    t.analyze()
                except media.MediaError:
                    t.kind = media.kind_from_ext(t.path)  # o erro aparece quando chegar a vez deste arquivo
            self.cb.status("Iniciando mecanismo de transcrição…")
            self.mgr.notify = self.cb.notice
            if self.mgr.engine is None:
                self.mgr.start(self.ctl.cancel)
            self._model_key = self.mgr.choice.model_key
            self.cb.engine_ready(self.mgr.info())
            self._persist_queue()
            pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="prepara")
            pending = [i for i, t in enumerate(self.tasks) if t.status not in ("concluido",)]
            futures: Dict[int, cf.Future] = {}

            def submit(i):
                if i not in futures and i < len(self.tasks):
                    self.tasks[i].status = "preparando"
                    futures[i] = pool.submit(self._prepare, self.tasks[i])

            if pending:
                submit(pending[0])
            for n, i in enumerate(pending):
                task = self.tasks[i]
                if self.ctl.cancel.is_set():
                    task.status = "cancelado"
                    continue
                self.cb.file_started(i)
                self.cb.status(f"Preparando {task.path.name} (leitura e detecção de fala)…")
                try:
                    prep = futures.pop(i).result()
                    if n + 1 < len(pending):
                        submit(pending[n + 1])  # prepara a próxima enquanto esta usa a GPU
                    self._transcribe_file(i, task, prep)
                    summary["ok"] += 1
                    self.cb.file_done(i, task)
                except Cancelled:
                    task.status = "cancelado"
                except (audio_mod.AudioError, EngineError, MemoryError, OSError, ValueError) as e:
                    if self.ctl.cancel.is_set():
                        task.status = "cancelado"
                        continue
                    task.status, task.error = "erro", str(e)
                    log.error("Falha em %s: %s", task.path, traceback.format_exc())
                    self.cb.file_error(i, task)
                    if n + 1 < len(pending):
                        submit(pending[n + 1])
                except Exception as e:  # noqa: BLE001 — nunca derruba a fila inteira
                    task.status, task.error = "erro", f"Erro inesperado: {e}"
                    log.error("Erro inesperado em %s: %s", task.path, traceback.format_exc())
                    self.cb.file_error(i, task)
                    if n + 1 < len(pending):
                        submit(pending[n + 1])
                finally:
                    self._persist_queue()
            pool.shutdown(wait=False, cancel_futures=True)
        except Cancelled:
            pass
        except EngineError as e:
            summary["fatal"] = str(e)
            for t in self.tasks:
                if t.status in ("pendente", "preparando"):
                    t.status, t.error = "erro", str(e)
        summary["cancelado"] = sum(1 for t in self.tasks if t.status in ("cancelado", "pendente", "preparando"))
        summary["erro"] = sum(1 for t in self.tasks if t.status == "erro")
        summary["ok"] = sum(1 for t in self.tasks if t.status == "concluido")
        summary["tempo_total"] = time.monotonic() - t_start
        summary["pasta"] = str(self.output_dir)
        summary["arquivos"] = [o for t in self.tasks for o in t.outputs]
        summary["eventos"] = list(self.mgr.events)
        if all(t.status == "concluido" for t in self.tasks) or not self.ctl.cancel.is_set():
            if all(t.status in ("concluido", "erro") for t in self.tasks):
                checkpoint.clear_queue()
        self.cb.finished(summary)
        return summary

    def _persist_queue(self) -> None:
        state = {"output_dir": str(self.output_dir),
                 "files": [{"path": str(t.path), "status": t.status, "track": t.track} for t in self.tasks]}
        if any(t.status not in ("concluido", "erro") for t in self.tasks):
            checkpoint.save_queue(state)

    def _remaining_audio(self, current_left: float, idx: int) -> float:
        rest = sum(t.duration * 0.9 for j, t in enumerate(self.tasks)
                   if j > idx and t.status in ("pendente", "preparando"))
        return current_left + rest

    def _transcribe_file(self, idx: int, task: FileTask, prep: Prepared) -> None:
        t0 = time.monotonic()
        task.status = "transcrevendo"
        task.duration = prep.duration
        opts = DecodeOptions(language=self.s.language, prompt=glossary.build_prompt(self.s.use_glossary),
                             beam_size=self.s.beam_size)
        by_id = {c.index: c for c in prep.chunks}
        results: Dict[int, ChunkResult] = {}
        done = prep.job.load_groups(prep.groups)
        task.resumed_groups = len(done)
        if done:
            self.cb.notice(f"{task.path.name}: retomando — {len(done)} de {len(prep.groups)} partes já estavam prontas.")
        for g in done.values():
            results.update(g)
        self.cb.file_planned(idx, prep.duration, [(c.index, c.start, c.end) for c in prep.chunks])
        if done:
            self.cb.chunks_done(idx, [i for g in done.values() for i in g])
        total = sum(c.duration for c in prep.chunks) or 1.0
        done_audio = sum(by_id[i].duration for g in done.values() for i in g)
        self.cb.status(f"Transcrevendo {task.path.name}…")

        def report_eta(left_audio: float) -> None:
            spd = self._audio_done / self._t_busy if self._t_busy > 1 else (
                self.mgr.choice.rtf if self.mgr.choice and self.mgr.choice.rtf else 0.0)
            task.eta = left_audio / spd if spd > 0 else None
            self.cb.file_eta(idx, task.eta)

        report_eta(total - done_audio)

        if hasattr(self.mgr.engine, "work_dir"):
            self.mgr.engine.work_dir = prep.job.work_dir
        for gi, ids in enumerate(prep.groups):
            if gi in done:
                continue
            self.ctl.wait_if_paused()
            if self.ctl.cancel.is_set():
                raise Cancelled()
            chunks = [by_id[i] for i in ids]
            g_audio = sum(c.duration for c in chunks)
            t_g = time.monotonic()
            base_done = done_audio

            def prog(k, _chunks=chunks, _base=base_done):
                part = sum(c.duration for c in _chunks[:k])
                frac = min(1.0, (_base + part) / total)
                task.progress = frac
                self.cb.file_progress(idx, frac)
                self.cb.chunks_done(idx, [c.index for c in _chunks[:k]])

            res = self.mgr.transcribe(prep.audio, chunks, opts, prog, self.ctl.cancel)
            prep.job.save_group(gi, ids, res)
            self.cb.chunks_done(idx, list(ids))
            for r in res:
                results[r.index] = r
            done_audio += g_audio
            self._audio_done += g_audio
            self._t_busy += time.monotonic() - t_g
            report_eta(total - done_audio)
            speed = self._audio_done / max(1e-6, self._t_busy)
            left = self._remaining_audio(total - done_audio, idx)
            task.progress = done_audio / total
            self.cb.file_progress(idx, task.progress)
            all_audio = sum(t.duration * 0.9 for t in self.tasks) or 1.0
            self.cb.overall(min(1.0, 1 - left / all_audio), speed, left / speed if speed > 0 else None)

        if self.ctl.cancel.is_set():
            raise Cancelled()
        self.cb.status(f"Montando o texto de {task.path.name}…")
        merged = textproc.merge(prep.chunks, results)
        clean = textproc.clean(merged, self.s.mark_uncertain)
        paras = textproc.paragraphs(clean)
        task.elapsed = time.monotonic() - t0
        info = self.mgr.info()
        footer = exporter.footer_line(models.MODELS[self.mgr.choice.model_key].label.split(" (")[0],
                                      info.get("aceleracao", "CPU"), task.elapsed)
        stem = task.path.stem
        out_txt = exporter.unique_path(self.output_dir, stem, ".txt", self.reserved)
        exporter.atomic_write(out_txt, exporter.build_txt(stem, prep.duration, paras, footer))
        task.outputs = [str(out_txt)]
        if self.s.export_txt_timestamps:
            p = exporter.unique_path(self.output_dir, stem + " (com tempos)", ".txt", self.reserved)
            exporter.atomic_write(p, exporter.build_txt_timestamps(stem, prep.duration, paras))
            task.outputs.append(str(p))
        if self.s.export_srt:
            p = exporter.unique_path(self.output_dir, stem, ".srt", self.reserved)
            exporter.atomic_write(p, exporter.build_srt(clean))
            task.outputs.append(str(p))
        task.status, task.progress = "concluido", 1.0
        prep.job.cleanup()
        log.info("%s concluída em %.0f s (%d palavras)", task.path.name, task.elapsed, textproc.word_count(clean))
