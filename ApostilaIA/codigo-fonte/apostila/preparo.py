"""Preparação inicial: o que falta baixar (modelos e, para NVIDIA, o llama.cpp CUDA).

Tudo só acontece depois do consentimento do usuário. Depois disso, offline.
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional

from . import downloader, logs
from .llm import modelos, runtime

log = logs.get("preparo")


def itens_faltando(hw, conjunto: modelos.Conjunto, incluir_cuda: bool = True) -> List[dict]:
    itens = []
    for m in conjunto.faltando():
        itens.append({"tipo": "modelo", "key": m.key, "label": m.label, "size": m.size})
    g = hw.best_gpu() if hw else None
    if incluir_cuda and g and g.vendor == "nvidia" and not g.integrated and not runtime.cuda_instalado(g.name):
        itens.append({"tipo": "cuda", "key": runtime.cuda_variant(g.name), "gpu": g.name,
                      "label": f"Aceleração NVIDIA CUDA {runtime.cuda_variant(g.name)} para {g.name} (opcional; "
                               "sem ela a GPU é usada via Vulkan)", "size": runtime.cuda_tamanho(g.name), "opcional": True})
    return itens


def instalar(itens: List[dict], progress: Optional[Callable[[str, int, int], None]] = None,
             cancel: Optional[threading.Event] = None) -> bool:
    for it in itens:
        if it["tipo"] == "modelo":
            m = modelos.MODELOS[it["key"]]
            remoto = {}
            try:
                remoto = {f["path"]: f for f in downloader.hf_list_files(m.gguf.repo)}
            except Exception as e:  # noqa: BLE001
                log.warning("API do Hugging Face indisponível (%s); usando os SHA-256 fixados", e)
            for f in m.files:
                info = remoto.get(f.path, {})
                sha = info.get("sha256") or f.sha256
                size = info.get("size") or f.size
                if info and info.get("sha256") and info["sha256"] != f.sha256:
                    log.warning("SHA-256 de %s mudou no repositório oficial; usando o publicado agora", f.path)
                downloader.download_file(downloader.hf_url(f.repo, f.path), m.local(f), expected_size=size,
                                         sha256=sha, cancel=cancel,
                                         progress=(lambda d, t, n=f.path: progress(n, d, t)) if progress else None)
        elif it["tipo"] == "cuda":
            runtime.baixar_cuda(it["gpu"], progress=(lambda d, t: progress("llama.cpp CUDA", d, t)) if progress else None,
                                cancel=cancel)
    return True
