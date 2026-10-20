"""Leitura completa dos PDFs da aula (PyMuPDF).

Para cada página extrai: texto com tamanhos de fonte (título = maior fonte),
blocos, tabelas da camada de texto, imagens (quantidade e área ocupada),
referências bibliográficas impressas no slide, e uma renderização da página.

Classificação da página:
  texto      — conteúdo essencialmente textual
  misto      — texto + imagens (ultrassonografias, esquemas)
  imagem     — slide "achatado" em imagem ou figura sem texto extraível
               (exige o modelo de visão para ser compreendido)
  divisoria  — separador curto ("Caso 1", "Isomerismo direito")
  capa       — primeira página com título/professor/curso

Nada aqui interpreta o conteúdo médico: só extrai o que está impresso.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .. import logs
from ..util import natural_key, words

log = logs.get("slides")

_REF_HINT = re.compile(
    r"(^fonte\s*:|practical guide|guide to|textbook|atlas de|\bet al\b|j\.? ?ultrasound|journal|annals of|"
    r"obstet(rical|rics)? (and|&) gynecol|gynecol(ogical)? survey|ultrasound obstet|\bdoi\b|pubmed|"
    r"\b(19|20)\d{2}\s*;\s*\d+\s*(\(\d+\))?\s*:\s*\d+|volume\s+\d+,?\s+number|\b\d+(ª|a)?\s*ed\.)",
    re.I,
)
_URL = re.compile(r"(www\.|https?://|\.com\b|\.br\b)", re.I)
_PROF = re.compile(r"^\s*prof(essor|essora|\.|a\.)?\s*(dr\.?|dra\.?)?\s*:?\s*(.*)$", re.I)
_COURSE = re.compile(r"(p[óo]s[- ]?gradua|m[óo]dulo|curso|especializa|resid[êe]ncia|aula\s+\d)", re.I)


@dataclass
class Tabela:
    cabecalho: List[str]
    linhas: List[List[str]]


@dataclass
class Pagina:
    deck: int
    num: int                  # 1-based
    id: str                   # "A1-p12"
    texto: str = ""
    titulo: str = ""
    linhas: List[str] = field(default_factory=list)
    referencias: List[str] = field(default_factory=list)
    tabelas: List[Tabela] = field(default_factory=list)
    n_imagens: int = 0
    area_imagens: float = 0.0  # fração da página coberta por imagens
    n_palavras: int = 0
    tipo: str = "texto"
    render: str = ""           # JPEG da página (caminho relativo ao projeto)
    render_hash: str = ""
    duplicata_de: str = ""     # página idêntica já vista (mesmo render)
    largura: float = 0.0
    altura: float = 0.0

    @property
    def precisa_visao(self) -> bool:
        return self.tipo in ("imagem", "misto", "capa") or self.n_palavras < 25


@dataclass
class Deck:
    idx: int
    arquivo: str
    titulo: str = ""
    professor: str = ""
    curso: str = ""
    paginas: List[Pagina] = field(default_factory=list)
    referencias: List[str] = field(default_factory=list)

    @property
    def rotulo(self) -> str:
        return self.titulo or Path(self.arquivo).stem

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Deck":
        pags = []
        for p in d["paginas"]:
            p = dict(p)
            p["tabelas"] = [Tabela(**t) for t in p.get("tabelas", [])]
            pags.append(Pagina(**p))
        return cls(idx=d["idx"], arquivo=d["arquivo"], titulo=d["titulo"], professor=d["professor"],
                   curso=d["curso"], paginas=pags, referencias=d.get("referencias", []))


def _title_case(name: str) -> str:
    if name.isupper():
        small = {"de", "da", "do", "dos", "das", "e"}
        return " ".join(w.lower() if w.lower() in small else w.capitalize() for w in name.split())
    return name


def _spans(page) -> List[dict]:
    out = []
    d = page.get_text("dict")
    for b in d.get("blocks", []):
        for line in b.get("lines", []):
            txt = "".join(s["text"] for s in line.get("spans", [])).strip()
            if not txt:
                continue
            size = max((s["size"] for s in line["spans"]), default=0)
            bold = any("bold" in s.get("font", "").lower() or (s.get("flags", 0) & 16) for s in line["spans"])
            out.append({"text": txt, "size": round(size, 1), "bold": bold, "y": line["bbox"][1],
                        "x": line["bbox"][0], "block": b.get("number", 0)})
    return out


def _merge_lines(spans: List[dict]) -> List[str]:
    """Junta linhas do mesmo bloco com o mesmo tamanho (títulos quebrados em 2 linhas)."""
    out: List[str] = []
    prev = None
    for s in spans:
        if prev and s["block"] == prev["block"] and abs(s["size"] - prev["size"]) < 0.6 and s["size"] >= 20:
            out[-1] = (out[-1] + " " + s["text"]).strip()
        else:
            out.append(s["text"])
        prev = s
    return out


def _cover_metadata(spans: List[dict]) -> dict:
    meta = {"titulo": "", "professor": "", "curso": ""}
    if not spans:
        return meta
    prof_size = None
    for s in spans:
        m = _PROF.match(s["text"])
        if m and s["text"].lower().startswith("prof"):
            prof_size = s["size"]
            rest = (m.group(3) or "").strip()
            if rest and not _URL.search(rest):
                meta["professor"] = _title_case(rest)
            break
    if prof_size and not meta["professor"]:
        cands = [s for s in spans if abs(s["size"] - prof_size) <= 3 and not _URL.search(s["text"])
                 and not s["text"].lower().startswith("prof") and not _COURSE.search(s["text"])
                 and 1 < len(s["text"].split()) <= 5 and not re.search(r"\d", s["text"])]
        if cands:
            meta["professor"] = _title_case(cands[0]["text"])
    for s in spans:
        if _COURSE.search(s["text"]) and not _URL.search(s["text"]):
            meta["curso"] = s["text"].strip()
            break
    big = max(s["size"] for s in spans)
    tit = [s for s in spans if s["size"] >= big - 2 and not _URL.search(s["text"])]
    meta["titulo"] = re.sub(r"\s+", " ", " ".join(s["text"] for s in tit)).strip()
    if meta["titulo"].isupper():
        meta["titulo"] = meta["titulo"].capitalize()
    return meta


def _tables(page) -> List[Tabela]:
    out: List[Tabela] = []
    try:
        found = page.find_tables()
    except Exception:  # noqa: BLE001
        return out
    for t in getattr(found, "tables", []) or []:
        try:
            rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in t.extract()]
        except Exception:  # noqa: BLE001
            continue
        rows = [r for r in rows if any(r)]
        if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
            out.append(Tabela(cabecalho=rows[0], linhas=rows[1:]))
    return out


def classificar(p: Pagina, primeira: bool) -> str:
    if primeira:
        return "capa"
    if p.n_palavras <= 6 and p.area_imagens < 0.5 and p.n_palavras > 0:
        return "divisoria"
    if p.n_palavras < 15 and p.area_imagens >= 0.3:
        return "imagem"
    if p.n_palavras == 0:
        return "imagem"
    if p.area_imagens >= 0.15:
        return "misto"
    return "texto"


def ler_pdf(path: Path, deck_idx: int, render_dir: Optional[Path] = None, dpi: int = 96,
            progress: Optional[Callable[[int, int], None]] = None) -> Deck:
    import pymupdf

    path = Path(path)
    doc = pymupdf.open(str(path))
    if doc.needs_pass:
        raise ValueError(f"O PDF {path.name} está protegido por senha.")
    deck = Deck(idx=deck_idx, arquivo=path.name)
    seen_hash = {}
    refs_all: List[str] = []
    for i, page in enumerate(doc):
        pid = f"A{deck_idx}-p{i + 1}"
        spans = _spans(page)
        lines = _merge_lines(spans)
        texto = "\n".join(lines)
        refs = [ln for ln in lines if _REF_HINT.search(ln) and 15 < len(ln) < 320
                and not _URL.match(ln) and not ln.lstrip().startswith(("•", "-", "–", "▪", "●"))]
        conteudo = [ln for ln in lines if ln not in refs and not _URL.search(ln)]
        p = Pagina(deck=deck_idx, num=i + 1, id=pid, texto="\n".join(conteudo), linhas=conteudo,
                   referencias=refs, largura=page.rect.width, altura=page.rect.height)
        p.n_palavras = len(words(" ".join(conteudo)))
        try:
            info = page.get_image_info()
        except Exception:  # noqa: BLE001
            info = []
        p.n_imagens = len(info)
        parea = max(1.0, page.rect.width * page.rect.height)
        area = 0.0
        for b in info:
            x0, y0, x1, y1 = b["bbox"]
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, page.rect.width), min(y1, page.rect.height)
            area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
        p.area_imagens = round(min(1.0, area / parea), 3)
        body = [s for s in spans if s["text"] in conteudo or any(s["text"] in c for c in conteudo)]
        if body:
            big = max(s["size"] for s in body)
            p.titulo = " ".join(s["text"] for s in body if s["size"] >= big - 1)[:160].strip()
        p.tabelas = _tables(page) if p.n_palavras >= 8 else []
        p.tipo = classificar(p, i == 0)
        if i == 0:
            meta = _cover_metadata(spans)
            deck.titulo, deck.professor, deck.curso = meta["titulo"], meta["professor"], meta["curso"]
        if render_dir is not None:
            render_dir.mkdir(parents=True, exist_ok=True)
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=88)
            h = hashlib.sha1(pix.samples).hexdigest()[:16]
            p.render_hash = h
            if h in seen_hash:
                p.duplicata_de = seen_hash[h]
            else:
                seen_hash[h] = pid
            fn = render_dir / f"{pid}.jpg"
            fn.write_bytes(data)
            p.render = fn.name
        for r in refs:
            if r not in refs_all:
                refs_all.append(r)
        deck.paginas.append(p)
        if progress:
            progress(i + 1, doc.page_count)
    deck.referencias = refs_all
    if not deck.titulo:
        deck.titulo = path.stem.replace("_", " ")
    log.info("PDF %s: %d páginas (%s)", path.name, len(deck.paginas),
             ", ".join(f"{t}={sum(1 for p in deck.paginas if p.tipo == t)}"
                       for t in ("texto", "misto", "imagem", "divisoria")))
    doc.close()
    return deck


def render_figura(pdf_path: Path, num: int, dest: Path, dpi: int = 160) -> Path:
    """Renderização em alta qualidade de uma página (figura da apostila), sem deformação."""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as doc:
        page = doc[num - 1]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.suffix.lower() in (".jpg", ".jpeg"):
            dest.write_bytes(pix.tobytes("jpeg", jpg_quality=90))
        else:
            pix.save(str(dest))
    return dest


def ordenar_pdfs(paths: List[Path]) -> List[Path]:
    return sorted((Path(p) for p in paths), key=lambda p: natural_key(p.name))
