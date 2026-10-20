"""Ferramentas de texto locais e determinísticas (sem rede, sem modelos).

- TF-IDF esparso (palavras de conteúdo + n-gramas de caracteres), cosseno.
- Divisão em frases, limpeza de marcas de oralidade, similaridade entre trechos.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence

from ..util import content_words, norm_word, strip_accents, words

_SENT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ý0-9\"“(])")


def frases(texto: str) -> List[str]:
    return [s.strip() for s in _SENT.split(texto.strip()) if s.strip()]


def _char_ngrams(w: str, n=(3, 4, 5)) -> List[str]:
    w = f" {w} "
    out = []
    for k in n:
        out += [w[i:i + k] for i in range(max(0, len(w) - k + 1))]
    return out


def features(texto: str, chars: bool = True) -> Counter:
    cw = content_words(texto)
    c = Counter("w:" + w for w in cw)
    # bigramas de palavras de conteúdo (ex.: "situs solitus", "veia cava")
    c.update("b:" + a + "_" + b for a, b in zip(cw, cw[1:]))
    if chars:
        for w in cw:
            if len(w) >= 5:
                c.update("c:" + g for g in _char_ngrams(w))
    return c


class TfIdf:
    def __init__(self, docs: Sequence[str], chars: bool = True):
        self.chars = chars
        feats = [features(d, chars) for d in docs]
        df: Counter = Counter()
        for f in feats:
            df.update(f.keys())
        self.n = max(1, len(docs))
        self.idf = {t: math.log((1 + self.n) / (1 + d)) + 1 for t, d in df.items()}
        self.vecs = [self._vec(f) for f in feats]

    def _vec(self, f: Counter) -> Dict[str, float]:
        v = {}
        for t, tf in f.items():
            w = (1 + math.log(tf)) * self.idf.get(t, math.log(1 + self.n) + 1)
            if t.startswith("c:"):
                w *= 0.35  # n-gramas de caracteres pesam menos (tolerância a erros de grafia)
            elif t.startswith("b:"):
                w *= 1.4
            v[t] = w
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / nrm for t, x in v.items()}

    def vec(self, texto: str) -> Dict[str, float]:
        return self._vec(features(texto, self.chars))


def cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


# ------------------------------------------------------------------ oralidade
_FILLERS = [
    r"\bné\b\??", r"\btá\b\??", r"\bta\b\?", r"\bokay\b", r"\bok\b\??", r"\bentão assim\b", r"\bassim ó\b",
    r"(?<=[\s,])ó(?=[\s,.])", r"\bhum+\b", r"\bé{2,}\b", r"\bah+\b", r"\beh+\b", r"\bbeleza\?",
    r"\btipo assim\b",
]
_FILL_RE = re.compile("|".join(_FILLERS), re.I)


def limpar_oralidade(t: str) -> str:
    """Limpeza leve (o modelo faz a reescrita real). Usada no simulador e em verificações."""
    s = _FILL_RE.sub("", t)
    s = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", s, flags=re.I)  # palavras repetidas
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,;:])\1+", r"\1", s)
    s = re.sub(r"^[,;:\s]+", "", s)
    s = re.sub(r",\s*([.!?])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def shingles(t: str, k: int = 4) -> set:
    w = [norm_word(x) for x in words(t)]
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cobertura(frase: str, fonte_vocab: set) -> float:
    """Fração das palavras de conteúdo da frase presentes nas fontes (com tolerância de radical)."""
    cw = content_words(frase)
    if not cw:
        return 1.0
    ok = 0
    for w in cw:
        if w in fonte_vocab or w[:6] in fonte_vocab:
            ok += 1
    return ok / len(cw)


def vocab(textos: Iterable[str]) -> set:
    v = set()
    for t in textos:
        for w in content_words(t):
            v.add(w)
            v.add(w[:6])
    return v


def similar_ratio(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, strip_accents(a.lower()), strip_accents(b.lower())).ratio()
