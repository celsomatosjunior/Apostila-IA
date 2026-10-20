"""Cruzamento transcrição × slides (busca semântica local + ordem dos materiais).

1. Similaridade TF-IDF (palavras, bigramas e n-gramas de caracteres — tolerante a
   erros de transcrição como "sítios"/"situs") entre cada janela da fala e o cartão
   de cada slide (texto impresso + texto lido pelo modelo de visão + descrição).
2. Programação dinâmica (Viterbi) escolhe um slide-âncora por janela, favorecendo
   avanço na ordem do material mas permitindo voltas (a professora retorna a slides)
   e trocas de PDF — não depende só da ordem das páginas.
3. Cada janela recebe os slides com evidência suficiente perto da âncora. Janelas sem
   evidência ficam sem slide (nenhuma associação forçada).
4. Slides não comentados oralmente ficam "posicionais": entram no capítulo onde
   estariam pela ordem, marcados como "só no slide", e aparecem no relatório.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .texto import TfIdf, cos

LIMIAR_ABS = 0.055
LIMIAR_ALTO = 0.12
Z_MIN = 1.6


@dataclass
class Associacao:
    janela: int
    slides: List[str] = field(default_factory=list)       # com evidência na fala
    ancora: Optional[str] = None
    score_ancora: float = 0.0
    confianca: str = "nenhuma"                            # alta | media | nenhuma


@dataclass
class Alinhamento:
    janelas: List[Associacao]
    slide_janela: Dict[str, int]                           # slide -> janela onde foi comentado
    slide_posicional: Dict[str, int]                       # slide -> janela por posição (não comentado)
    slide_score: Dict[str, float]
    decks_sem_fala: List[int] = field(default_factory=list)
    blocos: List[dict] = field(default_factory=list)       # [{janela, paragrafos, ancora, slides, score}]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(janelas=[Associacao(**a) for a in d["janelas"]], slide_janela=d["slide_janela"],
                   slide_posicional=d["slide_posicional"], slide_score=d["slide_score"],
                   decks_sem_fala=d.get("decks_sem_fala", []), blocos=d.get("blocos", []))


def alinhar_blocos(blocos: List[dict], n_janelas: int, slides: List[dict]) -> Alinhamento:
    """Alinhamento fino: blocos de ~300 tokens da fala (cada um pertence a uma janela).

    blocos: [{janela, paragrafos: [ids], texto}] na ordem da aula.
    """
    base = alinhar([b["texto"] for b in blocos], slides)
    jan: List[Associacao] = [Associacao(janela=i) for i in range(n_janelas)]
    slide_janela: Dict[str, int] = {}
    best_sc: Dict[str, float] = {}
    out_blocos = []
    for k, (b, a) in enumerate(zip(blocos, base.janelas)):
        J = jan[b["janela"]]
        for sid in a.slides:
            if sid not in J.slides:
                J.slides.append(sid)
        if a.ancora and a.score_ancora > J.score_ancora:
            J.ancora, J.score_ancora, J.confianca = a.ancora, a.score_ancora, a.confianca
        out_blocos.append({"janela": b["janela"], "paragrafos": b["paragrafos"], "ancora": a.ancora,
                           "slides": a.slides, "score": a.score_ancora})
    for sid, k in base.slide_janela.items():
        slide_janela[sid] = blocos[k]["janela"]
        best_sc[sid] = base.slide_score.get(sid, 0.0)
    pos = {sid: blocos[k]["janela"] for sid, k in base.slide_posicional.items()}
    return Alinhamento(jan, slide_janela, pos, best_sc, base.decks_sem_fala, out_blocos)


def blocos_da_fala(janelas, por_id: Dict[str, object], alvo_tokens: int = 300) -> List[dict]:
    out = []
    for j in janelas:
        cur, acc = [], 0
        for pid in j.paragrafos:
            p = por_id[pid]
            cur.append(pid)
            acc += p.tokens
            if acc >= alvo_tokens:
                out.append({"janela": j.i, "paragrafos": cur, "texto": " ".join(por_id[x].texto for x in cur)})
                cur, acc = [], 0
        if cur:
            if out and out[-1]["janela"] == j.i and acc < alvo_tokens * 0.4:
                out[-1]["paragrafos"] += cur
                out[-1]["texto"] += " " + " ".join(por_id[x].texto for x in cur)
            else:
                out.append({"janela": j.i, "paragrafos": cur, "texto": " ".join(por_id[x].texto for x in cur)})
    return out


def alinhar(textos_janelas: List[str], slides: List[dict]) -> Alinhamento:
    """slides: [{id, deck, num, texto}] na ordem global (PDF 1 p1..pn, PDF 2...). Duplicatas já removidas."""
    nw, ns = len(textos_janelas), len(slides)
    if nw == 0 or ns == 0:
        return Alinhamento([Associacao(janela=i) for i in range(nw)], {}, {}, {})
    tf = TfIdf([s["texto"] for s in slides] + textos_janelas)
    sv = tf.vecs[:ns]
    wv = tf.vecs[ns:]
    S = [[cos(wv[w], sv[s]) if slides[s]["texto"].strip() else 0.0 for s in range(ns)] for w in range(nw)]
    # z-score por janela (o quanto o slide se destaca dos demais)
    Z = []
    for row in S:
        mu = statistics.fmean(row)
        sd = statistics.pstdev(row) or 1e-6
        Z.append([(x - mu) / sd for x in row])

    # z-score só faz sentido com material suficiente; com poucos slides vale o limiar absoluto
    zmin = Z_MIN if ns >= 8 else -99.0

    # ---- Viterbi: estado = slide âncora (índice global) ou -1 (sem slide)
    NONE = ns
    def emis(w, s):
        if s == NONE:
            return LIMIAR_ABS * 0.9
        return S[w][s] if (S[w][s] >= LIMIAR_ABS and Z[w][s] >= zmin * 0.75) else -0.05

    def trans(a, b):
        if a == NONE or b == NONE:
            return -0.01
        if slides[a]["deck"] != slides[b]["deck"]:
            return -0.03 if slides[b]["deck"] > slides[a]["deck"] else -0.08
        d = b - a
        if 0 <= d <= 12:
            return 0.0
        if d > 12:
            return -0.02 - 0.0015 * (d - 12)
        return -0.03 - 0.002 * (-d)  # volta a slide anterior

    states = list(range(ns)) + [NONE]
    # poda: por janela, só os 25 melhores slides + NONE
    cand = []
    for w in range(nw):
        top = sorted(range(ns), key=lambda s: S[w][s], reverse=True)[:25]
        cand.append(top + [NONE])
    best = {s: emis(0, s) for s in cand[0]}
    back: List[Dict[int, int]] = [{}]
    for w in range(1, nw):
        nb, bk = {}, {}
        for s in cand[w]:
            e = emis(w, s)
            prev, val = max(((p, v + trans(p, s)) for p, v in best.items()), key=lambda x: x[1])
            nb[s] = val + e
            bk[s] = prev
        best, back = nb, back + [bk]
    s = max(best, key=best.get)
    path = [s]
    for w in range(nw - 1, 0, -1):
        s = back[w][s]
        path.append(s)
    path.reverse()

    assoc: List[Associacao] = []
    slide_janela: Dict[str, int] = {}
    slide_best: Dict[str, float] = {}
    for w, a in enumerate(path):
        A = Associacao(janela=w)
        if a != NONE:
            A.ancora = slides[a]["id"]
            A.score_ancora = round(S[w][a], 4)
            A.confianca = "alta" if S[w][a] >= LIMIAR_ALTO else "media"
            lim = max(LIMIAR_ABS, 0.55 * S[w][a])
            for s2 in range(ns):
                if slides[s2]["deck"] != slides[a]["deck"] or abs(s2 - a) > 15:
                    continue
                if S[w][s2] >= lim and Z[w][s2] >= zmin:
                    A.slides.append(slides[s2]["id"])
            if A.ancora not in A.slides:
                A.slides.insert(0, A.ancora)
            for sid in A.slides:
                sc = S[w][[x["id"] for x in slides].index(sid)]
                if sc > slide_best.get(sid, -1):
                    slide_best[sid] = sc
                    slide_janela[sid] = w
        assoc.append(A)
    # janela sem slide entre duas janelas com âncoras: não forçamos (fica sem slide)

    # ---- slides não comentados: posição pela ordem do material
    pos: Dict[str, int] = {}
    decks = sorted({s["deck"] for s in slides})
    sem_fala = []
    for d in decks:
        idx = [i for i, s in enumerate(slides) if s["deck"] == d]
        if not any(slides[i]["id"] in slide_janela for i in idx):
            sem_fala.append(d)
            continue
        last_w = None
        # primeira janela do deck = menor janela que comenta algum slide do deck
        first_w = min(slide_janela[slides[i]["id"]] for i in idx if slides[i]["id"] in slide_janela)
        for i in idx:
            sid = slides[i]["id"]
            if sid in slide_janela:
                last_w = slide_janela[sid]
            else:
                pos[sid] = last_w if last_w is not None else first_w
    return Alinhamento(assoc, slide_janela, pos, {k: round(v, 4) for k, v in slide_best.items()}, sem_fala)
