"""Preparação comum dos dados da apostila para o PDF (Typst) e o DOCX."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict, List

from .. import paths
from ..fontes.transcricao import rotulo_paragrafo
from ..settings import PERFIS


def fontes_dir() -> Path:
    return paths.assets_dir() / "fonts"


def typst_dir() -> Path:
    return paths.assets_dir() / "typst"


def origem_slide(sid: str, aulas: List[dict]) -> str:
    m = re.match(r"A(\d+)-p(\d+)$", sid)
    if not m:
        return sid
    d, p = int(m.group(1)), int(m.group(2))
    rot = aulas[d - 1]["rotulo"] if 0 < d <= len(aulas) else f"PDF {d}"
    return f"{rot}, slide {p}"


def rotulo_fontes(fontes: List[str], aulas: List[dict], n_partes: int) -> str:
    ps = [f for f in fontes if f.startswith("P")]
    ss = [f for f in fontes if f.startswith("A")]
    out = []
    if ps:
        out.append("transcrição " + ", ".join(rotulo_paragrafo(p, n_partes) for p in ps[:6]) + ("…" if len(ps) > 6 else ""))
    if ss:
        out.append("; ".join(origem_slide(s, aulas) for s in ss[:5]) + ("…" if len(ss) > 5 else ""))
    return "; ".join(out)


def titulo_curto(t: str) -> str:
    return t if len(t) <= 70 else t[:67].rsplit(" ", 1)[0] + "…"


def preparar(apost: dict, work: Path) -> dict:
    """Copia figuras para a pasta de composição e completa campos padrão de cada bloco."""
    figs = work / "fig"
    figs.mkdir(parents=True, exist_ok=True)
    d = dict(apost)
    d["titulo_curto"] = titulo_curto(d["titulo"])
    d["perfil_rotulo"] = PERFIS.get(d.get("perfil", "equilibrada"), d.get("perfil", ""))
    caps = []
    for cap in apost["capitulos"]:
        secs = []
        for sec in cap["secoes"]:
            bl = []
            fontes = []
            for b in sec["blocos"]:
                nb = {"tipo": b["tipo"], "texto": b.get("texto", "") or "", "itens": list(b.get("itens", []) or []),
                      "subtipo": b.get("subtipo", "") or "", "cabecalho": list(b.get("cabecalho", []) or []),
                      "linhas": [list(r) for r in (b.get("linhas", []) or [])], "slide": b.get("slide", "") or "",
                      "fontes": list(b.get("fontes", []) or [])}
                fontes += [f for f in nb["fontes"] if f not in fontes]
                if nb["tipo"] == "figura":
                    src = Path(b.get("arquivo", ""))
                    if not src.exists():
                        continue
                    dst = figs / src.name
                    if not dst.exists():
                        shutil.copyfile(src, dst)
                    nb["arquivo"] = f"fig/{src.name}"
                    nb["arquivo_abs"] = str(dst)
                    nb["origem"] = origem_slide(nb["slide"], apost["aulas"])
                if nb["tipo"] == "tabela" and not nb["cabecalho"]:
                    continue
                bl.append(nb)
            if bl:
                secs.append({"titulo": sec.get("titulo", ""), "blocos": bl,
                             "fontes_rotulo": rotulo_fontes(fontes, apost["aulas"], apost.get("n_partes", 1))})
        if secs:
            caps.append({"num": cap["num"], "titulo": cap["titulo"], "secoes": secs})
    d["capitulos"] = caps
    return d
