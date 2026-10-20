"""Auditoria de fidelidade e revisão global (determinística + verificação pelo modelo).

As 10 verificações exigidas:
 1. assuntos principais preservados   — temas das janelas cobertos por algum capítulo
 2. exemplos importantes              — notas "exemplo" refletidas no texto
 3. observações clínicas              — notas observacao/dica/atencao refletidas; as essenciais
                                        ausentes são reinseridas como quadro (texto já fiel)
 4. sem informações externas          — cobertura lexical frase × fontes + números sem fonte;
                                        suspeitas vão ao modelo; "sem suporte" é removida
 5. slides associados corretamente    — figuras só de slides do próprio capítulo
 6. sem parágrafos duplicados         — similaridade de shingles entre blocos
 7. português                         — vícios de oralidade, palavras repetidas, frases longas
 8. tabelas e figuras legíveis        — colunas, células, figura existe
 9. esquemas fiéis                    — etapas sustentadas pelas fontes
10. objetividade                      — extensão × perfil
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable, Dict, List, Optional

from .. import logs
from ..fontes.transcricao import rotulo_paragrafo
from ..util import content_words, words
from . import numeros
from .prompts import QUADROS
from .texto import cobertura, frases, jaccard, limpar_oralidade, shingles, vocab

log = logs.get("auditoria")

ROTULO_QUADRO = {"observacao": "OBSERVAÇÃO DA PROFESSORA", "dica": "DICA CLÍNICA", "atencao": "PONTO DE ATENÇÃO",
                 "exemplo": "EXEMPLO DISCUTIDO", "passo_a_passo": "PASSO A PASSO"}
NOTA_QUADRO = {"observacao": "observacao", "dica_clinica": "dica", "atencao": "atencao", "exemplo": "exemplo",
               "passo_a_passo": "passo_a_passo"}
_ORAL = re.compile(r"\b(né|tá\?|tipo assim|então assim|aí você|aí a gente|beleza\?|okay)\b", re.I)
_ID_P = re.compile(r"^P\d+\.\d+$")
_ID_S = re.compile(r"^A\d+-p\d+$")


def _clean_ids(xs) -> List[str]:
    out = []
    for x in xs or []:
        x = str(x).strip().strip("[]<>")
        if (_ID_P.match(x) or _ID_S.match(x)) and x not in out:
            out.append(x)
    return out


def _txt(s) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    s = re.sub(r"\b(\w+)( \1\b)+", r"\1", s, flags=re.I)
    return s


def normalizar_secoes(secoes: list, slides_validos: set, paras_validos: set, cards: dict,
                      titulo_cap: str, esquemas: bool) -> List[dict]:
    """Valida a saída do modelo: tipos, campos, figuras só de slides do capítulo, ids de fonte."""
    out = []
    for s in secoes or []:
        tit = _txt(s.get("titulo"))
        blocos = []
        for b in s.get("blocos") or []:
            t = b.get("tipo")
            fontes = [f for f in _clean_ids(b.get("fontes")) if f in paras_validos or f in slides_validos]
            texto = _txt(b.get("texto"))
            itens = [_txt(i) for i in (b.get("itens") or []) if _txt(i)]
            nb = {"tipo": t, "fontes": fontes}
            if t == "paragrafo":
                if not texto:
                    continue
                nb["texto"] = texto
            elif t == "topicos":
                if not itens:
                    if texto:
                        nb = {"tipo": "paragrafo", "texto": texto, "fontes": fontes}
                    else:
                        continue
                else:
                    nb["itens"] = itens
                    if texto:
                        nb["texto"] = texto
            elif t == "tabela":
                cab = [_txt(c) for c in (b.get("cabecalho") or [])][:6]
                linhas = [[_txt(c) for c in r][:6] for r in (b.get("linhas") or []) if any(_txt(c) for c in r)]
                if not linhas:
                    continue
                ncol = max([len(cab)] + [len(r) for r in linhas])
                if ncol < 2:
                    nb = {"tipo": "topicos", "itens": [r[0] for r in linhas if r], "fontes": fontes}
                else:
                    cab = (cab + [""] * ncol)[:ncol]
                    linhas = [(r + [""] * ncol)[:ncol] for r in linhas]
                    nb.update(cabecalho=cab, linhas=linhas, texto=texto)
            elif t == "quadro":
                sub = b.get("subtipo")
                if sub not in QUADROS:
                    if not texto:
                        continue
                    nb = {"tipo": "paragrafo", "texto": texto, "fontes": fontes}
                else:
                    if not texto and not itens:
                        continue
                    nb.update(subtipo=sub, texto=texto, itens=itens)
            elif t == "figura":
                sid = str(b.get("slide") or "").strip("<> ")
                if sid not in slides_validos or sid not in cards:
                    continue
                nb.update(slide=sid, texto=texto or cards[sid].get("titulo", ""))
                if sid not in nb["fontes"]:
                    nb["fontes"].append(sid)
            elif t == "esquema":
                if not esquemas or len(itens) < 2:
                    if itens:
                        nb = {"tipo": "topicos", "itens": itens, "fontes": fontes}
                    else:
                        continue
                else:
                    sub = b.get("subtipo") if b.get("subtipo") in ("sequencia", "comparacao") else "sequencia"
                    nb.update(subtipo=sub, itens=itens[:10], texto=texto)
            else:
                if texto:
                    nb = {"tipo": "paragrafo", "texto": texto, "fontes": fontes}
                else:
                    continue
            blocos.append(nb)
        if not blocos:
            continue
        if out and tit and tit.lower() == out[-1]["titulo"].lower():
            out[-1]["blocos"] += blocos
            continue
        if tit.lower() == titulo_cap.lower() and not out:
            tit = ""
        out.append({"titulo": tit, "blocos": blocos})
    # figuras repetidas no capítulo
    vistos = set()
    for s in out:
        nb = []
        for b in s["blocos"]:
            if b["tipo"] == "figura":
                if b["slide"] in vistos:
                    continue
                vistos.add(b["slide"])
            nb.append(b)
        s["blocos"] = nb
    return out


def _textos_bloco(b: dict) -> List[str]:
    out = []
    if b.get("texto"):
        out.append(b["texto"])
    out += b.get("itens", []) or []
    for r in b.get("linhas", []) or []:
        out += r
    return out


class Auditoria:
    def __init__(self, trans, janelas, notas, aln, cards, term, fontes_txt: Dict[str, str], decks,
                 perfil: str, remover: bool = True, incluir_figuras: bool = True):
        self.trans = trans
        self.janelas = janelas
        self.notas = notas
        self.aln = aln
        self.cards = cards
        self.term = term
        self.fontes_txt = fontes_txt
        self.decks = decks
        self.perfil = perfil
        self.remover = remover
        self.incluir_figuras = incluir_figuras
        self.n_partes = len(trans.partes)
        self.removidas: List[dict] = []
        self.parciais: List[dict] = []
        self.duplicados: List[dict] = []
        self.reinseridas: List[dict] = []
        self.num_sem_fonte: List[dict] = []
        self.esquemas_removidos: List[dict] = []
        self.correcoes_pt = Counter()
        self.figuras_auto: List[str] = []
        all_slides = [c["titulo"] + " " + c["texto"] + " " + c.get("descricao", "") + " " +
                      " ".join(" ".join(r) for t in c.get("tabelas", []) for r in [t.get("cabecalho", [])] + t["linhas"])
                      for c in cards.values()]
        self.vals_fontes = numeros.todos_valores(list(fontes_txt.values()) + all_slides)

    # ------------------------------------------------------------ fontes de um capítulo
    def _fontes_cap(self, cap) -> List[str]:
        ids = [i for j in self.janelas if j.i in cap.get("janelas", []) for i in j.paragrafos]
        out = [self.fontes_txt[i] for i in ids if i in self.fontes_txt]
        for s in cap.get("slides", []):
            c = self.cards.get(s)
            if c:
                out.append(c["titulo"] + " " + c["texto"] + " " + c.get("descricao", ""))
                for t in c.get("tabelas", []):
                    out.append(" ".join(t.get("cabecalho", [])) + " " + " ".join(" ".join(r) for r in t["linhas"]))
        for j in self.janelas:
            if j.i in cap.get("janelas", []):
                for it in self.notas.get(j.i, {}).get("itens", []):
                    out.append(it.get("texto", ""))
        return out

    def _trecho_fontes(self, frase: str, cap, k: int = 3) -> str:
        """Trechos mais parecidos com a frase (para a verificação pelo modelo)."""
        cw = set(content_words(frase))
        cands = []
        for j in self.janelas:
            if j.i not in cap.get("janelas", []):
                continue
            for i in j.paragrafos:
                t = self.fontes_txt.get(i, "")
                cands.append((len(cw & set(content_words(t))), f"[{i}] {t[:700]}"))
        for s in cap.get("slides", []):
            c = self.cards.get(s)
            if c:
                t = c["titulo"] + ": " + c["texto"].replace("\n", "; ") + " " + c.get("descricao", "")
                cands.append((len(cw & set(content_words(t))), f"<{s}> {t[:700]}"))
        cands.sort(key=lambda x: -x[0])
        return "\n".join(t for _, t in cands[:k])

    # ------------------------------------------------------------ revisão
    def revisar_capitulos(self, caps: List[dict], verificar: Optional[Callable[[List[dict]], List[dict]]] = None) -> List[dict]:
        # (6) duplicados entre todos os blocos (mantém a primeira ocorrência)
        vistos: List[tuple] = []
        for cap in caps:
            for sec in cap["secoes"]:
                nb = []
                for b in sec["blocos"]:
                    if b["tipo"] in ("paragrafo", "quadro", "topicos"):
                        sh = shingles(" ".join(_textos_bloco(b)))
                        dup = next((v for v in vistos if jaccard(sh, v[0]) >= 0.72), None) if len(sh) >= 6 else None
                        if dup:
                            self.duplicados.append({"capitulo": cap["num"], "texto": " ".join(_textos_bloco(b))[:220],
                                                    "igual_a_capitulo": dup[1]})
                            continue
                        vistos.append((sh, cap["num"]))
                    nb.append(b)
                sec["blocos"] = nb
            cap["secoes"] = [s for s in cap["secoes"] if s["blocos"]]

        # (7) português: limpeza de oralidade residual e repetições
        for cap in caps:
            for sec in cap["secoes"]:
                for b in sec["blocos"]:
                    if b.get("texto"):
                        b["texto"] = self._pt(b["texto"])
                    if b.get("itens"):
                        b["itens"] = [self._pt(i) for i in b["itens"]]

        # (4) informação externa: cobertura lexical e números
        suspeitas = []
        for cap in caps:
            fv = vocab(self._fontes_cap(cap))
            for si, sec in enumerate(cap["secoes"]):
                for bi, b in enumerate(sec["blocos"]):
                    if b["tipo"] not in ("paragrafo", "quadro", "topicos"):
                        continue
                    pecas = frases(b["texto"]) if b.get("texto") else []
                    for fr in pecas + list(b.get("itens") or []):
                        cov = cobertura(fr, fv)
                        sem = numeros.numeros_sem_fonte(fr, self.vals_fontes)
                        if sem:
                            self.num_sem_fonte.append({"capitulo": cap["num"], "frase": fr[:300], "numeros": sem})
                        if (cov < 0.62 and len(content_words(fr)) >= 4) or sem:
                            suspeitas.append({"cap": cap, "si": si, "bi": bi, "frase": fr, "cobertura": round(cov, 2),
                                              "numeros": sem})
        if suspeitas and verificar is not None:
            itens = [{"id": k, "frase": s["frase"], "fontes": self._trecho_fontes(s["frase"], s["cap"])}
                     for k, s in enumerate(suspeitas)]
            res = {int(r.get("id", -1)): r for r in verificar(itens) or []}
            for k, s in enumerate(suspeitas):
                r = res.get(k)
                if not r:
                    continue
                reg = {"capitulo": s["cap"]["num"], "frase": s["frase"][:400], "comentario": r.get("comentario", "")[:300],
                       "cobertura": s["cobertura"]}
                if r.get("veredito") == "sem_suporte":
                    self.removidas.append(reg)
                    if self.remover:
                        self._remover_frase(s["cap"]["secoes"][s["si"]]["blocos"][s["bi"]], s["frase"])
                elif r.get("veredito") == "parcial":
                    self.parciais.append(reg)
        elif suspeitas:
            for s in suspeitas:
                self.parciais.append({"capitulo": s["cap"]["num"], "frase": s["frase"][:400],
                                      "comentario": "cobertura baixa (não verificada pelo modelo)", "cobertura": s["cobertura"]})
        for cap in caps:
            for sec in cap["secoes"]:
                sec["blocos"] = [b for b in sec["blocos"] if b.get("texto") or b.get("itens") or b["tipo"] in ("figura", "tabela")]

        # (9) esquemas: cada etapa precisa de sustentação
        for cap in caps:
            fv = vocab(self._fontes_cap(cap))
            for sec in cap["secoes"]:
                nb = []
                for b in sec["blocos"]:
                    if b["tipo"] == "esquema":
                        ruins = [i for i in b["itens"] if cobertura(i, fv) < 0.5]
                        if ruins:
                            self.esquemas_removidos.append({"capitulo": cap["num"], "etapas": b["itens"], "sem_suporte": ruins})
                            continue
                    nb.append(b)
                sec["blocos"] = nb

        # (3) observações/dicas/alertas essenciais ausentes -> reinserir (texto das notas, já fiel)
        if self.perfil != "compacta":
            for cap in caps:
                texto_cap = " ".join(t for sec in cap["secoes"] for b in sec["blocos"] for t in _textos_bloco(b))
                sh_cap = vocab([texto_cap])
                cit = {f for sec in cap["secoes"] for b in sec["blocos"] for f in b.get("fontes", [])}
                extra = []
                for j in self.janelas:
                    if j.i not in cap.get("janelas", []):
                        continue
                    for it in self.notas.get(j.i, {}).get("itens", []):
                        q = NOTA_QUADRO.get(it.get("tipo"))
                        if not q or int(it.get("importancia", 1)) < 3:
                            continue
                        cov = cobertura(it.get("texto", ""), sh_cap)
                        if cov >= 0.7 or (set(it.get("paragrafos", [])) & cit and cov >= 0.5):
                            continue
                        b = {"tipo": "quadro", "subtipo": q, "texto": self._pt(it["texto"]), "itens": [],
                             "fontes": list(it.get("paragrafos", []))}
                        if q == "passo_a_passo" and " | " in it["texto"]:
                            b["itens"] = [x.strip() for x in it["texto"].split(" | ") if x.strip()]
                            b["texto"] = ""
                        extra.append(b)
                        self.reinseridas.append({"capitulo": cap["num"], "tipo": ROTULO_QUADRO[q], "texto": it["texto"][:300]})
                if extra and cap["secoes"]:
                    cap["secoes"][-1]["blocos"] += extra[:6]

        # (5/8) figuras: ao menos as visuais mais bem associadas, se o capítulo ficou sem nenhuma
        if self.incluir_figuras:
            lim = {"compacta": 1, "equilibrada": 2, "fiel": 3}[self.perfil]
            for cap in caps:
                tem = any(b["tipo"] == "figura" for sec in cap["secoes"] for b in sec["blocos"])
                if tem or not cap["secoes"]:
                    continue
                cand = [(self.aln.slide_score.get(s, 0), s) for s in cap.get("slides", [])
                        if self.cards.get(s, {}).get("visual") and s in self.aln.slide_janela]
                cand = [c for c in sorted(cand, reverse=True) if c[0] >= 0.09][:lim]
                for _, s in sorted(cand, key=lambda x: (self.cards[x[1]]["deck"], self.cards[x[1]]["num"])):
                    sec = self._secao_mais_proxima(cap, s)
                    leg = self.cards[s].get("titulo") or ""
                    sec["blocos"].append({"tipo": "figura", "slide": s, "texto": leg, "fontes": [s], "auto": True})
                    self.figuras_auto.append(s)
        # numeração: capítulos 1..n
        for k, cap in enumerate(caps, 1):
            cap["num"] = k
        return caps

    def _secao_mais_proxima(self, cap, sid):
        c = self.cards[sid]
        alvo = set(content_words(c["titulo"] + " " + c["texto"]))
        best, bs = cap["secoes"][-1], -1
        for sec in cap["secoes"]:
            t = set(content_words(sec["titulo"] + " " + " ".join(t for b in sec["blocos"] for t in _textos_bloco(b))))
            sc = len(alvo & t)
            if sc > bs:
                best, bs = sec, sc
        return best

    def _pt(self, s: str) -> str:
        n0 = s
        s = _ORAL.sub("", s)
        s = re.sub(r"\b(\w{2,})( \1\b)+", r"\1", s, flags=re.I)
        s = re.sub(r"\s+([,.;:!?])", r"\1", s)
        s = re.sub(r"([.!?]){2,}", r"\1", s)
        s = re.sub(r",\s*,", ",", s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        if s != n0:
            self.correcoes_pt["ajustes automáticos de redação"] += 1
        return s

    @staticmethod
    def _remover_frase(b: dict, frase: str):
        if b.get("itens") and frase in b["itens"]:
            b["itens"] = [i for i in b["itens"] if i != frase]
        if b.get("texto") and frase in b["texto"]:
            b["texto"] = re.sub(r"\s{2,}", " ", b["texto"].replace(frase, "")).strip()

    # ------------------------------------------------------------ apêndices
    def referencias(self) -> List[str]:
        out = []
        for dk in self.decks:
            for r in dk.referencias:
                if r not in out:
                    out.append(r)
        for c in sorted(self.cards.values(), key=lambda c: (c["deck"], c["num"])):
            for r in c.get("referencias", []):
                r = r.strip()
                if r and r not in out and not any(r[:40] in o or o[:40] in r for o in out):
                    out.append(r)
        return out

    def pontos_conferir(self) -> List[dict]:
        out = []
        for c in self.term.a_conferir:
            out.append({"tipo": "termo", "texto": f"“{c.de}” na transcrição — nos slides: “{c.para}” ({c.motivo})."})
        seen = set()
        for j in self.janelas:
            for t in self.notas.get(j.i, {}).get("termos_duvidosos", []):
                k = (t.get("termo", "").lower())
                if not k or k in seen:
                    continue
                seen.add(k)
                sug = f" (possível: “{t['sugestao']}”)" if t.get("sugestao") and t["sugestao"].lower() != k else ""
                out.append({"tipo": "termo", "texto": f"“{t['termo']}”{sug} — {t.get('motivo', '')} "
                                                       f"[{rotulo_paragrafo(t.get('paragrafo', ''), self.n_partes)}]"})
        for d in self._divergencias():
            out.append({"tipo": "divergencia", "texto": f"{d['assunto']}: na fala “{d['fala']}”, no slide "
                                                         f"“{d['slide']}” ({d['onde']})."})
        return out[:40]

    def _divergencias(self) -> List[dict]:
        if hasattr(self, "_div"):
            return self._div
        nums_f = []
        for i, t in self.fontes_txt.items():
            nums_f += numeros.extrair(t, i)
        nums_s = []
        for c in self.cards.values():
            if c.get("duplicata_de"):
                continue
            txt = c["texto"] + "\n" + "\n".join(" ".join(r) for t in c.get("tabelas", []) for r in t["linhas"])
            nums_s += numeros.extrair(txt, c["id"])
        prox: Dict[str, set] = {}
        for sid, w in list(self.aln.slide_janela.items()) + list(self.aln.slide_posicional.items()):
            ws = {w, w - 1, w + 1}
            prox.setdefault(sid, set()).update(i for j in self.janelas if j.i in ws for i in j.paragrafos)
        out = []
        for d in numeros.divergencias(nums_f, nums_s, prox):
            c = self.cards.get(d.fonte_slide, {})
            dk = next((x for x in self.decks if x.idx == c.get("deck")), None)
            out.append({"assunto": d.assunto, "fala": d.fala, "slide": d.slide,
                        "onde": f"{', '.join(rotulo_paragrafo(x, self.n_partes) for x in d.fonte_fala.split(','))}; "
                                f"{(dk.rotulo if dk else '')} slide {c.get('num', '?')}",
                        "trecho_fala": d.trecho_fala, "trecho_slide": d.trecho_slide})
        self._div = out
        return out

    # ------------------------------------------------------------ relatório
    def relatorio(self, apost: dict) -> dict:
        caps = apost["capitulos"]
        texto_total = " ".join(t for c in caps for s in c["secoes"] for b in s["blocos"] for t in _textos_bloco(b))
        palavras = len(words(texto_total))
        pal_fala = self.trans.palavras
        voc_ap = vocab([texto_total])
        # (1) temas
        temas = []
        for j in self.janelas:
            n = self.notas.get(j.i, {})
            tema = n.get("tema", "")
            itens = [it for it in n.get("itens", []) if int(it.get("importancia", 1)) >= 2]
            cov = (sum(cobertura(it.get("texto", ""), voc_ap) for it in itens) / len(itens)) if itens else 1.0
            temas.append({"janela": j.i, "tema": tema, "cobertura": round(cov, 2),
                          "paragrafos": f"{rotulo_paragrafo(j.paragrafos[0], self.n_partes)} a "
                                        f"{rotulo_paragrafo(j.paragrafos[-1], self.n_partes)}"})
        # (2/3) omissões
        omissoes = []
        for j in self.janelas:
            for it in self.notas.get(j.i, {}).get("itens", []):
                if int(it.get("importancia", 1)) < 2:
                    continue
                cov = cobertura(it.get("texto", ""), voc_ap)
                if cov < 0.6:
                    omissoes.append({"tipo": it.get("tipo"), "texto": it.get("texto", "")[:300],
                                     "onde": ", ".join(rotulo_paragrafo(p, self.n_partes) for p in it.get("paragrafos", [])[:3]),
                                     "cobertura": round(cov, 2)})
        ex = [it for j in self.janelas for it in self.notas.get(j.i, {}).get("itens", []) if it.get("tipo") == "exemplo"]
        obs = [it for j in self.janelas for it in self.notas.get(j.i, {}).get("itens", [])
               if it.get("tipo") in ("observacao", "dica_clinica", "atencao")]
        ex_ok = sum(1 for it in ex if cobertura(it.get("texto", ""), voc_ap) >= 0.6)
        obs_ok = sum(1 for it in obs if cobertura(it.get("texto", ""), voc_ap) >= 0.6)
        # (5) slides
        usados = {b["slide"] for c in caps for s in c["secoes"] for b in s["blocos"] if b["tipo"] == "figura"}
        citados = {f for c in caps for s in c["secoes"] for b in s["blocos"] for f in b.get("fontes", []) if f.startswith("A")}
        slides_rel = []
        for c in sorted(self.cards.values(), key=lambda c: (c["deck"], c["num"])):
            if c.get("duplicata_de") or c.get("pagina_tipo") == "capa":
                continue
            sid = c["id"]
            w = self.aln.slide_janela.get(sid)
            cap = next((k["num"] for k in caps if w is not None and w in k.get("janelas", [])), None)
            if cap is None:
                pw = self.aln.slide_posicional.get(sid)
                cap = next((k["num"] for k in caps if pw is not None and pw in k.get("janelas", [])), None)
            slides_rel.append({"slide": sid, "titulo": c["titulo"][:80], "capitulo": cap,
                               "associacao": "fala" if w is not None else ("posição" if sid in self.aln.slide_posicional else "nenhuma"),
                               "score": self.aln.slide_score.get(sid, 0), "figura": sid in usados,
                               "citado": sid in citados, "visao": bool(c.get("visao"))})
        sem_assoc = [s for s in slides_rel if s["associacao"] == "nenhuma"]
        # (8) tabelas/figuras
        tabelas = [b for c in caps for s in c["secoes"] for b in s["blocos"] if b["tipo"] == "tabela"]
        tab_largas = sum(1 for b in tabelas if len(b["cabecalho"]) > 5)
        figs = [b for c in caps for s in c["secoes"] for b in s["blocos"] if b["tipo"] == "figura"]
        # (7) português
        oral = len(_ORAL.findall(texto_total))
        longas = sum(1 for f in frases(texto_total) if len(f.split()) > 55)
        # (10) extensão
        alvo = int(pal_fala * {"compacta": 0.17, "equilibrada": 0.30, "fiel": 0.46}[self.perfil])
        div = self._divergencias()
        janelas_sem = [a.janela for a in self.aln.janelas if a.confianca == "nenhuma"]
        quadros = Counter(ROTULO_QUADRO.get(b.get("subtipo"), "") for c in caps for s in c["secoes"]
                          for b in s["blocos"] if b["tipo"] == "quadro")
        checks = [
            {"n": 1, "item": "Principais assuntos da aula preservados",
             "resultado": f"{sum(1 for t in temas if t['cobertura'] >= 0.6)}/{len(temas)} trechos com cobertura ≥ 60%",
             "ok": all(t["cobertura"] >= 0.5 for t in temas)},
            {"n": 2, "item": "Exemplos importantes presentes", "resultado": f"{ex_ok}/{len(ex)} exemplos identificados na apostila",
             "ok": ex_ok >= 0.8 * len(ex) if ex else True},
            {"n": 3, "item": "Observações clínicas incluídas",
             "resultado": f"{obs_ok}/{len(obs)} observações/dicas/alertas; {len(self.reinseridas)} reinseridas pela auditoria",
             "ok": obs_ok >= 0.8 * len(obs) if obs else True},
            {"n": 4, "item": "Sem informações externas",
             "resultado": f"{len(self.removidas)} frase(s) sem suporte removida(s); {len(self.parciais)} parcial(is) para conferência; "
                          f"{len(self.num_sem_fonte)} número(s) sem fonte", "ok": not self.parciais and not self.num_sem_fonte},
            {"n": 5, "item": "Slides corretamente associados",
             "resultado": f"{sum(1 for s in slides_rel if s['associacao'] == 'fala')} slides associados à fala, "
                          f"{sum(1 for s in slides_rel if s['associacao'] == 'posição')} por posição, {len(sem_assoc)} sem associação; "
                          f"{len(janelas_sem)} trecho(s) da fala sem slide correspondente (não forçado)", "ok": True},
            {"n": 6, "item": "Sem parágrafos duplicados", "resultado": f"{len(self.duplicados)} duplicata(s) removida(s)", "ok": True},
            {"n": 7, "item": "Português", "resultado": f"{oral} marca(s) de oralidade restante(s); {longas} frase(s) muito longa(s)",
             "ok": oral == 0 and longas <= 3},
            {"n": 8, "item": "Tabelas e figuras legíveis",
             "resultado": f"{len(tabelas)} tabela(s) ({tab_largas} com 6 colunas), {len(figs)} figura(s) em 160 dpi", "ok": True},
            {"n": 9, "item": "Esquemas fiéis às fontes",
             "resultado": f"{sum(1 for c in caps for s in c['secoes'] for b in s['blocos'] if b['tipo'] == 'esquema')} esquema(s); "
                          f"{len(self.esquemas_removidos)} descartado(s) por falta de sustentação", "ok": True},
            {"n": 10, "item": "Objetiva e agradável para estudo",
             "resultado": f"{palavras} palavras (referência do perfil: ~{alvo}; fala: {pal_fala} palavras)",
             "ok": 0.5 * alvo <= palavras <= 1.6 * alvo if alvo else True},
        ]
        avisos = []
        if any(not c.get("visao") and c.get("pagina_tipo") in ("imagem", "misto") for c in self.cards.values()):
            n = sum(1 for c in self.cards.values() if not c.get("visao") and c.get("pagina_tipo") in ("imagem", "misto"))
            avisos.append(f"{n} slide(s) com conteúdo em imagem não foram lidos pelo modelo de visão.")
        if self.aln.decks_sem_fala:
            avisos.append("Material(is) de slides sem correspondência na fala: " +
                          ", ".join(dk.rotulo for dk in self.decks if dk.idx in self.aln.decks_sem_fala))
        return {
            "checagens": checks,
            "removidas": self.removidas, "parciais": self.parciais, "duplicados": self.duplicados[:40],
            "reinseridas": self.reinseridas, "numeros_sem_fonte": self.num_sem_fonte,
            "esquemas_removidos": self.esquemas_removidos, "omissoes": omissoes[:120],
            "divergencias": div, "termos_corrigidos": [c.__dict__ for c in self.term.correcoes],
            "termos_conferir": [c.__dict__ for c in self.term.a_conferir],
            "termos_duvidosos_modelo": [t for j in self.janelas for t in self.notas.get(j.i, {}).get("termos_duvidosos", [])],
            "slides": slides_rel, "temas": temas, "janelas_sem_slide": janelas_sem,
            "figuras_automaticas": self.figuras_auto,
            "quadros": dict(quadros), "palavras_apostila": palavras, "palavras_fala": pal_fala, "alvo_palavras": alvo,
            "mapa": [{"capitulo": c["num"], "titulo": c["titulo"],
                      "fala": (f"{rotulo_paragrafo(self._pids(c)[0], self.n_partes)} a "
                               f"{rotulo_paragrafo(self._pids(c)[-1], self.n_partes)}") if self._pids(c) else "",
                      "slides": self._rotulo_slides(c.get("slides", []))} for c in caps],
            "avisos": avisos,
        }

    def _pids(self, cap) -> List[str]:
        return [i for j in self.janelas if j.i in cap.get("janelas", []) for i in j.paragrafos]

    def _rotulo_slides(self, sids: List[str]) -> str:
        por = {}
        for s in sids:
            m = re.match(r"A(\d+)-p(\d+)", s)
            if m:
                por.setdefault(int(m.group(1)), []).append(int(m.group(2)))
        partes = []
        for d, ps in sorted(por.items()):
            dk = next((x for x in self.decks if x.idx == d), None)
            partes.append(f"{dk.rotulo if dk else 'PDF ' + str(d)}: " + _faixas(sorted(set(ps))))
        return "; ".join(partes)


def _faixas(ns: List[int]) -> str:
    out = []
    i = 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append(f"{ns[i]}" if i == j else f"{ns[i]}–{ns[j]}")
        i = j + 1
    return "slides " + ", ".join(out)
