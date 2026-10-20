"""Gera vídeos de teste (MP4, MKV, AVI, MOV, WMV, WEBM, MPG, M4V, FLV) a partir de aulas sintéticas.

O vídeo é mínimo (64x48, 1 quadro por segundo): o que interessa é o áudio, que vem de uma
aula com "partitura" conhecida (tools/gerar_audio_teste.py), permitindo conferir o texto.

Uso em código:  make_video(saida, [Trilha(audio, "por", "Português", True)], video=True)
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

import numpy as np

SR = 16000

# contêiner -> (codec de vídeo, codec de áudio, taxa de amostragem do áudio)
PROFILES = {
    ".mp4": ("mpeg4", "aac", 44100), ".m4v": ("mpeg4", "aac", 44100), ".mov": ("mpeg4", "aac", 48000),
    ".mkv": ("mpeg4", "ac3", 48000), ".avi": ("mpeg4", "libmp3lame", 44100), ".wmv": ("wmv2", "wmav2", 44100),
    ".webm": ("libvpx", "libopus", 48000), ".mpg": ("mpeg1video", "mp2", 44100),
    ".mpeg": ("mpeg2video", "mp2", 48000), ".flv": ("flv", "aac", 44100),
}


@dataclass
class Trilha:
    audio: np.ndarray            # float32 16 kHz mono
    language: str = ""
    title: str = ""
    default: bool = False


def make_video(out: Path, tracks: List[Trilha], video: bool = True, stereo: bool = True,
               fps: int = 1, profile: Optional[tuple] = None) -> Path:
    import av

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    vcodec, acodec, asr = profile or PROFILES[out.suffix.lower()]
    dur = max((len(t.audio) / SR for t in tracks), default=10.0)
    with av.open(str(out), "w") as c:
        vs = None
        if video:
            vs = c.add_stream(vcodec, rate=fps if vcodec not in ("mpeg1video", "mpeg2video") else 25)
            vs.width, vs.height, vs.pix_fmt = 64, 48, "yuv420p"
            if vcodec == "libvpx":
                vs.options = {"deadline": "realtime", "cpu-used": "8"}
        astreams = []
        for t in tracks:
            st = c.add_stream(acodec, rate=asr)
            st.layout = "stereo" if stereo else "mono"
            st.bit_rate = 128000
            if t.language:
                st.metadata["language"] = t.language
            if t.title:
                st.metadata["title"] = t.title
            astreams.append(st)
        try:
            import av.stream as avs
            for t, st in zip(tracks, astreams):
                st.disposition = avs.Disposition.default if t.default else avs.Disposition(0)
        except Exception:  # noqa: BLE001
            pass

        # áudio gerado sob demanda, quadro a quadro (memória baixa mesmo para 3 h)
        ch = 2 if stereo else 1
        layout = "stereo" if stereo else "mono"
        srcs = [t.audio for t in tracks]
        poss = [0 for _ in tracks]

        def audio_chunk(k: int, i: int, fs: int) -> np.ndarray:
            src = srcs[k]
            pos = (np.arange(i, i + fs) * (SR / asr))
            lo = int(pos[0])
            hi = min(len(src) - 1, int(pos[-1]) + 2)
            if lo >= len(src) - 1:
                x = np.zeros(fs, np.float32)
            else:
                x = np.interp(pos, np.arange(lo, hi + 1), src[lo:hi + 1], right=0.0).astype(np.float32)
            pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
            return np.repeat(pcm[:, None], ch, axis=1).reshape(-1) if stereo else pcm
        rate = (fps if vcodec not in ("mpeg1video", "mpeg2video") else 25) if vs is not None else 1
        img = np.zeros((48, 64, 3), np.uint8)
        nsec = int(np.ceil(dur)) + 1
        frame_i = 0
        for sec in range(nsec):  # intercala: 1 s de vídeo, 1 s de cada trilha
            if vs is not None:
                for _ in range(rate):
                    img[:] = (frame_i * 7) % 255
                    fr = av.VideoFrame.from_ndarray(img, format="rgb24")
                    fr.pts = frame_i
                    fr.time_base = Fraction(1, rate)
                    for p in vs.encode(fr):
                        c.mux(p)
                    frame_i += 1
            for k, st in enumerate(astreams):
                fs = st.codec_context.frame_size or 1152
                total = int(len(srcs[k]) * asr / SR)
                while poss[k] < min(total, (sec + 1) * asr):
                    i = poss[k]
                    chunk = audio_chunk(k, i, fs)
                    fr = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout=layout)
                    fr.sample_rate = asr
                    fr.pts = i
                    for p in st.encode(fr):
                        c.mux(p)
                    poss[k] += fs
        for st in astreams:
            for p in st.encode(None):
                c.mux(p)
        if vs is not None:
            for p in vs.encode(None):
                c.mux(p)
    return out
