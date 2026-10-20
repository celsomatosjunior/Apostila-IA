"""Motor simulado para testes automatizados (não usado pelo usuário).

Gera texto determinístico a partir de uma "partitura": lista de (início, fim, frase)
do áudio sintético. Permite validar divisão, sobreposição, junção, checkpoints,
retomada, cancelamento e fila sem depender de modelo de IA.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..segmenter import Chunk
from .base import Cancelled, ChunkResult, DecodeOptions, Engine, GpuOutOfMemory, ProgressCB, Seg


class FakeEngine(Engine):
    family = "fake"
    accel = "CPU"

    def __init__(self, script: List[Tuple[float, float, str]], delay: float = 0.0,
                 oom_above_batch: Optional[int] = None, fail_after: Optional[int] = None):
        super().__init__("fake")
        self.script = script
        self.delay = delay
        self.oom_above_batch = oom_above_batch
        self.fail_after = fail_after
        self.calls = 0
        self.chunks_seen: List[int] = []

    def load(self) -> None:
        pass

    def transcribe(self, audio: np.ndarray, chunks: Sequence[Chunk], opts: DecodeOptions,
                   progress: Optional[ProgressCB] = None,
                   cancel: Optional[threading.Event] = None) -> List[ChunkResult]:
        self.calls += 1
        if self.oom_above_batch is not None and self.batch_size > self.oom_above_batch:
            raise GpuOutOfMemory("simulado: out of memory")
        out = []
        for k, c in enumerate(chunks):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if self.fail_after is not None and len(self.chunks_seen) >= self.fail_after:
                raise RuntimeError("queda simulada")
            if self.delay:
                time.sleep(self.delay)
            self.chunks_seen.append(c.index)
            segs = []
            for s, e, txt in self.script:
                # a palavra só é "ouvida" se estiver inteira dentro do bloco;
                # palavra cortada na borda se perde — exatamente o risco que a
                # sobreposição entre blocos precisa cobrir
                if s >= c.start - 0.01 and e <= c.end + 0.01:
                    segs.append(Seg(s, e, " " + txt, -0.2, 0.01, 1.2))
            out.append(ChunkResult(c.index, _merge_words(segs)))
            if progress:
                progress(k + 1)
        return out


def _merge_words(words: List[Seg], max_words: int = 12) -> List[Seg]:
    """Agrupa palavras em segmentos como o Whisper faria."""
    segs: List[Seg] = []
    cur: List[Seg] = []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w.text.strip().endswith((".", "?", "!")):
            segs.append(Seg(cur[0].start, cur[-1].end, "".join(x.text for x in cur), -0.2, 0.01, 1.2))
            cur = []
    if cur:
        segs.append(Seg(cur[0].start, cur[-1].end, "".join(x.text for x in cur), -0.2, 0.01, 1.2))
    return segs
