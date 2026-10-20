"""Teste de desempenho completo (opcional, acionado pelo usuário).

Compara, no computador real, as estratégias exigidas pela especificação:
  A) sequencial otimizado (lote = 1)
  B) lote na GPU (vários tamanhos)
  C) paralelo: 2 instâncias do modelo ao mesmo tempo (só se couber na VRAM)
  D) CPU (referência)
e registra velocidade (× tempo real), WER no áudio de referência e VRAM/RAM.
Nenhum número é estimado: tudo é medido.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import psutil

from . import backend, hardware, logs, paths
from .engines.base import DecodeOptions, EngineError, GpuFailure, GpuOutOfMemory

log = logs.get("benchmark")


def run(hw: hardware.HardwareInfo, model_pref: str = "auto", notify: Callable[[str], None] = print,
        cancel: Optional[threading.Event] = None) -> dict:
    ref, ref_txt = backend.reference()
    opts = DecodeOptions(language="pt", beam_size=5)
    report = {"data": datetime.now().isoformat(timespec="seconds"), "hardware": hw.to_dict(), "testes": []}

    def record(nome, fn):
        if cancel is not None and cancel.is_set():
            return
        notify(f"Teste: {nome}…")
        rss0 = psutil.Process().memory_info().rss
        try:
            speed, w, extra = fn()
            item = {"teste": nome, "velocidade_x": round(speed, 2), "wer_referencia": round(w, 3),
                    "ram_processo_mb": psutil.Process().memory_info().rss // 2**20, **extra}
        except (EngineError, GpuFailure, GpuOutOfMemory, RuntimeError) as e:
            item = {"teste": nome, "erro": str(e)[:300]}
        item["delta_ram_mb"] = (psutil.Process().memory_info().rss - rss0) // 2**20
        report["testes"].append(item)
        log.info("benchmark %s", item)

    for cand in backend.build_candidates(hw, model_pref, "auto", "turbo"):
        if backend.missing_components(cand):
            report["testes"].append({"teste": f"{cand.accel} {cand.gpu_name}", "erro": "componentes não instalados"})
            continue
        eng = backend.make_engine(cand)
        try:
            eng.load()
        except Exception as e:  # noqa: BLE001
            report["testes"].append({"teste": f"{cand.accel} carregar", "erro": str(e)[:300]})
            continue
        ladder = backend._batch_ladder(cand, next((g.vram_total_mb for g in hw.gpus if g.name == cand.gpu_name), 0))
        if cand.family == "ct2":
            eng.set_batch_size(1)
            backend._measure(eng, ref, ref_txt, 1, opts, cancel)  # aquecimento
        for bs in ladder:
            def t(bs=bs):
                eng.set_batch_size(bs)
                s, w = backend._measure(eng, ref, ref_txt, max(4, bs * 2), opts, cancel)
                free = hardware.nvidia_free_vram_mb(max(0, cand.gpu_index)) if cand.device == "cuda" else None
                return s, w, {"lote": bs, "vram_livre_mb": free}
            nome = "sequencial (lote 1)" if bs == 1 else f"lote {bs}"
            record(f"{cand.accel} {cand.gpu_name or 'CPU'} — {nome}", t)
        if cand.device == "cuda":
            free = hardware.nvidia_free_vram_mb(max(0, cand.gpu_index)) or 0
            from .models import MODELS
            if free > MODELS[cand.model_key].vram_fp16_mb * 1.6:
                def par():
                    eng2 = backend.make_engine(cand)
                    eng2.load()
                    bs = max(1, ladder[-1] // 2)
                    eng.set_batch_size(bs)
                    eng2.set_batch_size(bs)
                    out = {}

                    def w(e, k):
                        out[k] = backend._measure(e, ref, ref_txt, bs * 2, opts, cancel)
                    t0 = time.perf_counter()
                    th = [threading.Thread(target=w, args=(e, k)) for k, e in ((0, eng), (1, eng2))]
                    [x.start() for x in th]
                    [x.join() for x in th]
                    el = time.perf_counter() - t0
                    audio_s = 2 * bs * 2 * (len(ref) / 16000)
                    eng2.close()
                    return audio_s / el, out[0][1], {"instancias": 2, "lote_cada": bs}
                record(f"{cand.accel} — 2 instâncias paralelas", par)
            else:
                report["testes"].append({"teste": "2 instâncias paralelas",
                                         "erro": "VRAM livre insuficiente para duplicar o modelo"})
        eng.close()
    path = paths.logs_dir() / f"desempenho_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["arquivo"] = str(path)
    return report


def format_report(rep: dict) -> str:
    lines = [f"Teste de desempenho — {rep['data']}", ""]
    for t in rep["testes"]:
        if "erro" in t:
            lines.append(f"• {t['teste']}: não executado ({t['erro']})")
        else:
            lines.append(f"• {t['teste']}: {t['velocidade_x']:.1f}× tempo real · WER ref. {t['wer_referencia']:.0%}")
    ok = [t for t in rep["testes"] if "velocidade_x" in t]
    if ok:
        best = max(ok, key=lambda t: t["velocidade_x"])
        lines += ["", f"Melhor estratégia medida: {best['teste']} ({best['velocidade_x']:.1f}× tempo real)."]
        lines.append(f"Uma aula de 2 h levaria cerca de {120 / best['velocidade_x']:.0f} min nessa configuração.")
    lines += ["", f"Relatório salvo em: {rep.get('arquivo', '')}"]
    return "\n".join(lines)
