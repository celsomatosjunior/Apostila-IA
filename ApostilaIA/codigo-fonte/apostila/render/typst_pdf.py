"""PDF da apostila com Typst (motor de composição embutido, sem dependências externas).

Fontes IBM Plex (licença SIL OFL) embutidas no programa: o resultado é idêntico em
qualquer Windows. Sumário navegável, marcadores (bookmarks), cabeçalhos e paginação.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import logs
from .comum import fontes_dir, preparar, typst_dir

log = logs.get("pdf")


def compilar(template: Path, dados: dict, work: Path, saida, fmt: str = "pdf", ppi=None,
             nome_dados: str = "dados.json") -> bytes:
    import typst

    work.mkdir(parents=True, exist_ok=True)
    (work / nome_dados).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    for f in template.parent.glob("*.typ"):
        shutil.copyfile(f, work / f.name)
    main = work / template.name
    kw = {"root": str(work), "font_paths": [str(fontes_dir())], "ignore_system_fonts": True}
    if fmt != "pdf":
        kw["format"] = fmt
        if ppi:
            kw["ppi"] = ppi
    data = typst.compile(str(main), **kw)
    if isinstance(data, list):
        data = data[0]
    if saida is not None:
        saida.write_bytes(data)
    return data


def contar_paginas(pdf: Path) -> int:
    import pymupdf
    with pymupdf.open(str(pdf)) as d:
        return d.page_count


def gerar(apost: dict, saida: Path, work: Path) -> int:
    dados = preparar(apost, work)
    compilar(typst_dir() / "apostila.typ", dados, work, saida)
    n = contar_paginas(saida)
    log.info("PDF gerado: %s (%d páginas)", saida, n)
    return n


def esquema_png(bloco: dict, work: Path, saida: Path, ppi: int = 220) -> Path:
    """Esquema vetorial da apostila rasterizado para o DOCX (o PDF usa o vetor)."""
    dados = {"subtipo": bloco.get("subtipo", "sequencia"), "itens": bloco.get("itens", []), "texto": bloco.get("texto", "")}
    compilar(typst_dir() / "esquema.typ", dados, work, saida, fmt="png", ppi=ppi, nome_dados="esquema.json")
    return saida
