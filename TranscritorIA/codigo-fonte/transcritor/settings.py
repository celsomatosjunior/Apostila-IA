"""Preferências do usuário (dados/config/config.json)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from . import paths


@dataclass
class Settings:
    model: str = "auto"              # auto | large-v3 | large-v3-turbo | medium | small
    engine: str = "auto"             # auto | cuda | vulkan | cpu
    profile: str = "turbo"           # turbo | trabalho
    language: str = "pt"
    output_dir: str = ""
    last_input_dir: str = ""
    export_srt: bool = False
    export_txt_timestamps: bool = False
    mark_uncertain: bool = True
    use_glossary: bool = True
    beam_size: int = 5
    open_folder_when_done: bool = True
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
