"""Localização dos executáveis do llama.cpp (b11435) e listagem real de dispositivos.

  <programa>/llama/vulkan/  — compilação Vulkan (NVIDIA, AMD Radeon, Intel Arc) com
                              backends de CPU otimizados (AVX2/AVX-512...), incluída
  <programa>/llama/cpu/     — compilação só CPU (contingência), incluída
  <dados>/libs/llama-cuda-12.4/ — CUDA 12.4 (GeForce até a série 40), baixada com consentimento
  <dados>/libs/llama-cuda-13.4/ — CUDA 13.4 (série 50 / Blackwell), baixada com consentimento

A capacidade de cada backend é verificada executando "llama-server --list-devices",
nunca presumida pelo nome da placa.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .. import downloader, logs, paths

log = logs.get("runtime")
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
EXE = "llama-server.exe" if IS_WINDOWS else "llama-server"

LLAMA_BUILD = "b11435"
GH = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}"

CUDA_PACOTES = {
    "12.4": [
        (f"llama-{LLAMA_BUILD}-bin-win-cuda-12.4-x64.zip", 264_000_000,
         "18ef0727457adf843fe0e6dc17da296c019c821e56b7bc5fc88db734538fbfb7"),
        ("cudart-llama-bin-win-cuda-12.4-x64.zip", 391_000_000,
         "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"),
    ],
    "13.4": [
        (f"llama-{LLAMA_BUILD}-bin-win-cuda-13.4-x64.zip", 153_000_000,
         "3d2d9edf17488f955b7c36ca38eec0398244f83be596abffbd297151f7af705c"),
        ("cudart-llama-bin-win-cuda-13.4-x64.zip", 423_000_000,
         "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668"),
    ],
}

_DEV = re.compile(r"^\s*([A-Za-z]+\d+)\s*:\s*(.+?)\s*\((\d+)\s*MiB,\s*(\d+)\s*MiB free\)")


@dataclass
class Dispositivo:
    id: str          # "CUDA0", "Vulkan0"
    nome: str
    total_mb: int
    livre_mb: int

    @property
    def backend(self) -> str:
        return re.sub(r"\d+$", "", self.id).lower()


def cuda_variant(gpu_name: str) -> str:
    """RTX 50xx (Blackwell) exige CUDA 12.8+ -> pacote 13.4; demais GeForce -> 12.4."""
    n = gpu_name.lower()
    if re.search(r"rtx\s*50\d0|rtx\s*pro\s*\d{4}\s*blackwell|\bb\d{3}\b|blackwell", n):
        return "13.4"
    return "12.4"


def server_path(backend: str, gpu_name: str = "") -> Optional[Path]:
    if backend == "cuda":
        base = paths.cuda_runtime_dir(cuda_variant(gpu_name))
    else:
        base = paths.runtime_dir() / ("cpu" if backend == "cpu" else "vulkan")
    exe = base / EXE
    if exe.exists():
        return exe
    # instalação "achatada" (testes Linux): um único diretório
    flat = paths.runtime_dir() / EXE
    if backend != "cuda" and flat.exists():
        return flat
    return None


def _env_for(exe: Path) -> dict:
    env = dict(os.environ)
    if not IS_WINDOWS:
        env["LD_LIBRARY_PATH"] = str(exe.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env


def list_devices(exe: Path, timeout: float = 30.0) -> List[Dispositivo]:
    try:
        r = subprocess.run([str(exe), "--list-devices"], capture_output=True, text=True,
                           timeout=timeout, creationflags=CREATE_NO_WINDOW, env=_env_for(exe),
                           encoding="utf-8", errors="replace", cwd=str(exe.parent))
    except Exception as e:  # noqa: BLE001
        log.warning("Falha ao listar dispositivos (%s): %s", exe, e)
        return []
    devs = []
    for line in (r.stdout + "\n" + r.stderr).splitlines():
        m = _DEV.match(line)
        if m:
            devs.append(Dispositivo(m.group(1), m.group(2).strip(), int(m.group(3)), int(m.group(4))))
    log.info("Dispositivos em %s: %s", exe.parent.name, [(d.id, d.nome, d.total_mb) for d in devs])
    return devs


def cuda_instalado(gpu_name: str) -> bool:
    return server_path("cuda", gpu_name) is not None


def cuda_tamanho(gpu_name: str) -> int:
    return sum(s for _, s, _ in CUDA_PACOTES[cuda_variant(gpu_name)])


def baixar_cuda(gpu_name: str, progress: Optional[Callable[[int, int], None]] = None,
                cancel: Optional[threading.Event] = None) -> Path:
    """Baixa (com consentimento prévio) e extrai o llama.cpp CUDA + runtime CUDA."""
    var = cuda_variant(gpu_name)
    dest = paths.cuda_runtime_dir(var)
    pkgs = CUDA_PACOTES[var]
    total = sum(s for _, s, _ in pkgs)
    done_before = 0
    for name, size, sha in pkgs:
        z = paths.libs_dir() / name

        def cb(d, t, base=done_before):
            if progress:
                progress(base + d, total)

        downloader.download_file(f"{GH}/{name}", z, sha256=sha, progress=cb, cancel=cancel)
        with zipfile.ZipFile(z) as zf:
            for member in zf.infolist():
                target = (dest / member.filename).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    continue  # proteção contra caminhos maliciosos
                zf.extract(member, dest)
        z.unlink(missing_ok=True)
        done_before += size
    # pacotes podem vir com subpasta
    if not (dest / EXE).exists():
        for p in dest.rglob(EXE):
            for f in p.parent.iterdir():
                f.replace(dest / f.name)
            break
    log.info("CUDA %s instalado em %s", var, dest)
    return dest


def backends_disponiveis() -> Dict[str, Path]:
    out = {}
    for b in ("vulkan", "cpu"):
        p = server_path(b)
        if p:
            out[b] = p
    return out
