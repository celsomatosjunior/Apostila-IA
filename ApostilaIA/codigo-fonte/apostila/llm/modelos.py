"""Catálogo de modelos locais (GGUF) e escolha automática conforme o hardware.

Critérios (nesta ordem): fidelidade, redação em português, leitura de slides,
estabilidade e desempenho — não o número de parâmetros.

  Conjunto A — qualidade máxima (RAM >= 28 GB):
      texto: Qwen3-30B-A3B-Instruct-2507 (MoE, 3B ativos por token: rápido mesmo
             com especialistas na RAM; excelente em português e em seguir instruções)
      visão: Qwen3-VL-8B-Instruct + projetor multimodal
      carregados em sequência (nunca juntos)
  Conjunto B — econômico (RAM >= 14 GB ou GPU >= 8 GB):
      texto e visão: Qwen3-VL-8B-Instruct (um único modelo carregado)
  Conjunto C — computadores modestos:
      texto e visão: Qwen3-VL-4B-Instruct

Tamanhos e SHA-256 conferidos na API pública do Hugging Face (out/2026). Na hora do
download o SHA-256 é consultado de novo na própria API (fonte autoritativa) e o
arquivo baixado é verificado antes de ser usado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .. import paths


@dataclass(frozen=True)
class Arquivo:
    repo: str
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Modelo:
    key: str
    label: str
    gguf: Arquivo
    mmproj: Optional[Arquivo] = None
    moe: bool = False
    ctx_texto: int = 32768
    ctx_visao: int = 8192

    @property
    def files(self) -> List[Arquivo]:
        return [self.gguf] + ([self.mmproj] if self.mmproj else [])

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)

    def local(self, f: Arquivo, base: Optional[Path] = None) -> Path:
        return (base or paths.models_dir()) / self.key / f.path

    def instalado(self, base: Optional[Path] = None) -> bool:
        return all(self.local(f, base).exists() and self.local(f, base).stat().st_size == f.size
                   for f in self.files)


QWEN3_30B = Modelo(
    key="qwen3-30b-a3b-2507",
    label="Qwen3 30B-A3B Instruct 2507 (MoE, Q4_K_XL)",
    gguf=Arquivo("unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF",
                 "Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf", 17690497440,
                 "535f831bf3034a7fcfdcc8f0277a57cbad3a36c650c6068bf1d0894f25fb4383"),
    moe=True,
)
QWEN3_VL_8B = Modelo(
    key="qwen3-vl-8b",
    label="Qwen3-VL 8B Instruct (Q4_K_M) + visão",
    gguf=Arquivo("Qwen/Qwen3-VL-8B-Instruct-GGUF", "Qwen3VL-8B-Instruct-Q4_K_M.gguf", 5027784800,
                 "67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2"),
    mmproj=Arquivo("Qwen/Qwen3-VL-8B-Instruct-GGUF", "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf", 752289728,
                   "c6ba85508d82f42590e6eb77d5340369ab6fecf107a7561d809523d8aa5f3bfd"),
    ctx_texto=24576,
)
QWEN3_VL_4B = Modelo(
    key="qwen3-vl-4b",
    label="Qwen3-VL 4B Instruct (Q4_K_M) + visão",
    gguf=Arquivo("Qwen/Qwen3-VL-4B-Instruct-GGUF", "Qwen3VL-4B-Instruct-Q4_K_M.gguf", 2497281664,
                 "66358cb18bb6b3b1b6675aa412c7a88ef01d228f481184d13668e5201c730a0a"),
    mmproj=Arquivo("Qwen/Qwen3-VL-4B-Instruct-GGUF", "mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf", 453974304,
                   "30ba2c7dd3127a4561b6cba9d13d0f711c91bdb38742e2f56d73c8cb596bd06d"),
    ctx_texto=16384,
)

MODELOS: Dict[str, Modelo] = {m.key: m for m in (QWEN3_30B, QWEN3_VL_8B, QWEN3_VL_4B)}


@dataclass
class Conjunto:
    key: str
    label: str
    texto: Modelo
    visao: Modelo
    motivo: str = ""

    @property
    def modelos(self) -> List[Modelo]:
        return [self.texto] if self.texto.key == self.visao.key else [self.texto, self.visao]

    @property
    def size(self) -> int:
        return sum(m.size for m in self.modelos)

    def faltando(self, base: Optional[Path] = None) -> List[Modelo]:
        return [m for m in self.modelos if not m.instalado(base)]


CONJUNTOS = {
    "A": ("Qualidade máxima", QWEN3_30B, QWEN3_VL_8B),
    "B": ("Econômico", QWEN3_VL_8B, QWEN3_VL_8B),
    "C": ("Leve", QWEN3_VL_4B, QWEN3_VL_4B),
}


def conjunto(key: str, motivo: str = "") -> Conjunto:
    label, t, v = CONJUNTOS[key]
    return Conjunto(key=key, label=label, texto=t, visao=v, motivo=motivo)


def recomendar(hw) -> Conjunto:
    """Escolha automática pelo hardware real (RAM total e VRAM da melhor GPU)."""
    ram_gb = hw.ram_total_mb / 1024
    g = hw.best_gpu()
    vram_gb = (g.vram_total_mb / 1024) if (g and not g.integrated) else 0
    if ram_gb >= 28 or (ram_gb >= 22 and vram_gb >= 12):
        return conjunto("A", f"{ram_gb:.0f} GB de RAM" + (f" e {vram_gb:.0f} GB de VRAM" if vram_gb else "")
                        + ": cabe o modelo de 30B (MoE) dividido entre GPU e RAM")
    if ram_gb >= 14 or vram_gb >= 8:
        return conjunto("B", f"{ram_gb:.0f} GB de RAM: modelo único de 8B (texto e visão)")
    return conjunto("C", f"{ram_gb:.0f} GB de RAM: modelo leve de 4B")


def escolher(hw, preferencia: str = "auto") -> Conjunto:
    if preferencia in CONJUNTOS:
        return conjunto(preferencia, "escolhido nas configurações avançadas")
    rec = recomendar(hw)
    # se o recomendado não está baixado mas outro conjunto completo está, usa o disponível
    if rec.faltando():
        for k in ("A", "B", "C"):
            c = conjunto(k)
            if not c.faltando():
                return conjunto(k, f"conjunto {k} já instalado (recomendado: {rec.key})")
    return rec
