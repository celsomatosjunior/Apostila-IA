"""Modo linha de comando (automação, testes e diagnóstico).

O usuário comum não precisa disto: o duplo clique abre a interface gráfica.
Exemplos:
  TranscritorIA.exe --cli aula1.mp3 aula2.mp3 --saida D:\\Textos --baixar
  TranscritorIA.exe --diagnostico
  TranscritorIA.exe --autoteste --modelo tiny --baixar   (validação completa com áudio de referência)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

from . import APP_TITLE, __version__, audio, backend, benchmark, hardware, logs, metrics, paths
from .pipeline import Callbacks, Controller, FileTask, QueueRunner
from .settings import Settings


def _out(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:  # noqa: BLE001 — executável sem console
        pass
    logs.get("cli").info(msg)


class CliCallbacks(Callbacks):
    def __init__(self):
        self._last = 0.0

    def status(self, text):
        _out(text)

    def notice(self, text):
        _out("AVISO: " + text)

    def engine_ready(self, info):
        _out("Motor: " + " | ".join(f"{k}: {v}" for k, v in info.items() if v))

    def file_progress(self, idx, frac):
        now = time.monotonic()
        if now - self._last > 5 or frac >= 1.0:
            _out(f"  aula {idx + 1}: {frac:.0%}")
            self._last = now

    def overall(self, frac, speed, eta):
        eta_txt = audio.fmt_hms(eta) if eta else "--"
        _out(f"  geral {frac:.0%} · {speed:.1f}× tempo real · restante {eta_txt}")

    def file_done(self, idx, task):
        _out(f"OK: {task.path.name} -> {', '.join(task.outputs)}")

    def file_error(self, idx, task):
        _out(f"ERRO: {task.path.name}: {task.error}")

    def finished(self, s):
        _out(json.dumps({k: v for k, v in s.items() if k != "arquivos"}, ensure_ascii=False))


def _expand(inputs: List[str]) -> List[Path]:
    files = []
    for i in inputs:
        p = Path(i)
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix.lower() in audio.AUDIO_EXTS)
        elif p.is_file():
            files.append(p)
        else:
            _out(f"Ignorado (não encontrado): {i}")
    return files


def ensure_components(mgr: backend.EngineManager, allow: bool) -> bool:
    need = mgr.pending_downloads()
    if not need:
        return True
    _out("Componentes necessários (download único):")
    for n in need:
        _out(f"  - {n['label']} (~{n['size_mb']} MB)")
    if not allow:
        _out("Use --baixar para autorizar o download (somente modelos/bibliotecas; nenhum áudio é enviado).")
        return False
    last = [0.0]

    def prog(name, done, total):
        if time.monotonic() - last[0] > 3:
            _out(f"  baixando {name}: {done / 2**20:.0f}/{total / 2**20:.0f} MB")
            last[0] = time.monotonic()
    backend.install_components(need, prog)
    return True


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="TranscritorIA", description=APP_TITLE)
    ap.add_argument("--cli", nargs="*", metavar="AUDIO", help="transcreve arquivos/pastas sem interface")
    ap.add_argument("--saida", help="pasta de destino dos textos")
    ap.add_argument("--modelo", default=None, help="auto | large-v3 | large-v3-turbo | medium | small | tiny")
    ap.add_argument("--motor", default=None, choices=["auto", "cuda", "vulkan", "cpu", "wcpp-cpu"])
    ap.add_argument("--perfil", default=None, choices=["turbo", "trabalho"])
    ap.add_argument("--trilha", type=int, default=None,
                    help="trilha de áudio dos vídeos (1, 2…); padrão: automática, priorizando português")
    ap.add_argument("--analisar", nargs="+", metavar="ARQUIVO", help="mostra contêiner e trilhas de áudio")
    ap.add_argument("--srt", action="store_true")
    ap.add_argument("--tempos", action="store_true", help="também gera TXT com marcações de tempo")
    ap.add_argument("--baixar", action="store_true", help="autoriza baixar modelo/bibliotecas que faltarem")
    ap.add_argument("--diagnostico", action="store_true")
    ap.add_argument("--desempenho", action="store_true", help="teste de desempenho completo")
    ap.add_argument("--autoteste", action="store_true", help="transcreve o áudio de referência e mede WER")
    ap.add_argument("--relatorio", help="grava resultado (JSON) neste arquivo")
    ap.add_argument("--recalibrar", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if sys.platform == "win32":  # acentos corretos no Prompt de Comando
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    logs.setup(a.verbose)
    s = Settings.load()
    if a.modelo:
        s.model = a.modelo
    if a.motor:
        s.engine = a.motor
    if a.perfil:
        s.profile = a.perfil
    s.export_srt = s.export_srt or a.srt
    s.export_txt_timestamps = s.export_txt_timestamps or a.tempos
    report: dict = {"versao": __version__}
    rc = 0
    _out(f"{APP_TITLE} {__version__} — dados em {paths.data_dir()}")
    hw = hardware.detect()
    for line in hardware.describe(hw):
        _out(line)
    report["hardware"] = hw.to_dict()
    if a.recalibrar:
        backend.forget_profiles()
    mgr = backend.EngineManager(hw, s.model, s.engine, s.profile, notify=lambda m: _out(m))
    cands = mgr.candidates()
    report["candidatos"] = [c.key() for c in cands]
    _out("Mecanismos candidatos: " + ", ".join(f"{c.accel}/{c.model_key}" for c in cands))

    if a.analisar:
        from . import media
        report["analise"] = []
        for f in a.analisar:
            try:
                i = media.probe(f)
                report["analise"].append(i.to_dict())
                _out(f"{i.kind_label} [{i.container}] {Path(f).name}: {audio.fmt_hms(i.duration)} "
                     f"(análise: {i.prober})")
                for t in i.tracks:
                    mark = "  <- escolhida (" + i.reason + ")" if t.ordinal == i.selected else ""
                    _out(f"   {t.label()}{mark}")
                if not i.tracks:
                    _out("   sem trilha de áudio")
            except media.MediaError as e:
                _out(f"ERRO {f}: {e}")
                rc = 7
    if a.diagnostico:
        from . import media
        _out(f"FFprobe: {media.tool('ffprobe') or 'não incluído'} | FFmpeg: {media.tool('ffmpeg') or 'não incluído'}")
        _out("Vulkan loader: " + ("sim" if hw.vulkan_loader else "não"))
        try:
            import ctranslate2
            import faster_whisper  # noqa: F401

            from . import segmenter
            ref = audio.decode(paths.assets_dir() / "referencia_calibracao.mp3")
            fala = segmenter.detect_speech(ref)
            _out(f"Leitura de áudio e detecção de voz: OK ({len(ref) / 16000:.1f} s, {len(fala)} trecho(s) de fala)")
            _out(f"CTranslate2 {ctranslate2.__version__}: GPUs CUDA visíveis = "
                 f"{ctranslate2.get_cuda_device_count()}")
            report["diagnostico_ok"] = True
        except Exception as e:  # noqa: BLE001
            _out(f"FALHA no diagnóstico interno: {e}")
            report["diagnostico_ok"] = False
            rc = 6
        from .engines import whispercpp_engine
        _out(f"whisper.cpp Vulkan: {whispercpp_engine.find_cli(True) or 'não incluído'} | "
             f"CPU: {whispercpp_engine.find_cli(False) or 'não incluído'}")
        for c in cands:
            miss = backend.missing_components(c)
            _out(f"  {c.accel} {c.gpu_name or ''} {c.model_key}: " +
                 ("pronto" if not miss else "falta " + ", ".join(m["label"] for m in miss)))
    if a.desempenho:
        if not ensure_components(mgr, a.baixar):
            return 3
        rep = benchmark.run(hw, s.model, _out)
        _out(benchmark.format_report(rep))
        report["desempenho"] = rep
    if a.autoteste:
        if not ensure_components(mgr, a.baixar):
            return 3
        t0 = time.monotonic()
        choice = mgr.start()
        ref = paths.assets_dir() / "referencia_calibracao.mp3"
        out = Path(a.saida or (paths.data_dir() / "autoteste"))
        out.mkdir(parents=True, exist_ok=True)
        tasks = [FileTask(ref)]
        summ = QueueRunner(tasks, out, s, mgr, CliCallbacks(), Controller()).run()
        txt = Path(tasks[0].outputs[0]).read_text(encoding="utf-8") if tasks[0].outputs else ""
        body = txt.split("TRANSCRIÇÃO", 1)[-1].split("—" * 40)[0]
        ref_txt = (paths.assets_dir() / "referencia_calibracao.txt").read_text(encoding="utf-8")
        w = metrics.wer(ref_txt, body)
        report["autoteste"] = {"motor": mgr.info(), "escolha": choice.to_dict(), "wer": round(w, 3),
                               "texto": body.strip(), "segundos": round(time.monotonic() - t0, 1),
                               "resumo": {k: v for k, v in summ.items() if k != "arquivos"}}
        _out(f"Autoteste: WER = {w:.1%} | acelerador real: {mgr.info().get('aceleracao')}")
        rc = 0 if summ["ok"] == 1 and w < 0.6 else 4
    if a.cli is not None:
        files = _expand(a.cli)
        if not files:
            _out("Nenhum arquivo de áudio informado.")
            return 2
        outdir = Path(a.saida or s.output_dir or files[0].parent)
        outdir.mkdir(parents=True, exist_ok=True)
        if not ensure_components(mgr, a.baixar):
            return 3
        tasks = [FileTask(f, track=(a.trilha - 1) if a.trilha else None) for f in files]
        for t in tasks:
            try:
                i = t.analyze()
                _out(f"{i.kind_label}: {t.path.name} ({audio.fmt_hms(i.duration)}, {len(i.tracks)} trilha(s) de áudio"
                     + (f"; usando {i.tracks[t.track_used].label()} — {i.reason if t.track is None else 'escolha manual'}"
                        if i.tracks and t.track_used is not None and t.track_used < len(i.tracks) else "") + ")")
            except audio.AudioError as e:
                _out(f"Arquivo ilegível: {t.path.name}: {e}")
        summ = QueueRunner(tasks, outdir, s, mgr, CliCallbacks(), Controller()).run()
        report["transcricao"] = {k: v for k, v in summ.items()}
        report["motor"] = mgr.info()
        rc = 0 if summ["erro"] == 0 and summ["ok"] == len(files) else 5
    if a.relatorio:
        Path(a.relatorio).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    mgr.close()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
