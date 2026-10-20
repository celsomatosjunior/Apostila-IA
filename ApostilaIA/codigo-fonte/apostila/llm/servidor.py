"""Processo llama-server local (127.0.0.1, porta aleatória, chave aleatória).

Um único modelo carregado por vez. O uso real da GPU é confirmado pelo log do
próprio llama.cpp ("offloaded N/M layers to GPU" e buffers alocados em CUDA0/Vulkan0)
— a interface só mostra "GPU" quando isso aparece.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .. import logs

log = logs.get("servidor")
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
BELOW_NORMAL = 0x00004000


class ServidorErro(RuntimeError):
    pass


@dataclass
class Config:
    exe: Path
    model: Path
    mmproj: Optional[Path] = None
    ctx: int = 16384
    backend: str = "cpu"           # cuda | vulkan | cpu
    device: str = ""               # "CUDA0", "Vulkan0" ("" = automático / nenhum para cpu)
    threads: int = 0
    trabalho: bool = False         # prioridade reduzida e margem maior de VRAM
    fit_margin_mb: int = 1024
    kv_quant: bool = True
    n_gpu_layers: Optional[str] = None  # None = automático (--fit)
    extra: List[str] = field(default_factory=list)


@dataclass
class EstadoGPU:
    camadas_gpu: int = 0
    camadas_total: int = 0
    dispositivo: str = ""
    buffer_gpu_mb: float = 0.0
    buffer_cpu_mb: float = 0.0

    @property
    def verificada(self) -> bool:
        return self.camadas_gpu > 0 and self.buffer_gpu_mb > 0

    def descricao(self) -> str:
        if not self.verificada:
            return "CPU"
        return (f"{self.dispositivo}: {self.camadas_gpu}/{self.camadas_total} camadas na GPU "
                f"({self.buffer_gpu_mb / 1024:.1f} GB em VRAM)")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_OFF = re.compile(r"offloaded (\d+)/(\d+) layers to GPU")
_BUF = re.compile(r"(\b[A-Za-z]+\d+|CPU(?:_Mapped|_REPACK)?)\s+model buffer size\s*=\s*([\d.]+)\s*MiB")
_DEVUSE = re.compile(r"using device (\w+\d+) \(([^)]+)\)")


class LlamaServer:
    def __init__(self, cfg: Config, log_path: Optional[Path] = None):
        self.cfg = cfg
        self.port = _free_port()
        self.key = secrets.token_hex(16)
        self.proc: Optional[subprocess.Popen] = None
        self.log_path = log_path
        self.tail: deque = deque(maxlen=400)
        self.gpu = EstadoGPU()
        self.n_ctx = cfg.ctx
        self._reader: Optional[threading.Thread] = None
        self._logf = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def args(self) -> List[str]:
        c = self.cfg
        a = [str(c.exe), "-m", str(c.model), "--host", "127.0.0.1", "--port", str(self.port),
             "--api-key", self.key, "-c", str(c.ctx), "-np", "1", "--jinja", "--no-webui",
             "--cache-ram", "0", "--offline", "-fa", "auto"]
        if c.mmproj:
            a += ["--mmproj", str(c.mmproj)]
        if c.threads:
            a += ["-t", str(c.threads), "-tb", str(c.threads)]
        if c.kv_quant:
            a += ["-ctk", "q8_0", "-ctv", "q8_0"]
        if c.backend == "cpu":
            a += ["-dev", "none", "-ngl", "0", "--fit", "off"]
            if c.mmproj:
                a += ["--no-mmproj-offload"]
        else:
            if c.device:
                a += ["-dev", c.device]
            if c.n_gpu_layers is not None:
                a += ["-ngl", c.n_gpu_layers, "--fit", "off"]
            else:
                a += ["--fit", "on", "--fit-target", str(c.fit_margin_mb), "--fit-ctx", str(min(c.ctx, 8192))]
        if c.trabalho:
            a += ["--prio", "-1", "--poll", "0"]
        a += list(c.extra)
        return a

    def _env(self) -> dict:
        env = dict(os.environ)
        if not IS_WINDOWS:
            env["LD_LIBRARY_PATH"] = str(self.cfg.exe.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        env["LLAMA_OFFLINE"] = "1"
        return env

    def _read(self):
        assert self.proc and self.proc.stdout
        for raw in self.proc.stdout:
            line = raw.rstrip()
            self.tail.append(line)
            if self._logf:
                try:
                    self._logf.write(line + "\n")
                    self._logf.flush()
                except Exception:  # noqa: BLE001
                    pass
            m = _OFF.search(line)
            if m:
                self.gpu.camadas_gpu, self.gpu.camadas_total = int(m.group(1)), int(m.group(2))
            m = _BUF.search(line)
            if m:
                dev, mb = m.group(1), float(m.group(2))
                if dev.startswith("CPU"):
                    self.gpu.buffer_cpu_mb += mb
                else:
                    self.gpu.buffer_gpu_mb += mb
                    self.gpu.dispositivo = self.gpu.dispositivo or dev
            m = _DEVUSE.search(line)
            if m:
                self.gpu.dispositivo = f"{m.group(1)} ({m.group(2).split(' - ')[0]})"

    def start(self, timeout: float = 900.0, cancel: Optional[threading.Event] = None) -> None:
        args = self.args()
        log.info("Iniciando llama-server: %s", " ".join(a if a != self.key else "***" for a in args))
        flags = CREATE_NO_WINDOW | (BELOW_NORMAL if (IS_WINDOWS and self.cfg.trabalho) else 0)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._logf = open(self.log_path, "a", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     errors="replace", creationflags=flags, env=self._env(),
                                     cwd=str(self.cfg.exe.parent))
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        t0 = time.monotonic()
        while True:
            if cancel is not None and cancel.is_set():
                self.stop()
                raise ServidorErro("cancelado")
            if self.proc.poll() is not None:
                time.sleep(0.3)
                raise ServidorErro("llama-server terminou ao carregar o modelo:\n" + "\n".join(list(self.tail)[-25:]))
            try:
                req = urllib.request.Request(self.base + "/health", headers={"Authorization": f"Bearer {self.key}"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    if r.status == 200:
                        break
            except urllib.error.HTTPError as e:
                if e.code != 503:  # 503 = carregando
                    raise ServidorErro(f"health HTTP {e.code}")
            except (urllib.error.URLError, OSError, TimeoutError):
                pass
            if time.monotonic() - t0 > timeout:
                self.stop()
                raise ServidorErro("tempo esgotado ao carregar o modelo")
            time.sleep(0.5)
        try:
            props = self.get("/props")
            self.n_ctx = int(props.get("default_generation_settings", {}).get("n_ctx") or self.cfg.ctx)
        except Exception:  # noqa: BLE001
            self.n_ctx = self.cfg.ctx
        log.info("Modelo pronto em %.0fs (ctx=%d, %s)", time.monotonic() - t0, self.n_ctx, self.gpu.descricao())

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def get(self, path: str, timeout: float = 20) -> dict:
        req = urllib.request.Request(self.base + path, headers={"Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path: str, body: dict, timeout: float = 600):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers={"Authorization": f"Bearer {self.key}",
                                              "Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=timeout)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=15)
            except Exception:  # noqa: BLE001
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass
        self.proc = None
        if self._logf:
            try:
                self._logf.close()
            except Exception:  # noqa: BLE001
                pass
            self._logf = None

    def ultimas_linhas(self, n: int = 20) -> str:
        return "\n".join(list(self.tail)[-n:])
