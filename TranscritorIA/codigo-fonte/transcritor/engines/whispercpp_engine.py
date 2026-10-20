"""Motor whisper.cpp (Vulkan) — AMD Radeon, Intel Arc/iGPU e alternativa para NVIDIA.

O executável whisper-cli.exe (compilado com GGML_VULKAN no GitHub Actions) é
chamado uma vez por grupo de blocos, com vários arquivos -f: o modelo é carregado
uma única vez por grupo. O log do próprio whisper.cpp é analisado para confirmar
qual backend foi realmente usado — nunca afirmamos GPU se ele caiu para CPU.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from .. import audio as audio_mod
from .. import logs, models, paths
from ..segmenter import Chunk
from .base import (Cancelled, ChunkResult, DecodeOptions, Engine, EngineError, GpuFailure,
                   GpuOutOfMemory, ProgressCB, Seg)

log = logs.get("whispercpp")
SR = 16000
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
_BACKEND_RE = re.compile(r"using (\S+) backend")


def find_cli(gpu: bool = True) -> Optional[Path]:
    """whisper-cli com Vulkan (GPU) ou a variante só-CPU, que não depende do
    vulkan-1.dll do driver de vídeo."""
    name = "whisper-cli.exe" if IS_WINDOWS else "whisper-cli"
    env = os.environ.get("TRANSCRITOR_WHISPER_CLI")
    if env and Path(env).is_file():
        return Path(env)
    subs = ("whispercpp-vulkan", "whispercpp") if gpu else ("whispercpp-cpu", "whispercpp", "whispercpp-vulkan")
    for sub in subs:
        p = paths.engines_dir() / sub / name
        if p.is_file():
            return p
    w = shutil.which(name)
    return Path(w) if w else None


def available() -> bool:
    return find_cli() is not None


class WhisperCppEngine(Engine):
    family = "whispercpp"

    def __init__(self, model_key: str, use_gpu: bool = True, threads: int = 4, gpu_device: int = 0,
                 work_dir: Optional[Path] = None):
        super().__init__(model_key)
        self.use_gpu = use_gpu
        self.threads = threads
        self.gpu_device = gpu_device
        self.work_dir = work_dir
        self.cli: Optional[Path] = None
        self.actual_backend = ""
        self.uses_gpu = False          # só vira True após confirmação no log
        self.accel = "CPU"
        self.batch_size = 16           # nº de blocos por chamada
        self._proc: Optional[subprocess.Popen] = None

    def load(self) -> None:
        self.cli = find_cli(self.use_gpu)
        if self.cli is None:
            raise EngineError("whisper.cpp (whisper-cli) não encontrado no pacote")
        if not models.ggml_installed(self.model_key):
            raise EngineError(f"Modelo GGML {self.model_key} não instalado")

    def set_threads(self, n: int) -> None:
        self.threads = max(1, int(n))

    def _args(self, files: List[Path], opts: DecodeOptions) -> List[str]:
        a = [str(self.cli), "-m", str(models.ggml_path(self.model_key)), "-l", opts.language,
             "-t", str(self.threads), "-bs", str(opts.beam_size), "-bo", "5", "-ojf", "-nth", "0.6"]
        if opts.prompt:
            a += ["--prompt", opts.prompt]
        if self.use_gpu:
            a += ["-dev", str(self.gpu_device)]
        else:
            a += ["-ng"]
        for f in files:
            a += ["-f", str(f)]
        return a

    def transcribe(self, audio: np.ndarray, chunks: Sequence[Chunk], opts: DecodeOptions,
                   progress: Optional[ProgressCB] = None,
                   cancel: Optional[threading.Event] = None) -> List[ChunkResult]:
        if self.cli is None:
            raise EngineError("Motor não carregado")
        chunks = list(chunks)
        results = [ChunkResult(c.index) for c in chunks]
        if not chunks:
            return results
        base = self.work_dir or Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="wcpp_", dir=str(base)))
        try:
            files = []
            for c in chunks:
                f = tmp / f"b{c.index:06d}.wav"
                audio_mod.write_wav16(f, audio[int(c.start * SR): int(c.end * SR)])
                files.append(f)
            stderr_path = tmp / "stderr.txt"
            with open(stderr_path, "wb") as errf:
                self._proc = subprocess.Popen(self._args(files, opts), stdout=subprocess.DEVNULL,
                                              stderr=errf, creationflags=CREATE_NO_WINDOW, cwd=str(tmp))
                done_prev = 0
                while self._proc.poll() is None:
                    if cancel is not None and cancel.is_set():
                        self._proc.kill()
                        self._proc.wait()
                        raise Cancelled()
                    time.sleep(0.25)
                    if progress:
                        done = sum(1 for f in files if Path(str(f) + ".json").exists())
                        if done != done_prev:
                            progress(done)
                            done_prev = done
                rc = self._proc.returncode
            err = stderr_path.read_text(encoding="utf-8", errors="replace")
            self._inspect_backend(err)
            if rc != 0:
                low = err.lower()
                if "out of memory" in low or "erroroutofdevicememory" in low:
                    raise GpuOutOfMemory(err[-800:])
                if self.use_gpu and ("vulkan" in low or "ggml_vk" in low):
                    raise GpuFailure(err[-800:])
                raise EngineError(f"whisper.cpp terminou com código {rc}: {err[-800:]}")
            for c, f, r in zip(chunks, files, results):
                r.segments = self._parse(Path(str(f) + ".json"), c)
            if progress:
                progress(len(chunks))
            return results
        finally:
            self._proc = None
            shutil.rmtree(tmp, ignore_errors=True)

    def _inspect_backend(self, err: str) -> None:
        backends = _BACKEND_RE.findall(err)
        gpu = [b for b in backends if not b.upper().startswith("CPU")]
        self.actual_backend = ", ".join(backends) or "CPU"
        if gpu:
            self.uses_gpu = True
            self.accel = "Vulkan" if any("vulkan" in b.lower() for b in gpu) else gpu[0]
            m = re.search(r"ggml_vulkan: \d+ = ([^|(\n]+)", err)
            if m:
                self.gpu_name = m.group(1).strip()
        else:
            self.uses_gpu = False
            self.accel = "CPU"
            if self.use_gpu:
                log.warning("whisper.cpp não usou GPU (backends: %s)", self.actual_backend)

    @staticmethod
    def _parse(path: Path, c: Chunk) -> List[Seg]:
        if not path.exists():
            raise EngineError(f"Saída ausente para o bloco {c.index}")
        raw = path.read_bytes().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw, strict=False)
        except json.JSONDecodeError as e:
            raise EngineError(f"JSON inválido do whisper.cpp: {e}") from e
        segs = []
        for t in data.get("transcription", []):
            off = t.get("offsets", {})
            text = t.get("text", "")
            probs = [tok.get("p", 1.0) for tok in t.get("tokens", [])
                     if not str(tok.get("text", "")).startswith("[_")]
            avg = float(np.mean([math.log(max(p, 1e-6)) for p in probs])) if probs else 0.0
            segs.append(Seg(c.start + off.get("from", 0) / 1000.0, c.start + off.get("to", 0) / 1000.0,
                            text, avg, 0.0, 1.0))
        return segs
