"""Motor faster-whisper / CTranslate2 (NVIDIA CUDA ou CPU).

Paralelismo: UMA cópia do modelo na memória e blocos decodificados em lote
(BatchedInferencePipeline). Isso é mais rápido e muito mais econômico em VRAM
do que várias instâncias concorrentes do modelo.

Qualidade: o modo em lote não usa "temperature fallback". Por isso, todo bloco
com sinal de falha do modelo (repetição/loop, taxa de compressão alta) é
reprocessado individualmente no modo clássico, com fallback de temperatura.
"""
from __future__ import annotations

import threading
import zlib
from typing import List, Optional, Sequence

import numpy as np

from .. import cuda_libs, logs, models
from ..segmenter import Chunk
from .base import (Cancelled, ChunkResult, DecodeOptions, Engine, EngineError, GpuFailure,
                   GpuOutOfMemory, ProgressCB, Seg)

log = logs.get("ct2")
SR = 16000


def _classify_error(e: Exception, device: str) -> Exception:
    msg = str(e).lower()
    if device == "cuda":
        if "out of memory" in msg or "cudaerrormemoryallocation" in msg or "cublas_status_alloc_failed" in msg:
            return GpuOutOfMemory(str(e))
        if any(k in msg for k in ("cuda", "cublas", "cudnn", "no kernel image", "driver", ".dll")):
            return GpuFailure(str(e))
    return EngineError(str(e))


def _compression_ratio(text: str) -> float:
    b = text.encode("utf-8")
    return len(b) / max(1, len(zlib.compress(b)))


class CT2Engine(Engine):
    family = "ct2"

    def __init__(self, model_key: str, device: str = "cpu", compute_type: str = "auto",
                 batch_size: int = 8, cpu_threads: int = 0, device_index: int = 0):
        super().__init__(model_key)
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.device_index = device_index
        self.batch_size = batch_size
        self.model = None
        self.batched = None
        self.uses_gpu = device == "cuda"
        self.accel = "CUDA" if self.uses_gpu else "CPU"

    def _resolve_compute_type(self) -> str:
        if self.compute_type != "auto":
            return self.compute_type
        import ctranslate2

        supported = ctranslate2.get_supported_compute_types(self.device, self.device_index)
        if self.device == "cuda":
            for ct in ("float16", "int8_float16", "int8"):
                if ct in supported:
                    return ct
            return "float32"
        for ct in ("int8", "int8_float32", "float32"):
            if ct in supported:
                return ct
        return "float32"

    def load(self) -> None:
        if self.device == "cuda":
            if not cuda_libs.activate():
                import sys
                if sys.platform == "win32":
                    raise GpuFailure("Bibliotecas CUDA (cuBLAS/cuDNN) não instaladas")
            import ctranslate2

            if ctranslate2.get_cuda_device_count() <= 0:
                raise GpuFailure("CTranslate2 não encontrou GPU CUDA utilizável")
        if not models.ct2_installed(self.model_key):
            raise EngineError(f"Modelo {self.model_key} não instalado")
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        self.compute_type = self._resolve_compute_type()
        try:
            self.model = WhisperModel(
                str(models.ct2_dir(self.model_key)), device=self.device, device_index=self.device_index,
                compute_type=self.compute_type, cpu_threads=self.cpu_threads, num_workers=1,
                local_files_only=True,
            )
        except Exception as e:  # noqa: BLE001
            raise _classify_error(e, self.device) from e
        self.batched = BatchedInferencePipeline(self.model)
        log.info("Modelo %s carregado em %s (%s)", self.model_key, self.device, self.compute_type)

    def close(self) -> None:
        self.batched = None
        self.model = None
        import gc
        gc.collect()

    def set_threads(self, n: int) -> None:
        self.cpu_threads = n  # aplicado no próximo load()

    # ----------------------------------------------------------------
    def transcribe(self, audio: np.ndarray, chunks: Sequence[Chunk], opts: DecodeOptions,
                   progress: Optional[ProgressCB] = None,
                   cancel: Optional[threading.Event] = None) -> List[ChunkResult]:
        if self.batched is None:
            raise EngineError("Motor não carregado")
        chunks = list(chunks)
        results = [ChunkResult(c.index) for c in chunks]
        if not chunks:
            return results
        clips = [{"start": float(c.start), "end": float(c.end)} for c in chunks]
        try:
            segs, _info = self.batched.transcribe(
                audio, language=opts.language, task="transcribe", beam_size=opts.beam_size,
                batch_size=self.batch_size, clip_timestamps=clips, vad_filter=False,
                without_timestamps=False, initial_prompt=opts.prompt or None,
                log_progress=False,
            )
            j = 0
            prev_end = None
            done_reported = 0
            for s in segs:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                st = float(s.start)
                # avança para o bloco correto (blocos vazios / sobreposição)
                while j + 1 < len(chunks) and st >= chunks[j + 1].start - 0.05 and (
                        st >= chunks[j].end - 0.05 or (prev_end is not None and st < prev_end - 0.3)):
                    j += 1
                    prev_end = None
                results[j].segments.append(Seg(st, float(s.end), s.text, float(s.avg_logprob),
                                               float(s.no_speech_prob), float(s.compression_ratio)))
                prev_end = float(s.end)
                if progress and j > done_reported:
                    progress(j)
                    done_reported = j
        except Cancelled:
            raise
        except (GpuOutOfMemory, GpuFailure):
            raise
        except Exception as e:  # noqa: BLE001
            raise _classify_error(e, self.device) from e
        if progress:
            progress(len(chunks))
        # reparo de blocos com falha típica do modelo (loop de repetição)
        for c, r in zip(chunks, results):
            txt = " ".join(x.text.strip() for x in r.segments)
            if txt and (_compression_ratio(txt) > 2.4 or any(x.compression_ratio > 2.4 for x in r.segments)):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                log.info("Reprocessando bloco %d (possível repetição do modelo)", c.index)
                try:
                    r.segments = self._sequential(audio, c, opts)
                except Exception as e:  # noqa: BLE001
                    raise _classify_error(e, self.device) from e
        return results

    def _sequential(self, audio: np.ndarray, c: Chunk, opts: DecodeOptions) -> List[Seg]:
        piece = audio[int(c.start * SR): int(c.end * SR)]
        segs, _ = self.model.transcribe(
            piece, language=opts.language, beam_size=opts.beam_size,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0], condition_on_previous_text=False,
            vad_filter=False, initial_prompt=opts.prompt or None, compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0, no_speech_threshold=0.6,
        )
        return [Seg(c.start + float(s.start), c.start + float(s.end), s.text, float(s.avg_logprob),
                    float(s.no_speech_prob), float(s.compression_ratio)) for s in segs]
