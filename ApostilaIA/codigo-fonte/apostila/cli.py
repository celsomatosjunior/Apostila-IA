"""Linha de comando (ApostilaIA-cli.exe) — diagnóstico, preparação e geração sem interface."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from . import __version__, hardware, logs
from .settings import PERFIS, Settings


def _print(*a):
    print(*a, flush=True)


def diagnostico() -> int:
    from .llm import modelos, runtime
    hw = hardware.detect()
    _print(f"ApostilaIA {__version__}")
    for line in hardware.describe(hw):
        _print(line)
    _print("Recursos da CPU:", ", ".join(hw.cpu_features) or "—")
    conj = modelos.recomendar(hw)
    _print(f"Conjunto de modelos recomendado: {conj.key} — {conj.label} ({conj.motivo})")
    for m in conj.modelos:
        _print(f"  {m.label}: {'instalado' if m.instalado() else 'não instalado'} ({m.size / 2**30:.1f} GB)")
    for b, exe in runtime.backends_disponiveis().items():
        devs = runtime.list_devices(exe)
        _print(f"llama.cpp {runtime.LLAMA_BUILD} [{b}]: " + ("; ".join(f"{d.id} {d.nome} ({d.total_mb} MB)" for d in devs)
                                                           or "nenhum dispositivo de GPU (CPU disponível)"))
    g = hw.best_gpu()
    if g and g.vendor == "nvidia":
        _print(f"CUDA ({runtime.cuda_variant(g.name)}): {'instalado' if runtime.cuda_instalado(g.name) else 'não instalado (opcional)'}")
    return 0


def preparar(sim: bool, conjunto: str) -> int:
    from . import preparo
    from .llm import modelos
    hw = hardware.detect()
    conj = modelos.escolher(hw, conjunto) if conjunto != "auto" else modelos.recomendar(hw)
    itens = preparo.itens_faltando(hw, conj)
    if not itens:
        _print("Tudo instalado. O programa funciona offline.")
        return 0
    total = sum(i["size"] for i in itens)
    for i in itens:
        _print(f"- {i['label']}: {i['size'] / 2**30:.1f} GB")
    if not sim:
        _print(f"Total: {total / 2**30:.1f} GB. Repita com --sim para autorizar o download.")
        return 2
    last = [0.0]

    def prog(n, d, t):
        import time
        if time.monotonic() - last[0] > 2:
            last[0] = time.monotonic()
            _print(f"  {n}: {d / 2**20:,.0f}/{t / 2**20:,.0f} MB")
    preparo.instalar(itens, prog, threading.Event())
    _print("Preparação concluída.")
    return 0


def main(argv) -> int:
    p = argparse.ArgumentParser(prog="ApostilaIA-cli", description="ApostilaIA — apostilas a partir de aulas (IA local)")
    p.add_argument("--cli", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--diagnostico", action="store_true", help="mostra hardware, backends e modelos")
    p.add_argument("--preparar", action="store_true", help="baixa os modelos (uma vez)")
    p.add_argument("--sim", action="store_true", help="autoriza o download em --preparar")
    p.add_argument("--txt", nargs="*", default=[], help="transcrições (TXT do TranscritorIA)")
    p.add_argument("--pdf", nargs="*", default=[], help="PDFs dos slides")
    p.add_argument("--destino", help="pasta de destino")
    p.add_argument("--perfil", choices=list(PERFIS), default=None)
    p.add_argument("--modo", choices=["turbo", "trabalho"], default=None)
    p.add_argument("--conjunto", choices=["auto", "A", "B", "C"], default="auto")
    p.add_argument("--backend", choices=["auto", "cuda", "vulkan", "cpu"], default=None)
    p.add_argument("--sem-visao", action="store_true")
    p.add_argument("--simulador", action="store_true", help="testes: usa o simulador extrativo, sem IA")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logs.setup(verbose=a.verbose)
    if a.diagnostico:
        return diagnostico()
    if a.preparar:
        return preparar(a.sim, a.conjunto)
    if not a.txt:
        p.print_help()
        return 1
    s = Settings.load()
    if a.perfil:
        s.perfil = a.perfil
    if a.modo:
        s.modo = a.modo
    if a.backend:
        s.backend = a.backend
    s.conjunto_modelos = a.conjunto
    if a.sem_visao:
        s.usar_visao = False
    destino = Path(a.destino or Path(a.txt[0]).parent)
    from . import servico

    def prog(d):
        if "frac" in d:
            eta = d.get("eta_s")
            _print(f"[{d['frac'] * 100:5.1f}%] {d.get('etapa', '')} — {d.get('detalhe', '')}"
                   + (f" (faltam ~{eta / 60:.0f} min)" if eta else "") + f" | {d.get('gpu', '')}")
    try:
        r = servico.gerar([Path(x) for x in a.txt], [Path(x) for x in a.pdf], destino, s, on_progress=prog,
                          on_status=lambda t: _print("•", t), simulador=a.simulador)
    except KeyboardInterrupt:
        _print("Interrompido. O progresso foi salvo; execute de novo para continuar.")
        return 130
    except Exception as e:  # noqa: BLE001
        logs.get("cli").exception("Falha")
        _print("ERRO:", e)
        return 1
    _print(f"PDF: {r.pdf} ({r.paginas} páginas)\nDOCX: {r.docx}\nRelatório: {r.relatorio}")
    for w in r.avisos:
        _print("Aviso:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
