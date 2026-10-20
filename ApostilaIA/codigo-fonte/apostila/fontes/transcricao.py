"""Leitura das transcrições (TXT do TranscritorIA ou TXT simples).

Formato do TranscritorIA:
    AULA: <TÍTULO>
    Duração original: hh:mm:ss
    TRANSCRIÇÃO   (ou "TRANSCRIÇÃO COM MARCAÇÕES DE TEMPO", com linhas "[hh:mm:ss] texto")
    <parágrafos separados por linha em branco>
    ————————— (rodapé técnico, ignorado)

Vários arquivos = partes da mesma aula, em ordem natural do nome (Parte 1, 2, ... 10).
Cada parágrafo recebe um identificador estável "P<parte>.<n>" usado nas referências
internas (relatório de fidelidade) e nos checkpoints.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from ..util import est_tokens, natural_key

_HMS = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})$")
_TS_LINE = re.compile(r"^\[(\d{1,2}:\d{2}:\d{2})\]\s*(.*)$")
_FOOTER = re.compile(r"^[—–-]{10,}\s*$")
_SENT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ý0-9\"“(])")


def _hms_to_s(t: str) -> float:
    m = _HMS.match(t.strip())
    if not m:
        return 0.0
    h, mi, s = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + s


@dataclass
class Paragrafo:
    id: str
    parte: int
    n: int
    texto: str
    inicio: Optional[float] = None  # segundos, se o TXT tiver marcações de tempo

    @property
    def tokens(self) -> int:
        return est_tokens(self.texto)


@dataclass
class Parte:
    arquivo: str
    titulo: str
    duracao_s: float
    paragrafos: List[Paragrafo] = field(default_factory=list)


@dataclass
class Transcricao:
    partes: List[Parte] = field(default_factory=list)

    @property
    def paragrafos(self) -> List[Paragrafo]:
        return [p for parte in self.partes for p in parte.paragrafos]

    @property
    def duracao_s(self) -> float:
        return sum(p.duracao_s for p in self.partes)

    @property
    def palavras(self) -> int:
        return sum(len(p.texto.split()) for p in self.paragrafos)

    def por_id(self) -> dict:
        return {p.id: p for p in self.paragrafos}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcricao":
        return cls(partes=[Parte(arquivo=p["arquivo"], titulo=p["titulo"], duracao_s=p["duracao_s"],
                                 paragrafos=[Paragrafo(**q) for q in p["paragrafos"]])
                           for p in d["partes"]])


def _read_text(path: Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return txt
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _split_long(texto: str, max_tokens: int = 450) -> List[str]:
    """Parágrafos gigantes (TXT sem quebras) viram blocos de algumas frases."""
    if est_tokens(texto) <= max_tokens:
        return [texto]
    sents = _SENT.split(texto)
    if len(sents) == 1:  # sem pontuação: corta por palavras
        ws = texto.split()
        step = int(max_tokens * 3.3 / 6)
        return [" ".join(ws[i:i + step]) for i in range(0, len(ws), step)]
    out, cur = [], ""
    for s in sents:
        if cur and est_tokens(cur + " " + s) > max_tokens:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def ler_parte(path: Path, parte_idx: int) -> Parte:
    txt = _read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    lines = txt.split("\n")
    titulo = ""
    duracao = 0.0
    body_start = 0
    # cabeçalho do TranscritorIA (tolerante: só nas primeiras linhas)
    for i, line in enumerate(lines[:12]):
        s = line.strip()
        if s.upper().startswith("AULA:"):
            titulo = s.split(":", 1)[1].strip()
            body_start = i + 1
        elif s.lower().startswith("duração original:") or s.lower().startswith("duracao original:"):
            duracao = _hms_to_s(s.split(":", 1)[1])
            body_start = i + 1
        elif s.upper().startswith("TRANSCRIÇÃO") or s.upper().startswith("TRANSCRICAO"):
            body_start = i + 1
            break
    body = lines[body_start:]
    # rodapé técnico
    for i, line in enumerate(body):
        if _FOOTER.match(line.strip()):
            body = body[:i]
            break
    blocos: List[tuple] = []
    cur: List[str] = []
    cur_ts: Optional[float] = None
    for line in body + [""]:
        s = line.strip()
        if not s:
            if cur:
                blocos.append((" ".join(cur), cur_ts))
            cur, cur_ts = [], None
            continue
        m = _TS_LINE.match(s)
        if m:
            if cur:
                blocos.append((" ".join(cur), cur_ts))
                cur = []
            cur_ts = _hms_to_s(m.group(1))
            s = m.group(2)
        if s.startswith("[Nenhuma fala"):
            continue
        cur.append(s)
    paras: List[Paragrafo] = []
    for texto, ts in blocos:
        for piece in _split_long(re.sub(r"\s+", " ", texto).strip()):
            if piece:
                paras.append(Paragrafo(id=f"P{parte_idx}.{len(paras) + 1}", parte=parte_idx,
                                       n=len(paras) + 1, texto=piece, inicio=ts))
                ts = None
    if not titulo:
        titulo = Path(path).stem.replace("_", " ")
    return Parte(arquivo=Path(path).name, titulo=titulo, duracao_s=duracao, paragrafos=paras)


def ler_transcricoes(paths: List[Path]) -> Transcricao:
    ordered = sorted((Path(p) for p in paths), key=lambda p: natural_key(p.name))
    t = Transcricao()
    for i, p in enumerate(ordered, 1):
        parte = ler_parte(p, i)
        t.partes.append(parte)
    return t


def rotulo_paragrafo(pid: str, n_partes: int) -> str:
    """'P2.15' -> 'Parte 2, §15' (ou '§15' quando há uma só parte)."""
    m = re.match(r"P(\d+)\.(\d+)$", pid)
    if not m:
        return pid
    return f"§{m.group(2)}" if n_partes <= 1 else f"Parte {m.group(1)}, §{m.group(2)}"
