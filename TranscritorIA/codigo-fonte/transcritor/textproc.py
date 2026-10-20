"""Reconstrução do texto: ordem, sobreposição, limpeza e parágrafos.

Regra fundamental: nada é inventado. As únicas alterações sobre a saída do modelo são
  1) remover o texto duplicado criado pela sobreposição entre blocos;
  2) remover loops de repetição típicos de falha do Whisper (mesma frase 3+ vezes);
  3) remover frases-fantasma conhecidas SOMENTE quando o próprio modelo indica baixa
     confiança/ausência de fala (ex.: "Legendas pela comunidade Amara.org");
  4) sinalizar [trecho incerto] / [inaudível] conforme a confiança do modelo;
  5) organizar em parágrafos pelas pausas naturais da fala.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .engines.base import ChunkResult, Seg
from .segmenter import Chunk

UNCERTAIN_LOGPROB = -1.0
INAUDIBLE_LOGPROB = -1.5

_HALLUCINATIONS = [
    r"legendas? (pela|por) comunidade amara\.?org", r"amara\.org", r"inscreva-se no canal",
    r"obrigad[oa] por assistir", r"legendado por", r"transcri[çc][ãa]o (e|por) legendas?",
    r"^\W*(tchau|valeu)[\W]*$", r"subt[ií]tulos? (realizados|por)", r"www\.\S+\.(com|org)",
    r"^\W*\.\.\.\W*$", r"^\W*música\W*$", r"^\W*\[m[úu]sica\]\W*$",
]
_HALLU_RE = re.compile("|".join(_HALLUCINATIONS), re.I)


def _norm_words(text: str) -> List[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", t)


def _tokens(text: str) -> List[str]:
    return text.split()


def _overlap_cut(prev_tail: List[str], cur_words: List[str], min_match: int = 2) -> int:
    """Quantas palavras do início de `cur_words` repetem o fim de `prev_tail`."""
    pn = [_norm_words(w) for w in prev_tail]
    cn = [_norm_words(w) for w in cur_words]
    pn = ["".join(x) for x in pn]
    cn = ["".join(x) for x in cn]
    best = 0
    max_k = min(len(pn), len(cn), 40)
    for k in range(max_k, min_match - 1, -1):
        if pn[-k:] == cn[:k] and any(cn[:k]):
            best = k
            break
    if best:
        return best
    # sobreposição curta pode conter uma única palavra; aceita se não for palavra
    # funcional curta ("de", "a", "o"), pois repetição real de palavra longa
    # exatamente na fronteira é improvável
    if pn and cn and pn[-1] == cn[0] and len(cn[0]) >= 4:
        return 1
    # tolera 1 palavra cortada na borda: procura o fim anterior dentro do início atual
    for k in range(min(len(pn), 25), min_match + 1, -1):
        tail = pn[-k:]
        for off in range(1, 4):
            if cn[off:off + k] == tail:
                return off + k
    return 0


def merge(chunks: Sequence[Chunk], results: Dict[int, ChunkResult]) -> List[Seg]:
    """Une os resultados na ordem original, removendo a duplicação da sobreposição."""
    out: List[Seg] = []
    for c in sorted(chunks, key=lambda x: x.index):
        r = results.get(c.index)
        if r is None:
            raise ValueError(f"Bloco {c.index} ausente na reconstrução")
        segs = [Seg(s.start, s.end, s.text, s.avg_logprob, s.no_speech_prob, s.compression_ratio)
                for s in r.segments if s.text and s.text.strip()]
        if c.overlap_prev > 0 and out and segs:
            prev_words: List[str] = []
            for p in reversed(out):
                prev_words = _tokens(p.text) + prev_words
                if len(prev_words) >= 40 or p.end < c.start - 1.0:
                    break
            # junta palavras do início do bloco atual (até cobrir a sobreposição)
            cur_words: List[str] = []
            for s in segs:
                cur_words += _tokens(s.text)
                if len(cur_words) >= 40:
                    break
            cut = _overlap_cut(prev_words, cur_words)
            while cut > 0 and segs:
                w = _tokens(segs[0].text)
                if len(w) <= cut:
                    cut -= len(w)
                    segs.pop(0)
                else:
                    segs[0].text = " " + " ".join(w[cut:])
                    cut = 0
        out.extend(segs)
    if _is_unsorted(out):
        out.sort(key=lambda s: s.start)
    return out


def _is_unsorted(segs: List[Seg]) -> bool:
    return any(segs[i].start > segs[i + 1].start + 2.0 for i in range(len(segs) - 1))


def clean(segs: List[Seg], mark_uncertain: bool = True) -> List[Seg]:
    out: List[Seg] = []
    for s in segs:
        text = re.sub(r"\s+", " ", s.text).strip()
        if not text:
            continue
        low_conf = s.avg_logprob < UNCERTAIN_LOGPROB
        silence = s.no_speech_prob > 0.6
        if _HALLU_RE.search(text) and (low_conf or silence or len(_norm_words(text)) <= 6):
            continue  # frase-fantasma típica do Whisper
        text = collapse_repetitions(text)
        if mark_uncertain:
            if s.avg_logprob < INAUDIBLE_LOGPROB and silence:
                text = "[inaudível]"
            elif low_conf:
                text = f"{text} [trecho incerto]"
        out.append(Seg(s.start, s.end, text, s.avg_logprob, s.no_speech_prob, s.compression_ratio))
    # remove a mesma frase repetida em segmentos consecutivos (3+ vezes)
    final: List[Seg] = []
    for s in out:
        if len(final) >= 2 and _same(final[-1].text, s.text) and _same(final[-2].text, s.text):
            continue
        if final and final[-1].text == "[inaudível]" and s.text == "[inaudível]":
            final[-1].end = s.end
            continue
        final.append(s)
    return final


def _same(a: str, b: str) -> bool:
    return _norm_words(a) == _norm_words(b) and len(_norm_words(a)) > 0


def collapse_repetitions(text: str, max_rep: int = 2) -> str:
    """'a b c a b c a b c a b c' -> 'a b c a b c' (loops do modelo)."""
    words = text.split()
    if len(words) < 6:
        return text
    i = 0
    res: List[str] = []
    norm = ["".join(_norm_words(w)) for w in words]
    while i < len(words):
        collapsed = False
        for n in range(1, 16):
            if i + n * (max_rep + 1) > len(words):
                break
            unit = norm[i:i + n]
            if not any(unit):
                continue
            reps = 1
            while norm[i + reps * n: i + (reps + 1) * n] == unit:
                reps += 1
            if reps > max_rep and (n > 1 or reps > 4):
                res.extend(words[i:i + n * max_rep])
                i += n * reps
                collapsed = True
                break
        if not collapsed:
            res.append(words[i])
            i += 1
    return " ".join(res)


@dataclass
class Paragraph:
    start: float
    end: float
    text: str


def paragraphs(segs: List[Seg], pause: float = 2.0, max_chars: int = 900) -> List[Paragraph]:
    paras: List[Paragraph] = []
    cur: List[Seg] = []

    def flush():
        if cur:
            text = " ".join(s.text.strip() for s in cur)
            text = re.sub(r"\s+([,.;:!?])", r"\1", text)
            text = text[0].upper() + text[1:] if text and text[0].islower() else text
            paras.append(Paragraph(cur[0].start, cur[-1].end, text))

    for s in segs:
        if cur:
            gap = s.start - cur[-1].end
            cur_len = sum(len(x.text) for x in cur)
            ends_sentence = cur[-1].text.rstrip().endswith((".", "?", "!", "]"))
            if gap >= pause or (cur_len >= max_chars and ends_sentence) or cur_len >= max_chars * 2:
                flush()
                cur = []
        cur.append(s)
    flush()
    return paras


def word_count(segs: List[Seg]) -> int:
    return sum(len(s.text.split()) for s in segs)
