"""Projeto em andamento e checkpoints (retomada após queda de energia, fechamento ou falha de GPU).

dados/projetos/<id>/
  projeto.json            entradas, perfil, modelos, estado das etapas
  fontes.json             transcrição + PDFs lidos
  render/A1-p3.jpg        páginas renderizadas (entrada do modelo de visão)
  cartoes/A1-p3.json      leitura visual de cada slide (um arquivo por slide)
  janelas.json            segmentação
  alinhamento.json        cruzamento fala × slides
  notas/j0007.json        notas de cada janela
  termos.json, plano.json
  capitulos/c03.json      cada capítulo concluído
  revisao.json            auditoria
  figuras/A2-p14.jpg      figuras em alta qualidade
O <id> depende do CONTEÚDO dos arquivos de entrada, do perfil e dos modelos; um
arquivo alterado nunca reaproveita resultados antigos. Os originais nunca são alterados.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import List, Optional

from .. import logs, paths
from ..util import file_fingerprint, load_json, save_json

log = logs.get("projeto")
PIPELINE_VERSION = 1


class Projeto:
    def __init__(self, txts: List[Path], pdfs: List[Path], perfil: str, modelos_key: str,
                 opcoes: dict, base: Optional[Path] = None):
        self.txts = [Path(p) for p in txts]
        self.pdfs = [Path(p) for p in pdfs]
        fp_in = file_fingerprint(self.txts + self.pdfs)
        # fontes (leitura/visão) dependem só dos arquivos + modelo de visão; redação depende do perfil
        self.id_fontes = hashlib.sha1(f"{fp_in}|{modelos_key}|v{PIPELINE_VERSION}".encode()).hexdigest()[:12]
        key = json.dumps({"p": perfil, "o": opcoes}, sort_keys=True)
        self.id = self.id_fontes + "-" + hashlib.sha1(key.encode()).hexdigest()[:6]
        root = base or paths.jobs_dir()
        self.dir = root / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        # leitura das fontes, visão e notas não dependem do perfil: cache compartilhado
        self.cache = root / "_cache" / self.id_fontes
        self.cache.mkdir(parents=True, exist_ok=True)
        meta = self.dir / "projeto.json"
        if not meta.exists():
            meta.write_text(json.dumps({"txts": [str(p) for p in self.txts], "pdfs": [str(p) for p in self.pdfs],
                                        "perfil": perfil, "modelos": modelos_key, "opcoes": opcoes,
                                        "versao": PIPELINE_VERSION}, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    _COMPARTILHADO = ("fontes.json", "render", "cartoes", "janelas.json", "alinhamento.json", "notas", "termos.json")

    def _base(self, name: str) -> Path:
        top = name.split("/")[0]
        return self.cache if top in self._COMPARTILHADO else self.dir

    def sub(self, name: str) -> Path:
        p = self._base(name) / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def ck(self, name: str) -> Path:
        return self._base(name) / name

    def load(self, name: str):
        return load_json(self.ck(name))

    def save(self, name: str, obj) -> None:
        p = self.ck(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        save_json(p, obj)

    def existe(self, name: str) -> bool:
        return self.load(name) is not None

    def limpar(self, tudo: bool = False) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        if tudo:
            shutil.rmtree(self.cache, ignore_errors=True)

    def etapas_concluidas(self) -> List[str]:
        out = []
        for n in ("fontes.json", "janelas.json", "alinhamento.json", "termos.json", "plano.json", "revisao.json"):
            if self.ck(n).exists():
                out.append(n)
        return out


def projetos_pendentes(base: Optional[Path] = None) -> List[dict]:
    base = base or paths.jobs_dir()
    out = []
    for d in sorted(base.iterdir() if base.exists() else [], key=lambda p: p.stat().st_mtime, reverse=True):
        meta = d / "projeto.json"
        if d.name.startswith("_") or not meta.exists() or (d / "concluido.json").exists():
            continue
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            if all(Path(p).exists() for p in m["txts"] + m["pdfs"]):
                m["dir"] = str(d)
                out.append(m)
        except Exception:  # noqa: BLE001
            continue
    return out
