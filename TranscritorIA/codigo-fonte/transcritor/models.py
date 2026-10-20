"""Catálogo e gerenciamento local dos modelos Whisper.

Dois formatos, um por família de motor:
  - CTranslate2 (faster-whisper)  -> NVIDIA/CUDA e CPU
  - GGML (whisper.cpp)            -> Vulkan (AMD, Intel, NVIDIA alternativo)
Os modelos ficam em dados/modelos e NÃO são embutidos no executável.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import downloader, logs, paths

log = logs.get("models")


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    ct2_repo: str
    ggml_file: str
    approx_mb: int          # tamanho em disco (CT2 fp16)
    vram_fp16_mb: int       # VRAM aproximada só dos pesos em FP16
    quality_rank: int       # 1 = melhor


MODELS: Dict[str, ModelSpec] = {
    m.key: m for m in [
        ModelSpec("large-v3", "Whisper Large-v3 (máxima precisão)",
                  "Systran/faster-whisper-large-v3", "ggml-large-v3.bin", 3100, 3300, 1),
        ModelSpec("large-v3-turbo", "Whisper Large-v3 Turbo (rápido, alta precisão)",
                  "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "ggml-large-v3-turbo.bin", 1620, 1800, 2),
        ModelSpec("medium", "Whisper Medium",
                  "Systran/faster-whisper-medium", "ggml-medium.bin", 1530, 1700, 3),
        ModelSpec("small", "Whisper Small",
                  "Systran/faster-whisper-small", "ggml-small.bin", 484, 600, 4),
        ModelSpec("tiny", "Whisper Tiny (somente testes)",
                  "Systran/faster-whisper-tiny", "ggml-tiny.bin", 75, 150, 9),
    ]
}
USER_MODELS = ["large-v3", "large-v3-turbo", "medium", "small"]
GGML_REPO = "ggerganov/whisper.cpp"
CT2_REQUIRED = ("config.json", "model.bin", "tokenizer.json")


def ct2_dir(key: str) -> Path:
    return paths.models_dir() / "ct2" / key


def ggml_path(key: str) -> Path:
    return paths.models_dir() / "ggml" / MODELS[key].ggml_file


def ct2_installed(key: str) -> bool:
    d = ct2_dir(key)
    if not all((d / f).is_file() for f in CT2_REQUIRED):
        return False
    return (d / "model.bin").stat().st_size > 10_000_000 and not any(d.glob("*.part"))


def ggml_installed(key: str) -> bool:
    p = ggml_path(key)
    return p.is_file() and p.stat().st_size > 10_000_000


def installed(key: str, fmt: str) -> bool:
    return ct2_installed(key) if fmt == "ct2" else ggml_installed(key)


def plan_download(key: str, fmt: str) -> List[dict]:
    """Lista arquivos (url, destino, tamanho, sha256) que precisam ser baixados."""
    spec = MODELS[key]
    items = []
    if fmt == "ct2":
        for f in downloader.hf_list_files(spec.ct2_repo):
            name = f["path"]
            if name.startswith(".") or name.lower().endswith((".md",)) or "/" in name:
                continue
            dest = ct2_dir(key) / name
            if dest.is_file() and f["size"] and dest.stat().st_size == f["size"]:
                continue
            items.append({"url": downloader.hf_url(spec.ct2_repo, name), "dest": dest,
                          "size": f["size"], "sha256": f["sha256"], "name": f"{key}/{name}"})
    else:
        files = {f["path"]: f for f in downloader.hf_list_files(GGML_REPO)}
        f = files.get(spec.ggml_file)
        if f is None:
            raise downloader.DownloadError(f"{spec.ggml_file} não encontrado em {GGML_REPO}")
        dest = ggml_path(key)
        if not (dest.is_file() and dest.stat().st_size == f["size"]):
            items.append({"url": downloader.hf_url(GGML_REPO, spec.ggml_file), "dest": dest,
                          "size": f["size"], "sha256": f["sha256"], "name": spec.ggml_file})
    return items


def download(key: str, fmt: str, progress: Optional[Callable[[str, int, int], None]] = None,
             cancel: Optional[threading.Event] = None) -> None:
    items = plan_download(key, fmt)
    total = sum(i["size"] or 0 for i in items)
    base = 0
    for it in items:
        def cb(done, _tot, _b=base, _n=it["name"]):
            if progress:
                progress(_n, _b + done, total)
        downloader.download_file(it["url"], it["dest"], it["size"], it["sha256"], cb, cancel)
        base += it["size"] or 0
    log.info("Modelo %s (%s) pronto", key, fmt)
