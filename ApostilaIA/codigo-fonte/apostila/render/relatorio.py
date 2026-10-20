"""Relatório de fidelidade em PDF (Typst) — separado da apostila."""
from __future__ import annotations

from pathlib import Path

from .. import __version__
from ..settings import PERFIS
from ..util import fmt_hms
from .comum import typst_dir
from .typst_pdf import compilar


def gerar(rel: dict, apost: dict, saida: Path, work: Path) -> Path:
    r = dict(rel)
    r.setdefault("titulo", apost["titulo"])
    r.setdefault("data", apost.get("data", ""))
    r.setdefault("versao", __version__)
    r.setdefault("perfil", PERFIS.get(apost.get("perfil", ""), apost.get("perfil", "")))
    r.setdefault("entradas", {"txts": [], "pdfs": []})
    r.setdefault("execucao", {"modelos": "—", "aceleracao": "—", "tempo": "—"})
    r.setdefault("paginas_pdf", 0)
    d = r.get("duracao_s") or 0
    r["duracao"] = fmt_hms(d) if d else ""
    for k in ("removidas", "parciais", "numeros_sem_fonte", "omissoes", "reinseridas", "duplicados",
              "esquemas_removidos", "divergencias", "termos_corrigidos", "termos_conferir",
              "termos_duvidosos_modelo", "slides", "janelas_sem_slide", "avisos", "mapa", "checagens"):
        r.setdefault(k, [])
    for t in r["termos_duvidosos_modelo"]:
        for f in ("termo", "sugestao", "motivo", "paragrafo"):
            t.setdefault(f, "")
    compilar(typst_dir() / "relatorio.typ", r, work / "rel", saida, nome_dados="relatorio.json")
    return saida
