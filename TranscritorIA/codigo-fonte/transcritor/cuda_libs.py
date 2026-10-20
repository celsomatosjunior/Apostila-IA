"""Bibliotecas NVIDIA (cuBLAS + cuDNN) para o motor CTranslate2 em GPU.

O CTranslate2 para Windows carrega cublas64_12.dll e cuDNN 9 dinamicamente.
Elas são grandes (~1,3 GB), então NÃO vão dentro do executável: são baixadas
uma única vez, com consentimento, dos pacotes oficiais da NVIDIA no PyPI,
com verificação SHA-256, e extraídas para dados/libs/cuda.

As versões são fixadas: o cuDNN precisa ser idêntico ao carregador cudnn64_9.dll
que acompanha o CTranslate2 4.8.3 (9.10.2.21). O cuBLAS 12.9 cobre também as
GPUs Blackwell (RTX 50xx).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

from . import downloader, logs, paths

log = logs.get("cuda")

PACKAGES = [
    ("nvidia-cublas-cu12", "12.9.2.10"),
    ("nvidia-cuda-nvrtc-cu12", "12.9.86"),
    ("nvidia-cudnn-cu12", "9.10.2.21"),
]
REQUIRED_DLLS = ["cublas64_12.dll", "cublasLt64_12.dll", "cudnn_ops64_9.dll",
                 "cudnn_cnn64_9.dll", "cudnn_graph64_9.dll"]
_activated = False


def lib_dir() -> Path:
    return paths.cuda_libs_dir()


def installed() -> bool:
    d = lib_dir()
    return all((d / n).is_file() for n in REQUIRED_DLLS)


def plan() -> List[dict]:
    items = []
    for pkg, ver in PACKAGES:
        data = downloader.get_json(f"https://pypi.org/pypi/{pkg}/{ver}/json")
        wheel = next((u for u in data["urls"] if u["filename"].endswith("win_amd64.whl")), None)
        if wheel is None:
            raise downloader.DownloadError(f"{pkg} {ver} sem pacote para Windows")
        items.append({"name": f"{pkg} {ver}", "url": wheel["url"], "size": wheel["size"],
                      "sha256": wheel["digests"]["sha256"], "filename": wheel["filename"]})
    return items


def total_size_mb() -> int:
    try:
        return sum(i["size"] for i in plan()) // (1024 * 1024)
    except Exception:
        return 1265


def install(progress: Optional[Callable[[str, int, int], None]] = None,
            cancel: Optional[threading.Event] = None) -> None:
    items = plan()
    total = sum(i["size"] for i in items)
    tmp = paths.libs_dir() / "_download"
    tmp.mkdir(parents=True, exist_ok=True)
    base = 0
    extracted = []
    for it in items:
        dest = tmp / it["filename"]

        def cb(done, _t, _b=base, _n=it["name"]):
            if progress:
                progress(_n, _b + done, total)

        downloader.download_file(it["url"], dest, it["size"], it["sha256"], cb, cancel)
        base += it["size"]
        with zipfile.ZipFile(dest) as z:
            for m in z.infolist():
                n = m.filename.replace("\\", "/")
                if n.lower().endswith(".dll") and "/bin/" in n:
                    target = lib_dir() / Path(n).name
                    with z.open(m) as src, open(target.with_suffix(".tmp"), "wb") as out:
                        while True:
                            b = src.read(4 << 20)
                            if not b:
                                break
                            out.write(b)
                    os.replace(target.with_suffix(".tmp"), target)
                    extracted.append(target.name)
        dest.unlink(missing_ok=True)
    (lib_dir() / "manifest.json").write_text(
        json.dumps({"packages": PACKAGES, "dlls": sorted(set(extracted))}, indent=2), encoding="utf-8")
    try:
        tmp.rmdir()
    except OSError:
        pass
    log.info("Bibliotecas CUDA instaladas: %d DLLs", len(set(extracted)))


def activate() -> bool:
    """Torna as DLLs visíveis ao CTranslate2 (deve rodar antes do uso da GPU)."""
    global _activated
    if _activated:
        return True
    if sys.platform != "win32" or not installed():
        return False
    d = str(lib_dir())
    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    try:
        os.add_dll_directory(d)
    except (OSError, AttributeError):
        pass
    import ctypes

    for name in ["cublasLt64_12.dll", "cublas64_12.dll", "cudnn_graph64_9.dll",
                 "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll"]:
        try:
            ctypes.WinDLL(str(lib_dir() / name))
        except OSError as e:
            log.warning("Falha ao pré-carregar %s: %s", name, e)
    _activated = True
    return True
