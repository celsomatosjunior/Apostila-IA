"""Glossário médico local.

O Whisper aceita um "prompt inicial": texto que orienta grafia de termos técnicos e
estilo de pontuação. Ele NÃO acrescenta conteúdo ao texto — apenas aumenta a chance
de o termo ouvido ser grafado corretamente (ex.: "pré-eclâmpsia", "HELLP", "DUM").
O usuário pode editar o arquivo glossario_medico.txt (um termo por linha).
O prompt é limitado (~200 tokens) por restrição do próprio Whisper.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from . import paths

MAX_PROMPT_CHARS = 620
HEADER = "Aula de medicina, em português do Brasil, com pontuação. Termos: "


def user_file() -> Path:
    p = paths.config_dir() / "glossario_medico.txt"
    if not p.exists():
        default = paths.assets_dir() / "glossario_medico.txt"
        if default.exists():
            shutil.copyfile(default, p)
        else:
            p.write_text("# Um termo por linha. Linhas com # são ignoradas.\n", encoding="utf-8")
    return p


def terms() -> List[str]:
    out = []
    for line in user_file().read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and t not in out:
            out.append(t)
    return out


def build_prompt(enabled: bool = True) -> str:
    if not enabled:
        return ""
    prompt = HEADER
    first = True
    for t in terms():
        piece = ("" if first else ", ") + t
        if len(prompt) + len(piece) + 1 > MAX_PROMPT_CHARS:
            break
        prompt += piece
        first = False
    return prompt + "." if not first else ""
