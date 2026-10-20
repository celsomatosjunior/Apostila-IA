"""Preferências do usuário (dados/config/config.json)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from . import paths

PERFIS = {"compacta": "Compacta", "equilibrada": "Equilibrada", "fiel": "Fiel e detalhada"}


@dataclass
class Settings:
    perfil: str = "equilibrada"      # compacta | equilibrada | fiel
    modo: str = "turbo"              # turbo | trabalho
    conjunto_modelos: str = "auto"   # auto | A (qualidade máxima) | B (econômico) | C (leve)
    backend: str = "auto"            # auto | cuda | vulkan | cpu
    output_dir: str = ""
    last_input_dir: str = ""
    titulo_manual: str = ""
    usar_visao: bool = True          # analisar slides visuais com o modelo de visão
    incluir_figuras: bool = True
    incluir_esquemas: bool = True
    incluir_pontos_conferir: bool = True   # apêndice curto com termos/divergências a conferir
    mostrar_fontes_na_apostila: bool = False  # referências [§/slide] ao fim de cada seção
    remover_sem_suporte: bool = True  # auditoria remove frases sem sustentação nas fontes
    abrir_pasta_ao_concluir: bool = True
    consent_downloads: bool = False

    @staticmethod
    def path():
        return paths.config_dir() / "config.json"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        p = cls.path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                names = {f.name for f in fields(cls)}
                for k, v in data.items():
                    if k in names:
                        setattr(s, k, v)
            except Exception:  # noqa: BLE001
                pass
        return s

    def save(self) -> None:
        p = self.path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    def to_dict(self) -> dict:
        return asdict(self)
