"""Leitura de áudio (MP3, M4A, WAV, OGG, FLAC, AAC, WMA, OPUS, vídeos MP4...).

Usa PyAV (FFmpeg embutido) — o usuário não instala FFmpeg. O áudio é convertido
para 16 kHz mono float32, formato nativo do Whisper. Uma aula de 3 h ocupa
~690 MB em RAM, valor verificado contra a RAM livre antes do processamento.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 16000
# 2.0: a leitura de áudio E vídeo fica em media.py; mantidos aqui por compatibilidade
from .media import MEDIA_EXTS as AUDIO_EXTS  # noqa: E402,F401
from .media import MediaError as AudioError  # noqa: E402,F401


def probe_duration(path: str | Path) -> float:
    """Duração em segundos (sem decodificar)."""
    from . import media

    return media.probe(path).duration


def decode(path: str | Path, cancel=None, track=None) -> np.ndarray:
    """16 kHz mono float32 — somente o áudio, mesmo para vídeos."""
    from . import media

    return media.decode(path, track=track, cancel=cancel)


def estimated_ram_mb(duration_s: float) -> int:
    return int(duration_s * SR * 4 * 1.5 / (1024 * 1024)) + 200  # buffer pré-alocado + margem


def write_wav16(path: str | Path, audio: np.ndarray) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def fmt_hms(seconds: float) -> str:
    s = int(round(max(0.0, seconds)))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
