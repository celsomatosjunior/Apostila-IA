"""Gerenciador do modelo local: escolhe backend (CUDA → Vulkan → CPU), carrega um
modelo por vez (texto ou visão), verifica o uso real da GPU e faz fallback.

Modo Turbo: todos os núcleos físicos, margem de VRAM de 1 GB.
Modo Trabalho: metade dos núcleos, prioridade baixa, margem de VRAM de 2,5 GB
(sobra memória para o navegador e outros programas).
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import psutil

from .. import logs, paths
from . import runtime
from .cliente import LlamaLLM, LLMBase
from .modelos import Conjunto, Modelo
from .servidor import Config, LlamaServer, ServidorErro

log = logs.get("motor")


@dataclass
class Candidato:
    backend: str
    exe: Path
    device: str = ""
    nome_gpu: str = ""
    vram_mb: int = 0


class MotorErro(RuntimeError):
    pass


class Motor:
    def __init__(self, hw, conjunto: Conjunto, modo: str = "turbo", backend_pref: str = "auto",
                 log_dir: Optional[Path] = None, status: Optional[Callable[[str], None]] = None,
                 models_base: Optional[Path] = None):
        self.hw = hw
        self.conjunto = conjunto
        self.modo = modo
        self.backend_pref = backend_pref
        self.log_dir = log_dir or paths.logs_dir()
        self.status = status or (lambda s: None)
        self.models_base = models_base
        self.srv: Optional[LlamaServer] = None
        self.llm: Optional[LlamaLLM] = None
        self.atual: Optional[str] = None  # chave do modelo carregado + papel
        self.candidatos: List[Candidato] = []
        self.falhas: List[str] = []
        self._lock = threading.Lock()
        self._vistos: List[LlamaLLM] = []

    def llms_vistos(self):
        return self._vistos

    # ----------------------------------------------------------- backends
    def descobrir(self) -> List[Candidato]:
        cands: List[Candidato] = []
        best = None
        discretas = [g for g in self.hw.gpus if not g.integrated]
        if discretas:
            best = max(discretas, key=lambda g: g.vram_total_mb)
        pref = self.backend_pref
        if best and best.vendor == "nvidia" and pref in ("auto", "cuda"):
            exe = runtime.server_path("cuda", best.name)
            if exe:
                devs = [d for d in runtime.list_devices(exe) if d.backend == "cuda"]
                if devs:
                    d = max(devs, key=lambda d: d.total_mb)
                    cands.append(Candidato("cuda", exe, d.id, d.nome, d.total_mb))
                else:
                    self.falhas.append("CUDA instalado, mas nenhum dispositivo CUDA respondeu")
        if best and pref in ("auto", "cuda", "vulkan"):
            exe = runtime.server_path("vulkan")
            if exe:
                devs = [d for d in runtime.list_devices(exe) if d.backend == "vulkan"]
                # ignora GPUs integradas (memória compartilhada não traz ganho real)
                toks = re.findall(r"\d{3,4}\w*", best.name.lower())
                match = [d for d in devs if any(t in d.nome.lower() for t in toks)] or devs
                if match:
                    d = max(match, key=lambda d: d.total_mb)
                    if d.total_mb >= 3000:
                        cands.append(Candidato("vulkan", exe, d.id, d.nome, d.total_mb))
                elif devs == []:
                    self.falhas.append("Vulkan: nenhum dispositivo (driver de vídeo sem suporte a Vulkan?)")
        exe = runtime.server_path("cpu") or runtime.server_path("vulkan")
        if exe:
            cands.append(Candidato("cpu", exe))
        if not cands:
            raise MotorErro("Componentes do llama.cpp não encontrados na pasta do programa. Reinstale o ApostilaIA.")
        self.candidatos = cands
        log.info("Backends candidatos: %s", [(c.backend, c.device, c.nome_gpu) for c in cands])
        return cands

    # ----------------------------------------------------------- carga
    def _threads(self) -> int:
        phys = max(1, self.hw.cores_physical)
        return max(2, phys // 2) if self.modo == "trabalho" else phys

    def _cfg(self, c: Candidato, modelo: Modelo, visao: bool, kv_quant: bool) -> Config:
        base = self.models_base
        mm = modelo.local(modelo.mmproj, base) if (modelo.mmproj and visao) else None
        ctx = modelo.ctx_visao if (visao and modelo.key != self.conjunto.texto.key) else modelo.ctx_texto
        return Config(exe=c.exe, model=modelo.local(modelo.gguf, base), mmproj=mm, ctx=ctx,
                      backend=c.backend, device=c.device, threads=self._threads(),
                      trabalho=self.modo == "trabalho",
                      fit_margin_mb=2560 if self.modo == "trabalho" else 1024, kv_quant=kv_quant)

    def _verificar_memoria(self, modelo: Modelo) -> None:
        livre = psutil.virtual_memory().available
        vram = 0
        for c in self.candidatos:
            if c.backend != "cpu":
                vram = max(vram, c.vram_mb * 1024 * 1024)
        if livre + vram * 0.85 < modelo.size * 1.05:
            log.warning("Memória livre (%.1f GB RAM + %.1f GB VRAM) menor que o modelo (%.1f GB)",
                        livre / 2**30, vram / 2**30, modelo.size / 2**30)
            self.status("Atenção: pouca memória livre — feche outros programas para evitar lentidão")

    def obter(self, papel: str, cancel: Optional[threading.Event] = None) -> LLMBase:
        """papel: 'texto' ou 'visao'. Descarrega o modelo anterior se for outro."""
        with self._lock:
            modelo = self.conjunto.visao if papel == "visao" else self.conjunto.texto
            visao = papel == "visao" or (self.conjunto.texto.key == self.conjunto.visao.key)
            chave = f"{modelo.key}|{'v' if visao else 't'}"
            if self.srv and self.srv.alive() and self.atual == chave:
                return self.llm
            if self.srv and self.srv.alive() and self.atual and self.atual.startswith(modelo.key + "|v") and not visao:
                return self.llm  # o mesmo modelo com visão também escreve texto
            self.liberar()
            if not self.candidatos:
                self.descobrir()
            if not modelo.instalado(self.models_base):
                raise MotorErro(f"Modelo {modelo.label} não está instalado. Use 'Preparar modelos'.")
            self._verificar_memoria(modelo)
            erros = []
            for c in list(self.candidatos):
                for kvq in (True, False):
                    cfg = self._cfg(c, modelo, visao, kvq)
                    rot = "CPU" if c.backend == "cpu" else f"{c.backend.upper()} {c.nome_gpu}"
                    self.status(f"Carregando {modelo.label} ({rot})…")
                    srv = LlamaServer(cfg, self.log_dir / "llama-server.log")
                    try:
                        srv.start(cancel=cancel)
                    except ServidorErro as e:
                        srv.stop()
                        if str(e) == "cancelado":
                            raise
                        erros.append(f"{rot}{'' if kvq else ' (KV f16)'}: {str(e).splitlines()[0]}")
                        log.warning("Falha ao carregar com %s (kv_quant=%s): %s", rot, kvq, e)
                        continue
                    if c.backend != "cpu" and not srv.gpu.verificada:
                        log.warning("%s carregou mas nenhuma camada foi para a GPU", rot)
                        self.falhas.append(f"{rot}: modelo carregado sem camadas na GPU")
                    self.srv = srv
                    self.llm = LlamaLLM(srv, modelo.label, suporta_visao=bool(cfg.mmproj))
                    self._vistos.append(self.llm)
                    self.atual = chave
                    self.backend_atual = c
                    return self.llm
            raise MotorErro("Não foi possível carregar o modelo em nenhum backend:\n" + "\n".join(erros))

    def reiniciar(self, papel: str, cancel=None) -> LLMBase:
        """Após falha do servidor (ex.: erro de driver), recarrega; na 2ª falha, cai para o próximo backend."""
        backend = getattr(self, "backend_atual", None)
        self.liberar()
        if backend is not None and getattr(self, "_falhou_" + backend.backend, False):
            self.candidatos = [c for c in self.candidatos if c is not backend] or self.candidatos
        elif backend is not None:
            setattr(self, "_falhou_" + backend.backend, True)
        return self.obter(papel, cancel)

    def liberar(self) -> None:
        if self.srv:
            self.srv.stop()
        self.srv = None
        self.llm = None
        self.atual = None

    def descricao(self) -> str:
        if not self.srv:
            return "—"
        c = getattr(self, "backend_atual", None)
        if c is None or c.backend == "cpu" or not self.srv.gpu.verificada:
            return f"CPU ({self._threads()} threads)"
        return f"{c.backend.upper()} — {self.srv.gpu.descricao()}"
