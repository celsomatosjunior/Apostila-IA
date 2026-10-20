"""Conferência de números (porcentagens, medidas, valores) entre fala, slides e apostila.

- Divergência fala × slide: mesmo assunto (palavras de contexto em comum), mesma
  unidade, valores diferentes -> vai para o relatório (nunca escolhemos um valor).
- Número na apostila que não existe em nenhuma fonte -> possível informação externa.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Set, Tuple

from ..util import content_words

_UNIDADES = r"(%|por\s*cento|mm\s*hg|mmhg|mm|cm/s|cm|bpm|semanas?|graus?|º|°|ml|kg|g\b|anos?|meses|dias|vezes|x)"
_NUM = re.compile(r"(?<![\w.,])(\d{1,4}(?:[.,]\d{1,3})?)(?:\s*(?:a|-|–|até|e)\s*(\d{1,4}(?:[.,]\d{1,3})?))?\s*" + _UNIDADES + "?", re.I)

_EXTENSO = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
            "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20,
            "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80,
            "noventa": 90, "cem": 100}
_EXT_RE = re.compile(r"\b(" + "|".join(_EXTENSO) + r")\s+(por\s*cento|semanas|graus|milímetros|centímetros)\b", re.I)


@dataclass
class Numero:
    valor: str
    valor2: str
    unidade: str
    contexto: List[str]
    fonte: str  # id do parágrafo ou slide
    trecho: str

    def to_dict(self):
        return asdict(self)


def _unid(u: str) -> str:
    u = (u or "").lower().replace(" ", "")
    if u in ("%", "porcento"):
        return "%"
    if u in ("º", "°", "grau", "graus"):
        return "graus"
    if u.startswith("semana"):
        return "semanas"
    if u in ("mmhg",):
        return "mmhg"
    return u


def _norm_num(v: str) -> str:
    v = v.replace(",", ".")
    if "." in v:
        v = v.rstrip("0").rstrip(".")
    return v


def extrair(texto: str, fonte: str) -> List[Numero]:
    out = []
    t = _EXT_RE.sub(lambda m: f"{_EXTENSO[m.group(1).lower()]} {m.group(2)}", texto)
    for m in _NUM.finditer(t):
        v1, v2, u = m.group(1), m.group(2) or "", m.group(3) or ""
        if not u and not v2:
            continue  # número solto (ex.: "caso 1") não é conferido
        a, b = max(0, m.start() - 90), min(len(t), m.end() + 60)
        # contexto = a oração que contém o número (até vírgula, ponto, ponto e vírgula ou quebra)
        ini = max(t.rfind(ch, 0, m.start()) for ch in ".;\n,") + 1
        fims = [t.find(ch, m.end()) for ch in ".;\n,"]
        fim = min([f for f in fims if f >= 0] or [len(t)])
        ctx = content_words(t[ini:m.start()])[-7:] + content_words(t[m.end():fim])[:4]
        out.append(Numero(_norm_num(v1), _norm_num(v2) if v2 else "", _unid(u), ctx, fonte, t[a:b].strip()))
    return out


def valores(texto: str) -> Set[str]:
    """Todos os números (normalizados) presentes num texto, inclusive soltos e por extenso."""
    t = _EXT_RE.sub(lambda m: f"{_EXTENSO[m.group(1).lower()]} {m.group(2)}", texto)
    vals = {_norm_num(x) for x in re.findall(r"\d{1,4}(?:[.,]\d{1,3})?", t)}
    for w, n in _EXTENSO.items():
        if re.search(rf"\b{w}\b", t, re.I):
            vals.add(str(n))
    return vals


@dataclass
class Divergencia:
    assunto: str
    fala: str
    slide: str
    fonte_fala: str
    fonte_slide: str
    trecho_fala: str
    trecho_slide: str


def divergencias(nums_fala: List[Numero], nums_slide: List[Numero],
                 proximos: Dict[str, Set[str]]) -> List[Divergencia]:
    """proximos: slide_id -> ids de parágrafos da(s) janela(s) associada(s) ao slide."""
    out: List[Divergencia] = []
    agreg: Dict[Tuple, Divergencia] = {}
    # para cada número falado, o número de slide mais parecido em assunto (mesma unidade)
    melhor: Dict[int, Tuple[int, Numero]] = {}
    for ns in nums_slide:
        perto = proximos.get(ns.fonte, set())
        cs = set(ns.contexto)
        for k, nf in enumerate(nums_fala):
            if nf.fonte not in perto or nf.unidade != ns.unidade or not ns.unidade:
                continue
            ov = len(cs & set(nf.contexto))
            if ov >= 2 and ov > melhor.get(k, (0, None))[0]:
                melhor[k] = (ov, ns)
    for k, (ov, ns) in melhor.items():
        nf = nums_fala[k]
        comuns = set(ns.contexto) & set(nf.contexto)
        if True:
            vs = {ns.valor, ns.valor2} - {""}
            vf = {nf.valor, nf.valor2} - {""}
            if vs & vf:
                continue
            # faixa do slide contém o valor falado? não é divergência
            try:
                if ns.valor2 and float(ns.valor) <= float(nf.valor) <= float(ns.valor2):
                    continue
            except ValueError:
                pass
            k = (ns.fonte, ns.valor, ns.valor2, nf.valor, nf.valor2)
            if k in agreg:
                d0 = agreg[k]
                if nf.fonte not in d0.fonte_fala.split(",") and d0.fonte_fala.count(",") < 3:
                    d0.fonte_fala += "," + nf.fonte
                continue
            fmt = lambda n: (f"{n.valor}{('–' + n.valor2) if n.valor2 else ''}".replace('.', ',')
                             + (n.unidade if n.unidade == '%' else ' ' + n.unidade))
            dv = Divergencia(" ".join(sorted(comuns)), fmt(nf), fmt(ns), nf.fonte, ns.fonte, nf.trecho, ns.trecho)
            agreg[k] = dv
            out.append(dv)
    return out


def numeros_sem_fonte(texto: str, fontes_vals: Set[str]) -> List[str]:
    out = []
    for n in extrair(texto, "apostila"):
        for v in (n.valor, n.valor2):
            if v and v not in fontes_vals:
                out.append(v + (n.unidade if n.unidade == "%" else (" " + n.unidade if n.unidade else "")))
    return out


def todos_valores(textos: Iterable[str]) -> Set[str]:
    s: Set[str] = set()
    for t in textos:
        s |= valores(t)
    return s
