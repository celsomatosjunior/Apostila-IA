"""Montagem de um trabalho completo (usado pela interface e pela linha de comando)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from . import hardware, logs
from .llm import modelos
from .llm.cliente import Controle
from .monitor import Monitor
from .pipeline.orquestrador import Gerador, Resultado

log = logs.get("servico")


def criar_provedor(hw, settings, status: Callable[[str], None], simulador: bool = False):
    if simulador:
        from .llm.simulador import ProvedorSimulado
        return ProvedorSimulado(), "simulador"
    from .llm.motor import Motor
    conj = modelos.escolher(hw, settings.conjunto_modelos)
    falt = conj.faltando()
    if falt:
        raise RuntimeError("Modelos de IA ainda não instalados: " + ", ".join(m.label for m in falt) +
                           ". Use 'Preparar modelos' (download único, com sua autorização).")
    return Motor(hw, conj, modo=settings.modo, backend_pref=settings.backend, status=status), \
        f"{conj.key}:{conj.texto.key}+{conj.visao.key}"


def gerar(txts: List[Path], pdfs: List[Path], destino: Path, settings, hw=None,
          on_progress: Optional[Callable[[dict], None]] = None, on_status: Optional[Callable[[str], None]] = None,
          on_memoria=None, controle: Optional[Controle] = None, simulador: bool = False) -> Resultado:
    hw = hw or hardware.detect()
    ctl = controle or Controle()
    status = on_status or (lambda s: None)
    prov, key = criar_provedor(hw, settings, status, simulador)
    nv = next((g.index for g in hw.gpus if g.vendor == "nvidia" and not g.integrated), None)
    mon = Monitor(ctl, on_amostra=on_memoria, on_aviso=status, nvidia_idx=nv)
    mon.start()
    try:
        g = Gerador(txts, pdfs, destino, settings, prov, on_progress=on_progress, controle=ctl,
                    modelos_key=key, hw=hw)
        return g.executar()
    finally:
        mon.parar()
