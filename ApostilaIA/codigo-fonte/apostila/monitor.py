"""Monitoramento de RAM e VRAM durante o processamento (evita travar o computador).

Se a memória livre do sistema cair abaixo do limite crítico, o trabalho é pausado
automaticamente (o modelo para de gerar) e retomado quando a memória volta.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

from . import hardware, logs

log = logs.get("monitor")
CRITICO_MB = 700
RETOMA_MB = 1500


@dataclass
class Amostra:
    ram_total_mb: int = 0
    ram_livre_mb: int = 0
    ram_programa_mb: int = 0     # este programa + llama-server
    vram_total_mb: Optional[int] = None
    vram_livre_mb: Optional[int] = None
    cpu_percent: float = 0.0

    def texto(self) -> str:
        s = f"RAM: {self.ram_programa_mb / 1024:.1f} GB em uso pelo programa · {self.ram_livre_mb / 1024:.1f} GB livres"
        if self.vram_total_mb:
            usado = self.vram_total_mb - (self.vram_livre_mb or 0)
            s += f" · VRAM: {usado / 1024:.1f}/{self.vram_total_mb / 1024:.0f} GB"
        return s


def amostra(nvidia_idx: Optional[int] = None) -> Amostra:
    vm = psutil.virtual_memory()
    a = Amostra(ram_total_mb=vm.total // 2**20, ram_livre_mb=vm.available // 2**20)
    try:
        me = psutil.Process()
        rss = me.memory_info().rss
        for ch in me.children(recursive=True):
            try:
                rss += ch.memory_info().rss
            except psutil.Error:
                pass
        a.ram_programa_mb = rss // 2**20
        a.cpu_percent = psutil.cpu_percent(interval=None)
    except psutil.Error:
        pass
    if nvidia_idx is not None:
        for g in hardware._nvidia_smi():
            if g.index == nvidia_idx:
                a.vram_total_mb, a.vram_livre_mb = g.vram_total_mb, g.vram_free_mb
    return a


class Monitor(threading.Thread):
    def __init__(self, controle, on_amostra: Optional[Callable[[Amostra], None]] = None,
                 on_aviso: Optional[Callable[[str], None]] = None, nvidia_idx: Optional[int] = None,
                 intervalo: float = 2.0):
        super().__init__(daemon=True)
        self.ctl = controle
        self.on_amostra = on_amostra or (lambda a: None)
        self.on_aviso = on_aviso or (lambda s: None)
        self.nvidia_idx = nvidia_idx
        self.intervalo = intervalo
        self._stop = threading.Event()
        self.pausou = False
        self.ultima = Amostra()

    def run(self):
        n = 0
        while not self._stop.is_set():
            try:
                a = amostra(self.nvidia_idx if n % 3 == 0 else None)
                if a.vram_total_mb is None and self.ultima.vram_total_mb:
                    a.vram_total_mb, a.vram_livre_mb = self.ultima.vram_total_mb, self.ultima.vram_livre_mb
                self.ultima = a
                self.on_amostra(a)
                if a.ram_livre_mb < CRITICO_MB and not self.ctl.pause.is_set():
                    self.pausou = True
                    self.ctl.pause.set()
                    log.warning("Memória crítica (%d MB livres): pausa automática", a.ram_livre_mb)
                    self.on_aviso(f"Pouca memória livre ({a.ram_livre_mb} MB). Processamento pausado automaticamente; "
                                  "feche outros programas — ele continua sozinho quando a memória voltar.")
                elif self.pausou and a.ram_livre_mb > RETOMA_MB:
                    self.pausou = False
                    self.ctl.pause.clear()
                    self.on_aviso("Memória normalizada: processamento retomado.")
            except Exception as e:  # noqa: BLE001
                log.debug("monitor: %s", e)
            n += 1
            self._stop.wait(self.intervalo)

    def parar(self):
        self._stop.set()
