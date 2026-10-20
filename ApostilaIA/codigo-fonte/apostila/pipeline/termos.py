"""Terminologia: correções de transcrição SUSTENTADAS pelos slides.

O reconhecimento de fala erra termos técnicos ("sítios solitus" em vez de "situs
solitus", "RASC" em vez de "Rashkind"). Só propomos correção quando a forma
correta aparece impressa nos slides, com uma de duas evidências:

  (a) contexto: a palavra vizinha coincide — "sítios solitus" × "situs solitus";
  (b) grafia muito próxima de um termo raro do slide que não existe na fala.

Correções (a) são aplicadas ao texto enviado ao modelo e registradas no relatório.
Casos (b) e qualquer dúvida sem confirmação ficam como "termos a conferir" —
nunca inventamos correções.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Tuple

from ..util import STOP, norm_word, strip_accents, words
from .texto import similar_ratio

# palavras comuns do português que nunca devem ser "corrigidas" para termos parecidos
_COMUNS = set(norm_word(w) for w in """
sitio sitios situacao posicao lado lados direito direita esquerdo esquerda normal anormal veia veias
arteria arterias cava cavas aorta coracao fetal feto fetos atrio atrios ventriculo ventriculos
conexao conexoes valva valvas imagem imagens corte cortes vista estudo caso casos exemplo
""".split())


# formas verbais comuns ("voltando", "chamado") não são termos técnicos
_VERBAL = re.compile(r"(ando|endo|indo|ado|ados|ada|adas|ido|idos|ida|idas|ava|avam|iam|aram|eram|iram|ar|er|ir|mente)$")


_FLEXAO = re.compile(r"(mente|avam|aram|eram|iram|coes|cao|oes|ava|ais|al|icas|icos|ica|ico|ias|ia|as|os|es|am|em|ou|a|o|e|s|m)$")


def _radical(w: str) -> str:
    return _FLEXAO.sub("", w)


def _flexao(a: str, b: str) -> bool:
    """Mesma palavra em outra forma (plural, gênero, verbo): não é erro de transcrição."""
    if a.startswith(b) or b.startswith(a):
        return True
    ra, rb = _radical(a), _radical(b)
    return len(ra) >= 4 and ra == rb


@dataclass
class Correcao:
    de: str
    para: str
    motivo: str
    ocorrencias: int = 0
    automatica: bool = True


@dataclass
class Terminologia:
    correcoes: List[Correcao] = field(default_factory=list)
    a_conferir: List[Correcao] = field(default_factory=list)
    lexico: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls([Correcao(**c) for c in d["correcoes"]], [Correcao(**c) for c in d["a_conferir"]],
                   d.get("lexico", []))

    def aplicar(self, texto: str) -> str:
        for c in self.correcoes:
            if c.automatica:
                texto = _sub_preserving(texto, c.de, c.para)
        return texto


def _sub_preserving(texto: str, de: str, para: str) -> str:
    pat = re.compile(r"(?<![\wÀ-ÿ])" + re.escape(de) + r"(?![\wÀ-ÿ])", re.I)

    def rep(m):
        s = m.group(0)
        if s.isupper() and len(s) > 1:
            return para.upper()
        if s[0].isupper():
            return para[0].upper() + para[1:]
        return para
    return pat.sub(rep, texto)


def _tokens(texto: str) -> List[str]:
    return words(texto)


def construir(transcricao_textos: List[str], slide_textos: List[str]) -> Terminologia:
    slide_tok = [_tokens(t) for t in slide_textos]
    trans_tok = [_tokens(t) for t in transcricao_textos]
    slide_vocab = Counter(norm_word(w) for ts in slide_tok for w in ts)
    trans_vocab = Counter(norm_word(w) for ts in trans_tok for w in ts)
    formas: Dict[str, Counter] = defaultdict(Counter)
    for t in slide_textos:
        for line in t.splitlines():
            for j, w in enumerate(words(line)):
                formas[norm_word(w)][(w, j == 0)] += 1
    forma_slide: Dict[str, str] = {k: _forma_preferida(v) for k, v in formas.items()}
    # bigramas do slide: (termo, vizinho) e (vizinho, termo)
    sb_next: Dict[str, set] = defaultdict(set)
    sb_prev: Dict[str, set] = defaultdict(set)
    for ts in slide_tok:
        n = [norm_word(w) for w in ts]
        for a, b in zip(n, n[1:]):
            sb_next[a].add(b)
            sb_prev[b].add(a)
    termos_slide = [k for k in slide_vocab if len(k) >= 5 and k not in STOP]

    cand: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    for ts in trans_tok:
        n = [norm_word(w) for w in ts]
        for i, w in enumerate(n):
            if len(w) < 4 or w in slide_vocab or w in STOP:
                continue
            viz_next = n[i + 1] if i + 1 < len(n) else None
            viz_prev = n[i - 1] if i > 0 else None
            if viz_next in STOP and viz_prev in STOP:
                continue
            alvos = set()
            if viz_next and viz_next not in STOP:
                alvos |= sb_prev.get(viz_next, set())
            if viz_prev and viz_prev not in STOP:
                alvos |= sb_next.get(viz_prev, set())
            for t in alvos:
                if len(t) < 5 or t in STOP or abs(len(t) - len(w)) > 3 or t[0] != w[0]:
                    continue
                # o termo correto do slide (quase) nunca aparece na fala: o reconhecimento erra sempre do mesmo jeito
                if trans_vocab.get(t, 0) > 0.25 * trans_vocab[w] or _flexao(w, t):
                    continue
                if similar_ratio(w, t) >= 0.72:
                    cand[(w, t)]["ctx"] += 1
    term = Terminologia()
    usados = set()
    for (w, t), c in sorted(cand.items(), key=lambda kv: -kv[1]["ctx"]):
        if w in usados:
            continue
        orig = _forma_mais_comum(trans_tok, w)
        alvo = forma_slide.get(t, t)
        if c["ctx"] < 2 and similar_ratio(w, t) < 0.85:
            term.a_conferir.append(Correcao(orig, alvo, "uma única ocorrência em contexto do slide", c["ctx"], False))
            usados.add(w)
            continue
        # palavra comum do português só é corrigida quando quase sempre aparece no contexto do termo
        total_w = trans_vocab[w]
        if w in _COMUNS and c["ctx"] < 0.7 * total_w:
            term.a_conferir.append(Correcao(orig, alvo, "palavra comum; confirmar contexto", c["ctx"], False))
            usados.add(w)
            continue
        term.correcoes.append(Correcao(orig, alvo, f"forma impressa nos slides (\"{alvo}\")", total_w, True))
        usados.add(w)
    # (b) grafia próxima sem evidência de contexto -> a conferir
    por_letra: Dict[str, List[str]] = defaultdict(list)
    for t in termos_slide:
        if len(t) >= 6 and not trans_vocab.get(t):
            por_letra[t[0]].append(t)
    for w, n in trans_vocab.items():
        if w in usados or w in slide_vocab or len(w) < 6 or w in STOP or w in _COMUNS or _VERBAL.search(w):
            continue
        for t in por_letra.get(w[0], ()):
            if abs(len(t) - len(w)) <= 2 and not _flexao(w, t) and similar_ratio(w, t) >= 0.84:
                term.a_conferir.append(Correcao(_forma_mais_comum(trans_tok, w), forma_slide.get(t, t),
                                                "grafia semelhante a termo do slide", n, False))
                usados.add(w)
                break
    term.lexico = sorted({forma_slide[k] for k in termos_slide if slide_vocab[k] >= 1})[:600]
    return term


def _forma_mais_comum(trans_tok: List[List[str]], key: str) -> str:
    c = Counter(w for ts in trans_tok for w in ts if norm_word(w) == key)
    if not c:
        return key
    best = c.most_common(1)[0][0]
    return best.lower() if not best.isupper() else best


def siglas_slide(slide_textos: List[str]) -> List[str]:
    out = Counter()
    for t in slide_textos:
        for w in words(t):
            if 2 <= len(w) <= 8 and w.isupper() and not w.isdigit():
                out[w] += 1
    return [w for w, _ in out.most_common(200)]


def nome_professor_correcoes(professores: List[str], transcricao_textos: List[str]) -> List[Correcao]:
    """'Dra. Cátia' na fala × 'Katia Souza' no slide: só vale para o nome da professora."""
    out = []
    corpus = " ".join(transcricao_textos)
    for nome in professores:
        if not nome:
            continue
        primeiro = nome.split()[0]
        for m in set(re.findall(r"\b[A-ZÁ-Ú][a-zá-ú]{3,}\b", corpus)):
            if m != primeiro and strip_accents(m.lower())[1:] == strip_accents(primeiro.lower())[1:] \
                    and similar_ratio(m, primeiro) >= 0.75:
                out.append(Correcao(m, primeiro, f"nome da professora nos slides: {nome}", corpus.count(m), False))
    return out


_VOG = set("aeiouáéíóúâêôãõà")


def _forma_preferida(c: Counter) -> str:
    """Escolhe a grafia de um termo do slide: minúscula > nome próprio > sigla."""
    formas = [w for (w, _), _n in c.most_common()]
    low = [w for w in formas if w.islower()]
    if low:
        return low[0]
    meio = [w for (w, first), _n in c.most_common() if w[:1].isupper() and not w.isupper() and not first]
    if meio:
        return meio[0]  # nome próprio (maiúscula no meio da linha), ex.: Rashkind
    tit = [w for w in formas if w[:1].isupper() and not w.isupper()]
    up = formas[0]
    vog = sum(ch.lower() in _VOG for ch in up) / max(1, len(up))
    if tit:
        return tit[0].lower() if vog >= 0.3 else tit[0]
    if len(up) >= 5 and vog >= 0.3:
        return up.lower()
    return up
