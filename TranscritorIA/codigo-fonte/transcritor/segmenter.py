"""Detecção de voz e divisão inteligente das aulas em blocos.

Justificativa técnica do tamanho dos blocos
-------------------------------------------
O Whisper processa janelas de exatamente 30 s. Blocos maiores são fatiados
internamente de qualquer forma; blocos menores desperdiçam a janela. Por isso:

* Blocos de inferência: até 28 s (margem para o enchimento de borda), formados
  juntando falas consecutivas detectadas pelo Silero VAD e cortando SEMPRE em
  silêncio. Esses blocos são processados em lote na GPU (batching), que é a forma
  real de paralelismo — uma só cópia do modelo na VRAM.
* Fala contínua com mais de 28 s sem pausa: o corte é feito no ponto de menor
  energia (respiração/pausa curta) e os blocos vizinhos ganham 1,5 s de
  sobreposição; a duplicação é removida na junção (textproc.merge_overlap).
* Grupos de checkpoint: conjuntos de blocos que somam ~2–5 min de áudio
  (conforme o tamanho do lote calibrado). Cada grupo concluído é salvo em disco,
  então uma queda de energia perde no máximo um grupo.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

SR = 16000


@dataclass
class Chunk:
    index: int
    start: float          # segundos no áudio original
    end: float
    overlap_prev: float = 0.0   # >0 quando o início sobrepõe o bloco anterior
    forced: bool = False        # corte em fala contínua (sem silêncio)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self)


def detect_speech(audio: np.ndarray, threshold: float = 0.35) -> List[Tuple[float, float]]:
    """Regiões com fala (segundos), via Silero VAD (ONNX, local)."""
    try:
        import onnxruntime

        onnxruntime.disable_telemetry_events()
    except Exception:  # noqa: BLE001
        pass
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    opts = VadOptions(threshold=threshold, min_speech_duration_ms=200,
                      min_silence_duration_ms=400, speech_pad_ms=250)
    ts = get_speech_timestamps(audio, opts, sampling_rate=SR)
    return [(t["start"] / SR, t["end"] / SR) for t in ts]


def _lowest_energy_point(audio: Optional[np.ndarray], lo: float, hi: float) -> float:
    """Instante de menor energia (frames de 50 ms) dentro de [lo, hi]."""
    if audio is None or hi - lo < 0.2:
        return hi
    a, b = int(lo * SR), min(int(hi * SR), audio.shape[0])
    seg = audio[a:b]
    frame = int(0.05 * SR)
    n = seg.shape[0] // frame
    if n < 2:
        return hi
    rms = np.sqrt(np.mean(seg[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    i = int(np.argmin(rms))
    return lo + (i + 0.5) * frame / SR


def plan_chunks(
    speech: Sequence[Tuple[float, float]],
    duration: float,
    audio: Optional[np.ndarray] = None,
    max_len: float = 28.0,
    overlap: float = 1.5,
    max_gap: float = 4.0,
    pad: float = 0.15,
) -> List[Chunk]:
    # 1) normaliza, aplica margem e une regiões encostadas
    regs: List[List[float]] = []
    for s, e in sorted(speech):
        s, e = max(0.0, s - pad), min(duration, e + pad)
        if e - s < 0.05:
            continue
        if regs and s <= regs[-1][1]:
            regs[-1][1] = max(regs[-1][1], e)
        else:
            regs.append([s, e])

    # 2) quebra falas contínuas longas em pontos de menor energia, com sobreposição
    pieces: List[Tuple[float, float, float, bool]] = []  # (ini, fim, overlap_prev, forced)
    for s, e in regs:
        if e - s <= max_len:
            pieces.append((s, e, 0.0, False))
            continue
        cur, ov = s, 0.0
        while e - cur > max_len:
            window_lo = cur + max_len - 6.0
            cut = _lowest_energy_point(audio, max(cur + max_len / 2, window_lo), cur + max_len)
            pieces.append((cur, cut, ov, True))
            cur, ov = max(s, cut - overlap), overlap
        pieces.append((cur, e, ov, True))

    # 3) agrupa peças vizinhas em blocos de até max_len, sem atravessar silêncios longos
    chunks: List[Chunk] = []
    cs: Optional[float] = None
    ce = 0.0
    cov, cforced = 0.0, False
    for ps, pe, pov, pforced in pieces:
        if cs is not None and not pforced and not cforced and pe - cs <= max_len and ps - ce <= max_gap:
            ce = pe
            continue
        if cs is not None:
            chunks.append(Chunk(len(chunks), round(cs, 3), round(ce, 3), cov, cforced))
        cs, ce, cov, cforced = ps, pe, pov, pforced
    if cs is not None:
        chunks.append(Chunk(len(chunks), round(cs, 3), round(ce, 3), cov, cforced))
    return chunks


def plan_groups(chunks: Sequence[Chunk], batch_size: int, target_audio_s: float = 180.0) -> List[List[int]]:
    """Grupos de checkpoint: múltiplos do lote e ~3 min de áudio cada."""
    groups: List[List[int]] = []
    cur: List[int] = []
    acc = 0.0
    min_count = max(1, batch_size)
    for c in chunks:
        cur.append(c.index)
        acc += c.duration
        if len(cur) >= min_count and (acc >= target_audio_s or len(cur) >= batch_size * 4):
            groups.append(cur)
            cur, acc = [], 0.0
    if cur:
        groups.append(cur)
    return groups
