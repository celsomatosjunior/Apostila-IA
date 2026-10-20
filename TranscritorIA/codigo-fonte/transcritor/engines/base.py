"""Interface comum dos motores de transcrição."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np

from ..segmenter import Chunk


@dataclass
class Seg:
    start: float
    end: float
    text: str
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    compression_ratio: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Seg":
        return Seg(**{k: d[k] for k in ("start", "end", "text", "avg_logprob", "no_speech_prob",
                                         "compression_ratio") if k in d})


@dataclass
class ChunkResult:
    index: int
    segments: List[Seg] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"index": self.index, "segments": [s.to_dict() for s in self.segments]}

    @staticmethod
    def from_dict(d: dict) -> "ChunkResult":
        return ChunkResult(int(d["index"]), [Seg.from_dict(s) for s in d.get("segments", [])])


@dataclass
class DecodeOptions:
    language: str = "pt"
    prompt: str = ""
    beam_size: int = 5


class EngineError(Exception):
    pass


class GpuOutOfMemory(EngineError):
    pass


class GpuFailure(EngineError):
    """A GPU não executou de fato (driver, biblioteca, arquitetura não suportada)."""


class Cancelled(Exception):
    pass


ProgressCB = Callable[[int], None]  # nº de blocos concluídos no lote atual


class Engine(ABC):
    family: str = ""        # "ct2" | "whispercpp" | "fake"
    accel: str = "CPU"      # rótulo REAL do acelerador em uso
    uses_gpu: bool = False

    def __init__(self, model_key: str):
        self.model_key = model_key
        self.batch_size = 1
        self.gpu_name = ""

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def transcribe(self, audio: np.ndarray, chunks: Sequence[Chunk], opts: DecodeOptions,
                   progress: Optional[ProgressCB] = None,
                   cancel: Optional[threading.Event] = None) -> List[ChunkResult]: ...

    def close(self) -> None:
        pass

    def set_batch_size(self, n: int) -> None:
        self.batch_size = max(1, int(n))

    def set_threads(self, n: int) -> None:
        pass

    def describe(self) -> str:
        return f"{self.family}/{self.accel}/{self.model_key}"
