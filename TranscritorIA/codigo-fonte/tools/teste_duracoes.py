"""Teste de escala: aulas sintéticas de 5, 30, 60, 120 e 150 min.

Valida, com áudio MP3 real decodificado e VAD real, a parte do sistema que não
depende do modelo: leitura, detecção de fala, divisão, checkpoints, fila, junção
e exportação. A transcrição usa o motor SIMULADO (resultado fiel à partitura),
portanto mede integridade e tempo da infraestrutura — não a precisão do Whisper.

Uso: python tools/teste_duracoes.py [minutos ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TRANSCRITOR_DATA_DIR", tempfile.mkdtemp(prefix="transcritor_dados_"))

from transcritor import metrics  # noqa: E402
from transcritor.engines.fake_engine import FakeEngine  # noqa: E402
from test_core import body_of, run_queue  # noqa: E402

GEN = ROOT / "tests" / "_gerados"


def main(durations):
    GEN.mkdir(exist_ok=True)
    results = []
    for m in durations:
        f = GEN / f"aula_{m}min.mp3"
        if not f.exists():
            subprocess.check_call([sys.executable, str(ROOT / "tools" / "gerar_audio_teste.py"), "aula", str(f), str(m)])
        script = [tuple(x) for x in json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))]
        out = Path(tempfile.mkdtemp(prefix="saida_"))
        proc = psutil.Process()
        t0 = time.perf_counter()
        tasks, rec, _ = run_queue([f], out, FakeEngine(script), batch=16)
        el = time.perf_counter() - t0
        t = tasks[0]
        w = None
        if t.outputs:
            w = metrics.wer(" ".join(x[2] for x in script), body_of(t.outputs[0]))
        r = {"minutos": m, "status": t.status, "erro": t.error, "tempo_infra_s": round(el, 1),
             "palavras": len(script), "wer_reconstrucao": None if w is None else round(w, 4),
             "ram_pico_mb": proc.memory_info().rss // 2**20}
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    return results


if __name__ == "__main__":
    mins = [float(x) if "." in x else int(x) for x in sys.argv[1:]] or [5, 30, 60, 120, 150]
    res = main(mins)
    (ROOT / "docs" / "resultado_teste_duracoes.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                                               encoding="utf-8")
