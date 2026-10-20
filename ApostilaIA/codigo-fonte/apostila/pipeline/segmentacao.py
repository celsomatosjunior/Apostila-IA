"""Segmentação semântica da transcrição em janelas (trechos) para o modelo.

Uma aula de 5 horas não cabe numa única chamada. Dividimos em janelas de ~1.800
tokens, cortando preferencialmente nas mudanças de assunto (mínimos locais de
similaridade TF-IDF entre blocos vizinhos de parágrafos) e nunca no meio de um
parágrafo. Cada janela leva o parágrafo final da janela anterior como contexto
(não extraído de novo — evita duplicação nas transições).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List

from ..fontes.transcricao import Paragrafo
from .texto import TfIdf, cos


@dataclass
class Janela:
    i: int
    paragrafos: List[str]            # ids
    contexto: List[str] = field(default_factory=list)  # ids do contexto anterior
    tokens: int = 0
    parte: int = 1

    def to_dict(self):
        return asdict(self)


def fronteiras(paras: List[Paragrafo], k: int = 3) -> List[float]:
    """score[i] = similaridade entre os k parágrafos antes e depois da posição i (baixa = mudança de tema)."""
    n = len(paras)
    if n < 2:
        return [1.0] * n
    tf = TfIdf([p.texto for p in paras], chars=False)
    score = [1.0] * n
    for i in range(1, n):
        a = " ".join(p.texto for p in paras[max(0, i - k):i])
        b = " ".join(p.texto for p in paras[i:i + k])
        score[i] = cos(tf.vec(a), tf.vec(b))
    return score


def segmentar(paras: List[Paragrafo], alvo_tokens: int = 1800, min_frac: float = 0.6,
              max_frac: float = 1.35) -> List[Janela]:
    if not paras:
        return []
    score = fronteiras(paras)
    janelas: List[Janela] = []
    i = 0
    n = len(paras)
    while i < n:
        acc = 0
        j = i
        best_cut, best_score = None, 9.0
        while j < n:
            acc += paras[j].tokens
            j += 1
            if j < n and paras[j].parte != paras[j - 1].parte and acc >= alvo_tokens * 0.35:
                best_cut = j  # troca de arquivo (parte) é uma fronteira natural
                break
            if acc >= alvo_tokens * min_frac and j < n:
                s = score[j]
                if s < best_score:
                    best_score, best_cut = s, j
            if acc >= alvo_tokens * max_frac:
                break
        cut = best_cut if (best_cut and j < n) else j
        if cut <= i:
            cut = i + 1
        # evita janela final minúscula: junta à anterior
        resto = sum(p.tokens for p in paras[cut:])
        if 0 < resto < alvo_tokens * 0.3 and paras[-1].parte == paras[cut - 1].parte:
            cut = n
        ids = [p.id for p in paras[i:cut]]
        ctx = [paras[i - 1].id] if i > 0 else []
        janelas.append(Janela(i=len(janelas), paragrafos=ids, contexto=ctx,
                              tokens=sum(p.tokens for p in paras[i:cut]), parte=paras[i].parte))
        i = cut
    return janelas
