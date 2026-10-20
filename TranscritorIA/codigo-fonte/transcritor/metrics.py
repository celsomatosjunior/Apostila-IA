"""Métricas de qualidade: taxa de erro de palavras (WER)."""
from __future__ import annotations

import re
import unicodedata
from typing import List


def normalize(text: str) -> List[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"\[[^\]]*\]", " ", t)  # remove marcações [trecho incerto]
    return re.findall(r"[a-z0-9]+", t)


def wer(reference: str, hypothesis: str) -> float:
    r, h = normalize(reference), normalize(hypothesis)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(h)] / len(r)
