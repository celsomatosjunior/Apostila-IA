"""Orquestrador: executa todas as etapas com checkpoints, pausa, cancelamento e progresso.

Etapas
  1. Leitura das fontes (TXT + PDFs, renderização das páginas)
  2. Leitura visual dos slides (modelo de visão; uma página por vez, com checkpoint)
  3. Segmentação semântica da transcrição
  4. Cruzamento fala × slides
  5. Terminologia (correções sustentadas pelos slides) e números
  6. Representação intermediária: notas fiéis de cada trecho (modelo de texto)
  7. Planejamento dos capítulos
  8. Redação capítulo a capítulo (checkpoint por capítulo)
  9. Auditoria de fidelidade e revisão global
 10. Composição do PDF e do DOCX + relatório de fidelidade
"""
from __future__ import annotations

import math
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .. import __version__, logs
from ..fontes import slides as slides_mod
from ..fontes.slides import Deck
from ..fontes.transcricao import Transcricao, ler_transcricoes, rotulo_paragrafo
from ..llm.cliente import ContextoExcedido, Controle, LLMBase, LLMCancelado, LLMErro, LLMInterrompido
from ..util import content_words, est_tokens
from . import alinhamento as al
from . import auditoria, numeros, prompts, termos
from .projeto import Projeto
from .segmentacao import Janela, segmentar

log = logs.get("pipeline")

RAZAO_PERFIL = {"compacta": 0.17, "equilibrada": 0.30, "fiel": 0.46}
FIGURAS_PERFIL = {"compacta": 2, "equilibrada": 4, "fiel": 6}
VISUAIS = {"ultrassonografia", "esquema_anatomico", "diagrama", "foto", "grafico", "misto"}


class Cancelado(Exception):
    pass


class Provedor:
    """Fornece o modelo para cada papel (texto/visão). Implementado por Motor e pelo simulador."""

    def obter(self, papel: str, cancel=None) -> LLMBase:
        raise NotImplementedError

    def reiniciar(self, papel: str, cancel=None) -> LLMBase:
        return self.obter(papel, cancel)

    def liberar(self) -> None:
        pass

    def descricao(self) -> str:
        return "—"


@dataclass
class Resultado:
    pdf: Optional[Path] = None
    docx: Optional[Path] = None
    relatorio: Optional[Path] = None
    relatorio_json: Optional[Path] = None
    paginas: int = 0
    palavras: int = 0
    duracao_s: float = 0.0
    avisos: List[str] = field(default_factory=list)


class Gerador:
    def __init__(self, txts: List[Path], pdfs: List[Path], destino: Path, settings, provedor: Provedor,
                 on_progress: Optional[Callable[[dict], None]] = None, controle: Optional[Controle] = None,
                 base_dir: Optional[Path] = None, modelos_key: str = "", hw=None):
        self.txts = [Path(p) for p in txts]
        self.pdfs = slides_mod.ordenar_pdfs(pdfs)
        self.destino = Path(destino)
        self.st = settings
        self.prov = provedor
        self.cb = on_progress or (lambda d: None)
        self.ctl = controle or Controle()
        self.hw = hw
        opcoes = {"visao": settings.usar_visao, "fig": settings.incluir_figuras, "esq": settings.incluir_esquemas,
                  "conf": settings.incluir_pontos_conferir, "rm": settings.remover_sem_suporte,
                  "fontes": settings.mostrar_fontes_na_apostila, "tit": settings.titulo_manual}
        self.proj = Projeto(self.txts, self.pdfs, settings.perfil, modelos_key, opcoes, base_dir)
        self.t0 = time.monotonic()
        self.unid_total = 1.0
        self.unid_feitas = 0.0
        self.etapa = ""
        self.detalhe = ""
        self._rate_t = None
        self._rate_u = 0.0
        self.avisos: List[str] = []
        self.aceleracoes: List[str] = []
        self.modelos_usados: List[str] = []

    # ================================================================ progresso
    def _emit(self, detalhe: str = ""):
        if detalhe:
            self.detalhe = detalhe
        frac = min(0.999, self.unid_feitas / max(1e-6, self.unid_total))
        eta = None
        if self._rate_t is not None and self.unid_feitas - self._rate_u > 0.5:
            dt = time.monotonic() - self._rate_t
            rate = (self.unid_feitas - self._rate_u) / max(1e-6, dt)
            if rate > 0:
                eta = (self.unid_total - self.unid_feitas) / rate
        self.cb({"etapa": self.etapa, "detalhe": self.detalhe, "frac": frac,
                 "gpu": self.prov.descricao(), "decorrido_s": time.monotonic() - self.t0,
                 "eta_s": max(0.0, eta) if eta is not None else None})

    def _avanca(self, u: float, detalhe: str = ""):
        self.unid_feitas += u
        self._emit(detalhe)

    def _set_etapa(self, nome: str):
        self.etapa = nome
        log.info("Etapa: %s", nome)
        self._emit("")

    def _check(self):
        if self.ctl.cancel.is_set():
            raise Cancelado()
        if self.ctl.pause.is_set():
            self.cb({"pausado": True, "etapa": self.etapa, "detalhe": "Pausado"})
            while self.ctl.pause.is_set():
                if self.ctl.cancel.is_set():
                    raise Cancelado()
                time.sleep(0.3)
            self._rate_t = time.monotonic()
            self._rate_u = self.unid_feitas
            self.cb({"pausado": False, "etapa": self.etapa, "detalhe": self.detalhe})

    def _llm_call(self, papel: str, fn: Callable[[LLMBase], object]):
        """Executa uma chamada ao modelo tratando pausa (refaz a chamada), cancelamento e falhas do servidor."""
        falhas = 0
        while True:
            self._check()
            llm = self.prov.obter(papel, self.ctl.cancel)
            desc = self.prov.descricao()
            if desc not in self.aceleracoes:
                self.aceleracoes.append(desc)
            if llm.nome not in self.modelos_usados:
                self.modelos_usados.append(llm.nome)
            if self._rate_t is None:
                self._rate_t, self._rate_u = time.monotonic(), self.unid_feitas
            try:
                return fn(llm)
            except LLMInterrompido:
                continue  # pausa: _check espera; depois refaz a chamada
            except LLMCancelado:
                raise Cancelado()
            except ContextoExcedido:
                raise
            except LLMErro as e:
                falhas += 1
                log.warning("Falha na chamada ao modelo (%s): %s", papel, e)
                if falhas > 2:
                    raise
                if "indisponível" in str(e) or "servidor" in str(e):
                    self._emit("Reiniciando o modelo após falha…")
                    self.prov.reiniciar(papel, self.ctl.cancel)

    # ================================================================ execução
    def executar(self) -> Resultado:
        try:
            return self._executar()
        finally:
            self.prov.liberar()

    def _executar(self) -> Resultado:
        self._set_etapa("Lendo transcrição e PDFs")
        trans, decks = self._ingestao()
        n_vis = sum(1 for d in decks for p in d.paginas if not p.duplicata_de)
        n_win_est = max(1, math.ceil(sum(p.tokens for p in trans.paragrafos) / 1800))
        n_cap_est = max(2, round(n_win_est / 4))
        self.unid_total = 2 + n_vis * 1.0 + n_win_est * 3.0 + 2 + n_cap_est * 8.0 + 3 + 2
        self.unid_feitas = 2

        cards = self._cartoes(decks)
        self._set_etapa("Organizando a transcrição")
        janelas = self._segmentar(trans)
        aln = self._alinhar(trans, janelas, cards)
        term = self._termos(trans, cards, decks)
        notas = self._notas(trans, janelas, aln, cards, term)
        plano = self._plano(trans, janelas, notas, aln, cards, decks)
        caps = self._capitulos(trans, janelas, notas, aln, cards, term, plano, decks)
        apost, rev = self._revisao(trans, janelas, notas, aln, cards, term, plano, caps, decks)
        return self._render(apost, rev, trans, decks)

    # ---------------------------------------------------------------- 1. ingestão
    def _ingestao(self):
        d = self.proj.load("fontes.json")
        if d:
            trans = Transcricao.from_dict(d["transcricao"])
            decks = [Deck.from_dict(x) for x in d["decks"]]
            if all((self.proj.ck("render") / p.render).exists() for dk in decks for p in dk.paginas if p.render):
                return trans, decks
        trans = ler_transcricoes(self.txts)
        if not trans.paragrafos:
            raise ValueError("A transcrição está vazia: nenhum parágrafo encontrado nos arquivos TXT.")
        decks = []
        rdir = self.proj.sub("render")
        for i, pdf in enumerate(self.pdfs, 1):
            self._check()
            self._emit(f"Lendo {pdf.name}")
            decks.append(slides_mod.ler_pdf(pdf, i, rdir))
        self.proj.save("fontes.json", {"transcricao": trans.to_dict(), "decks": [dk.to_dict() for dk in decks]})
        return trans, decks

    # ---------------------------------------------------------------- 2. visão
    def _cartoes(self, decks: List[Deck]) -> Dict[str, dict]:
        self._set_etapa("Lendo os slides (texto e imagens)")
        cards: Dict[str, dict] = {}
        usar_visao = bool(self.st.usar_visao)
        rdir = self.proj.ck("render")
        total = sum(1 for d in decks for p in d.paginas if not p.duplicata_de)
        feitos = 0
        for dk in decks:
            for p in dk.paginas:
                if p.duplicata_de:
                    continue
                self._check()
                name = f"cartoes/{p.id}.json"
                card = self.proj.load(name)
                if card is None or (usar_visao and not card.get("visao") and p.precisa_visao and not card.get("visao_falhou")):
                    card = self._cartao(p, dk, rdir, usar_visao)
                    self.proj.save(name, card)
                cards[p.id] = card
                feitos += 1
                self._avanca(1.0, f"Slide {feitos}/{total} — {dk.rotulo[:40]} p. {p.num}")
        for dk in decks:
            for p in dk.paginas:
                if p.duplicata_de and p.duplicata_de in cards:
                    c = dict(cards[p.duplicata_de])
                    c.update(id=p.id, num=p.num, duplicata_de=p.duplicata_de)
                    cards[p.id] = c
        # professor(a)/curso a partir da leitura visual da capa, se a camada de texto não tinha
        for dk in decks:
            capa = cards.get(dk.paginas[0].id) if dk.paginas else None
            if capa and not dk.professor:
                m = re.search(r"prof(?:essor|essora|\.)?\s*(?:dr\.?|dra\.?)?\s*:?\s*\n?\s*([A-ZÁ-Ú][\wÀ-ÿ]+(?:\s+[A-ZÁ-Ú][\wÀ-ÿ]+){0,3})",
                              capa.get("texto", ""), re.I)
                if m:
                    dk.professor = slides_mod._title_case(m.group(1).strip())
        return cards

    def _cartao(self, p, dk: Deck, rdir: Path, usar_visao: bool) -> dict:
        base = {"id": p.id, "deck": p.deck, "num": p.num, "pagina_tipo": p.tipo, "titulo": p.titulo,
                "texto": p.texto, "descricao": "", "tipo_visual": "texto" if p.tipo == "texto" else "outro",
                "tabelas": [{"cabecalho": t.cabecalho, "linhas": t.linhas} for t in p.tabelas],
                "referencias": list(p.referencias), "visao": False, "render": p.render}
        if usar_visao and p.precisa_visao and p.render:
            try:
                r = self._llm_call("visao", lambda llm: llm.visao(
                    "cartao", prompts.SISTEMA_VISAO, prompts.prompt_cartao(p.texto), rdir / p.render,
                    prompts.SCHEMA_CARTAO, 900, ctx={"pagina": p.__dict__}, controle=self.ctl))
                base["visao"] = True
                vis_txt = (r.get("texto_visivel") or "").strip()
                linhas = [ln for ln in base["texto"].splitlines() if ln.strip()]
                for ln in vis_txt.splitlines():
                    if ln.strip() and ln.strip() not in linhas:
                        linhas.append(ln.strip())
                base["texto"] = "\n".join(linhas)
                base["titulo"] = base["titulo"] or (r.get("titulo") or "").strip()
                base["descricao"] = (r.get("descricao") or "").strip()
                base["tipo_visual"] = r.get("tipo_visual") or base["tipo_visual"]
                for t in r.get("tabelas") or []:
                    if t.get("linhas"):
                        base["tabelas"].append({"cabecalho": t.get("cabecalho") or [], "linhas": t["linhas"]})
                for ref in r.get("referencias") or []:
                    if ref and ref not in base["referencias"] and len(ref) > 12:
                        base["referencias"].append(ref)
            except Cancelado:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("Leitura visual falhou em %s: %s", p.id, e)
                base["visao_falhou"] = str(e)[:200]
        base["visual"] = (base["tipo_visual"] in VISUAIS) or (p.tipo in ("imagem", "misto") and p.area_imagens >= 0.25)
        return base

    # ---------------------------------------------------------------- 3/4. segmentação e alinhamento
    def _segmentar(self, trans: Transcricao) -> List[Janela]:
        d = self.proj.load("janelas.json")
        if d:
            return [Janela(**j) for j in d]
        js = segmentar(trans.paragrafos)
        self.proj.save("janelas.json", [j.to_dict() for j in js])
        return js

    def _texto_janela(self, trans: Transcricao, j: Janela) -> str:
        pid = trans.por_id()
        return " ".join(pid[i].texto for i in j.paragrafos)

    def _alinhar(self, trans, janelas, cards) -> al.Alinhamento:
        d = self.proj.load("alinhamento.json")
        if d:
            return al.Alinhamento.from_dict(d)
        self._emit("Cruzando a fala com os slides")
        sl = [{"id": c["id"], "deck": c["deck"], "num": c["num"],
               "texto": (c["titulo"] + " ") * 2 + c["texto"] + " " + c.get("descricao", "")}
              for c in sorted(cards.values(), key=lambda c: (c["deck"], c["num"]))
              if not c.get("duplicata_de") and c.get("pagina_tipo") != "capa"]
        blocos = al.blocos_da_fala(janelas, trans.por_id())
        a = al.alinhar_blocos(blocos, len(janelas), sl)
        self.proj.save("alinhamento.json", a.to_dict())
        return a

    # ---------------------------------------------------------------- 5. terminologia
    def _termos(self, trans, cards, decks) -> termos.Terminologia:
        d = self.proj.load("termos.json")
        if d:
            return termos.Terminologia.from_dict(d)
        t = termos.construir([p.texto for p in trans.paragrafos],
                             [c["titulo"] + "\n" + c["texto"] for c in cards.values() if not c.get("duplicata_de")])
        t.a_conferir += termos.nome_professor_correcoes([dk.professor for dk in decks], [p.texto for p in trans.paragrafos])
        self.proj.save("termos.json", t.to_dict())
        return t

    @staticmethod
    def _correcoes_prompt(term: termos.Terminologia) -> List[dict]:
        out = [{"de": c.de, "para": c.para, "motivo": "aplicada (slides)"} for c in term.correcoes]
        out += [{"de": c.de, "para": c.para, "motivo": "possível; confirme pelo contexto"} for c in term.a_conferir[:20]]
        return out

    # ---------------------------------------------------------------- 6. notas
    def _notas(self, trans, janelas, aln, cards, term) -> Dict[int, dict]:
        self._set_etapa("Extraindo o conteúdo da aula (representação intermediária)")
        pid = trans.por_id()
        out: Dict[int, dict] = {}
        anterior = ""
        cor = self._correcoes_prompt(term)
        for j in janelas:
            name = f"notas/j{j.i:04d}.json"
            n = self.proj.load(name)
            if n is None:
                paras = [(i, term.aplicar(pid[i].texto)) for i in j.paragrafos]
                ctx_txt = anterior or " ".join(pid[i].texto for i in j.contexto)[-600:]
                sl = []
                for sid in aln.janelas[j.i].slides[:6] if j.i < len(aln.janelas) else []:
                    c = cards.get(sid)
                    if c:
                        sl.append({"id": sid, "titulo": c["titulo"], "texto": c["texto"].replace("\n", "; ")})
                n = self._notas_janela(j.i, paras, ctx_txt, sl, cor)
                valid = set(j.paragrafos)
                for it in n.get("itens", []):
                    it["paragrafos"] = [x for x in it.get("paragrafos", []) if x in valid] or j.paragrafos[:1]
                n["slides_relacionados"] = [s for s in n.get("slides_relacionados", []) if s in cards]
                self.proj.save(name, n)
            out[j.i] = n
            anterior = f"Tema anterior: {n.get('tema', '')}. {n.get('resumo', '')}"
            self._avanca(3.0, f"Trecho {j.i + 1}/{len(janelas)}: {n.get('tema', '')[:50]}")
        return out

    def _contingencia(self, tarefa: str, ctx: dict, erro: Exception) -> dict:
        """Falha persistente do modelo num trecho: conteúdo extraído diretamente da fonte (fiel, menos
        elaborado) para não perder horas de trabalho. Registrado nos avisos do relatório."""
        from ..llm.simulador import Simulador
        log.error("Modelo falhou em %s (%s); usando extração direta da fonte neste trecho", tarefa, erro)
        aviso = f"Um trecho ({tarefa}) foi montado por extração direta da transcrição, pois o modelo falhou: {str(erro)[:120]}"
        if aviso not in self.avisos:
            self.avisos.append(aviso)
        return getattr(Simulador(), "_" + tarefa)(ctx)

    def _notas_janela(self, ji, paras, ctx_txt, sl, cor) -> dict:
        ctx = {"paragrafos": paras, "slides": sl, "correcoes": cor}
        try:
            return self._llm_call("texto", lambda llm: llm.json(
                "notas", prompts.SISTEMA, prompts.prompt_notas(paras, ctx_txt, sl, cor), prompts.SCHEMA_NOTAS,
                max_tokens=min(3500, 400 + int(sum(est_tokens(t) for _, t in paras) * 1.1)), temperatura=0.2,
                ctx=ctx, controle=self.ctl))
        except Cancelado:
            raise
        except ContextoExcedido:
            return self._notas_dividir(ji, paras, ctx_txt, sl, cor)
        except LLMErro as e:
            return self._contingencia("notas", ctx, e)

    def _notas_dividir(self, ji, paras, ctx_txt, sl, cor) -> dict:
        if True:  # trecho maior que o contexto: divide ao meio
            if len(paras) <= 1:
                return self._contingencia("notas", {"paragrafos": paras, "slides": sl, "correcoes": cor},
                                          LLMErro("trecho maior que o contexto do modelo"))
            h = len(paras) // 2
            a = self._notas_janela(ji, paras[:h], ctx_txt, sl, cor)
            b = self._notas_janela(ji, paras[h:], f"Tema anterior: {a.get('tema', '')}", sl, cor)
            return {"tema": a.get("tema", ""), "resumo": (a.get("resumo", "") + " " + b.get("resumo", "")).strip(),
                    "itens": a.get("itens", []) + b.get("itens", []),
                    "termos_duvidosos": a.get("termos_duvidosos", []) + b.get("termos_duvidosos", []),
                    "slides_relacionados": a.get("slides_relacionados", []) + b.get("slides_relacionados", [])}

    # ---------------------------------------------------------------- 7. plano
    def _plano(self, trans, janelas, notas, aln, cards, decks) -> dict:
        d = self.proj.load("plano.json")
        if d:
            self._avanca(2)
            return d
        self._set_etapa("Planejando os capítulos")
        total_tok = sum(j.tokens for j in janelas)
        n_est = max(1, min(16, round(total_tok / 7000)))
        n_min, n_max = max(1, n_est - 2), min(24, n_est + 3)
        if len(janelas) <= 1:
            n_min = n_max = 1
        jl = []
        deck_rot = {dk.idx: dk.rotulo for dk in decks}
        for j in janelas:
            a = aln.janelas[j.i] if j.i < len(aln.janelas) else None
            deck = deck_rot.get(cards[a.ancora]["deck"], "") if (a and a.ancora in cards) else "—"
            sl = "; ".join(cards[s]["titulo"][:50] for s in (a.slides[:3] if a else []) if s in cards and cards[s]["titulo"])
            jl.append({"i": j.i, "deck": deck[:40], "tema": notas[j.i].get("tema", ""),
                       "resumo": notas[j.i].get("resumo", "")[:240], "slides": sl})
        ds = []
        for dk in decks:
            estr = [c["titulo"] for c in (cards.get(p.id) for p in dk.paginas)
                    if c and c.get("pagina_tipo") in ("divisoria", "texto") and c["titulo"]][:25]
            ds.append({"rotulo": dk.rotulo, "estrutura": "; ".join(dict.fromkeys(estr))})
        plano = None
        try:
            plano = self._llm_call("texto", lambda llm: llm.json(
                "plano", prompts.SISTEMA, prompts.prompt_plano(jl, ds, n_min, n_max), prompts.SCHEMA_PLANO,
                max_tokens=2500, temperatura=0.2, ctx={"janelas": jl, "decks": ds, "n_min": n_min, "n_max": n_max},
                controle=self.ctl))
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Plano pelo modelo falhou (%s); usando plano automático", e)
        plano = self._validar_plano(plano, janelas, jl, aln, cards)
        if self.st.titulo_manual:
            plano["titulo_apostila"] = self.st.titulo_manual
        self.proj.save("plano.json", plano)
        self._avanca(2)
        return plano

    def _validar_plano(self, plano, janelas, jl, aln, cards) -> dict:
        n = len(janelas)
        caps = []
        if plano and plano.get("capitulos"):
            seen = set()
            for c in sorted(plano["capitulos"], key=lambda c: int(c.get("inicio", 0))):
                ini = max(0, min(n - 1, int(c.get("inicio", 0))))
                if ini in seen or not str(c.get("titulo", "")).strip():
                    continue
                seen.add(ini)
                caps.append({"titulo": c["titulo"].strip(), "inicio": ini,
                             "secoes": [s for s in c.get("secoes", []) if s.strip()][:10]})
            if caps:
                caps[0]["inicio"] = 0
        if not caps:  # plano automático: troca de material e mudanças de tema
            ini = 0
            acc = 0
            last_deck = None
            for j in janelas:
                a = aln.janelas[j.i] if j.i < len(aln.janelas) else None
                deck = cards[a.ancora]["deck"] if (a and a.ancora in cards) else last_deck
                novo = (j.i == 0) or (deck is not None and last_deck is not None and deck != last_deck) or acc >= 7000
                if novo:
                    tit = jl[j.i]["tema"] or (cards[a.ancora]["titulo"] if (a and a.ancora in cards) else f"Parte {len(caps) + 1}")
                    caps.append({"titulo": tit[:90].strip().capitalize() if tit.isupper() else tit[:90].strip(),
                                 "inicio": j.i, "secoes": []})
                    acc = 0
                acc += j.tokens
                last_deck = deck if deck is not None else last_deck
        # capítulos grandes demais (aulas longas): divide em capítulos de ~9 mil tokens de fala
        caps = self._dividir_grandes(caps, janelas, jl)
        titulo = (plano or {}).get("titulo_apostila", "").strip() if plano else ""
        return {"titulo_apostila": titulo, "capitulos": caps}

    @staticmethod
    def _dividir_grandes(caps, janelas, jl, limite: int = 12000, alvo: int = 9000):
        out = []
        n = len(janelas)
        for k, c in enumerate(caps):
            ini = c["inicio"]
            fim = caps[k + 1]["inicio"] if k + 1 < len(caps) else n
            tok = sum(j.tokens for j in janelas[ini:fim])
            if tok <= limite or fim - ini < 2:
                out.append(c)
                continue
            partes = min(fim - ini, math.ceil(tok / alvo))
            alvo_p = tok / partes
            inicios, acc = [ini], 0
            for j in janelas[ini:fim]:
                if acc >= alvo_p * len(inicios) and j.i not in inicios and len(inicios) < partes:
                    inicios.append(j.i)
                acc += j.tokens
            for q, i0 in enumerate(inicios):
                if q == 0:
                    out.append(dict(c))
                else:
                    tema = (jl[i0]["tema"] or "").strip()
                    tit = tema[:1].upper() + tema[1:] if tema else f"{c['titulo']} (continuação)"
                    out.append({"titulo": tit[:90], "inicio": i0, "secoes": []})
        return out

    # ---------------------------------------------------------------- 8. capítulos
    def _capitulos(self, trans, janelas, notas, aln, cards, term, plano, decks) -> List[dict]:
        self._set_etapa("Redigindo os capítulos")
        caps_plan = plano["capitulos"]
        n_cap = len(caps_plan)
        # reajusta a estimativa de progresso com o número real de capítulos
        self.unid_total += (n_cap - max(2, round(len(janelas) / 4))) * 8.0
        pid = trans.por_id()
        cor = self._correcoes_prompt(term)
        prof = ", ".join(dict.fromkeys(dk.professor for dk in decks if dk.professor))
        out = []
        ja = []
        for k, cp in enumerate(caps_plan):
            ini = cp["inicio"]
            fim = caps_plan[k + 1]["inicio"] if k + 1 < n_cap else len(janelas)
            js = janelas[ini:fim]
            name = f"capitulos/c{k + 1:02d}.json"
            cap = self.proj.load(name)
            if cap is None:
                cap = self._redigir(k + 1, cp, js, notas, aln, cards, pid, term, cor, ja, prof)
                self.proj.save(name, cap)
            out.append(cap)
            ja += [cp["titulo"]] + [s["titulo"] for s in cap["secoes"]]
            self._avanca(8.0, f"Capítulo {k + 1}/{n_cap}: {cp['titulo'][:50]}")
        return out

    def _slides_capitulo(self, js: List[Janela], aln, cards) -> List[dict]:
        ids = set(j.i for j in js)
        out = {}
        for j in js:
            if j.i < len(aln.janelas):
                for s in aln.janelas[j.i].slides:
                    if s in cards:
                        out[s] = False
        for s, w in aln.slide_posicional.items():
            if w in ids and s in cards and s not in out:
                c = cards[s]
                if c.get("pagina_tipo") in ("capa",) or c.get("duplicata_de"):
                    continue
                if not (c["texto"].strip() or c.get("descricao")):
                    continue
                out[s] = True
        res = []
        for s, so in sorted(out.items(), key=lambda kv: (cards[kv[0]]["deck"], cards[kv[0]]["num"])):
            c = cards[s]
            if c.get("pagina_tipo") == "capa":
                continue
            tab = ""
            if c.get("tabelas"):
                t = c["tabelas"][0]
                tab = " / ".join([" | ".join(t.get("cabecalho", []))] + [" | ".join(r) for r in t["linhas"][:12]])
            res.append({"id": s, "titulo": c["titulo"], "texto": c["texto"].replace("\n", "; "),
                        "descricao": c.get("descricao", ""), "tipo_visual": c.get("tipo_visual", ""),
                        "visual": bool(c.get("visual")), "so_slide": so, "tabela": tab})
        return res

    def _paras_marcados(self, js, aln, cards, pid, term) -> List[tuple]:
        """Transcrição do capítulo com marcas de qual slide estava sendo comentado em cada trecho."""
        inicio = {}
        for b in aln.blocos:
            if b.get("ancora") and b["paragrafos"]:
                inicio[b["paragrafos"][0]] = b["slides"] or [b["ancora"]]
        out = []
        ultimo = None
        for j in js:
            for i in j.paragrafos:
                sl = inicio.get(i)
                if sl and sl != ultimo:
                    tit = "; ".join(f"<{s}> {cards[s]['titulo'][:60]}" for s in sl[:3] if s in cards)
                    out.append(("#", f"(slides exibidos neste trecho: {tit})"))
                    ultimo = sl
                out.append((i, term.aplicar(pid[i].texto)))
        return out

    def _redigir(self, num, cp, js, notas, aln, cards, pid, term, cor, ja, prof, parte="") -> dict:
        paras_m = self._paras_marcados(js, aln, cards, pid, term)
        paras = [(i, t) for i, t in paras_m if i != "#"]
        ns = [it for j in js for it in notas[j.i].get("itens", [])]
        sl = self._slides_capitulo(js, aln, cards)[:36]
        palavras = sum(len(t.split()) for _, t in paras)
        alvo = int(palavras * RAZAO_PERFIL[self.st.perfil]) + 25 * sum(1 for s in sl if s["so_slide"])
        alvo = max(150, alvo)
        max_fig = FIGURAS_PERFIL[self.st.perfil] + (2 if len(js) > 4 else 0) if self.st.incluir_figuras else 0
        max_tok = min(9000, int(alvo * 1.45 * 1.7) + 900)
        prompt = prompts.prompt_capitulo(num, cp["titulo"], cp.get("secoes", []), ns, paras_m, sl, cor,
                                         self.st.perfil, alvo, ja, max_fig, prof, parte)
        if not self.st.incluir_esquemas:
            prompt += "\n- Não crie blocos do tipo esquema."
        ctx_cap = {"num": num, "titulo": cp["titulo"], "secoes": cp.get("secoes", []), "notas": ns,
                   "paragrafos": paras, "slides": sl, "max_figuras": max_fig, "perfil": self.st.perfil,
                   "esquemas": self.st.incluir_esquemas}
        r, erro_cap = None, None
        try:
            r = self._llm_call("texto", lambda llm: llm.json(
                "capitulo", prompts.SISTEMA, prompt, prompts.SCHEMA_CAPITULO, max_tokens=max_tok, temperatura=0.25,
                ctx=ctx_cap, controle=self.ctl))
        except Cancelado:
            raise
        except LLMErro as e:
            if isinstance(e, ContextoExcedido):
                r = None
            else:
                erro_cap = e
        if r is None and erro_cap is None:
            if len(js) <= 1:
              try:
                # última opção: só as notas (já fiéis), sem a transcrição bruta
                r = self._llm_call("texto", lambda llm: llm.json(
                    "capitulo", prompts.SISTEMA,
                    prompts.prompt_capitulo(num, cp["titulo"], cp.get("secoes", []), ns, [], sl[:20], cor,
                                            self.st.perfil, alvo, ja, max_fig, prof, parte),
                    prompts.SCHEMA_CAPITULO, max_tokens=max_tok, temperatura=0.25,
                    ctx={"num": num, "titulo": cp["titulo"], "secoes": cp.get("secoes", []), "notas": ns,
                         "paragrafos": paras, "slides": sl, "max_figuras": max_fig, "perfil": self.st.perfil,
                         "esquemas": self.st.incluir_esquemas}, controle=self.ctl))
              except Cancelado:
                raise
              except LLMErro as e:
                erro_cap = e
                r = None
            else:
                h = len(js) // 2
                a = self._redigir(num, cp, js[:h], notas, aln, cards, pid, term, cor, ja, prof, "primeira parte")
                b = self._redigir(num, cp, js[h:], notas, aln, cards, pid, term, cor,
                                  ja + [s["titulo"] for s in a["secoes"]], prof, "continuação")
                return {"num": num, "titulo": cp["titulo"], "secoes": a["secoes"] + b["secoes"],
                        "janelas": [j.i for j in js], "slides": a["slides"] + [s for s in b["slides"] if s not in a["slides"]]}
        if r is None:
            r = self._contingencia("capitulo", ctx_cap, erro_cap)
        validos_slides = {s["id"] for s in sl}
        validos_p = {i for i, _ in paras}
        secoes = auditoria.normalizar_secoes(r.get("secoes", []), validos_slides, validos_p, cards,
                                             cp["titulo"], self.st.incluir_esquemas)
        return {"num": num, "titulo": cp["titulo"], "secoes": secoes, "janelas": [j.i for j in js],
                "slides": [s["id"] for s in sl]}

    # ---------------------------------------------------------------- 9. revisão
    def _revisao(self, trans, janelas, notas, aln, cards, term, plano, caps, decks):
        self._set_etapa("Auditoria de fidelidade e revisão")
        self._check()
        d = self.proj.load("revisao.json")
        if d:
            self._avanca(3)
            return d["apostila"], d["relatorio"]
        pid = trans.por_id()
        fontes_txt = {i: term.aplicar(p.texto) for i, p in pid.items()}
        aud = auditoria.Auditoria(trans, janelas, notas, aln, cards, term, fontes_txt, decks,
                                  perfil=self.st.perfil, remover=self.st.remover_sem_suporte,
                                  incluir_figuras=self.st.incluir_figuras)
        caps = aud.revisar_capitulos(caps, verificar=lambda itens: self._verificar(itens))
        apost = {
            "titulo": plano.get("titulo_apostila") or self._titulo_padrao(decks, trans),
            "curso": next((dk.curso for dk in decks if dk.curso), ""),
            "professores": list(dict.fromkeys(dk.professor for dk in decks if dk.professor)),
            "aulas": [{"rotulo": dk.rotulo, "professor": dk.professor, "arquivo": dk.arquivo} for dk in decks],
            "data": datetime.now().strftime("%d/%m/%Y"),
            "perfil": self.st.perfil,
            "capitulos": caps,
            "referencias": aud.referencias(),
            "pontos_conferir": aud.pontos_conferir() if self.st.incluir_pontos_conferir else [],
            "mostrar_fontes": bool(self.st.mostrar_fontes_na_apostila),
            "n_partes": len(trans.partes),
            "versao": __version__,
        }
        rel = aud.relatorio(apost)
        self.proj.save("revisao.json", {"apostila": apost, "relatorio": rel})
        self._avanca(3)
        return apost, rel

    def _verificar(self, itens: List[dict]) -> List[dict]:
        out = []
        for k in range(0, len(itens), 8):
            lote = itens[k:k + 8]
            try:
                r = self._llm_call("texto", lambda llm: llm.json(
                    "verificar", prompts.SISTEMA, prompts.prompt_verificacao(lote), prompts.SCHEMA_VERIFICACAO,
                    max_tokens=120 * len(lote) + 200, temperatura=0.0, ctx={"itens": lote}, controle=self.ctl))
                out += r.get("resultados", [])
            except Cancelado:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("Verificação de fidelidade falhou num lote: %s", e)
            self._emit(f"Verificando frases ({min(k + 8, len(itens))}/{len(itens)})")
        return out

    def _llms_vistos(self):
        seen = getattr(self.prov, "llms_vistos", None)
        return list(seen()) if callable(seen) else []

    @staticmethod
    def _titulo_padrao(decks, trans) -> str:
        if decks:
            ts = [dk.titulo for dk in decks if dk.titulo]
            if len(ts) == 1:
                return ts[0]
            if ts:
                return " • ".join(ts[:4])
        return trans.partes[0].titulo.title() if trans.partes else "Apostila"

    # ---------------------------------------------------------------- 10. composição
    def _render(self, apost, rel, trans, decks) -> Resultado:
        from ..render import docx_out, relatorio, typst_pdf

        self._set_etapa("Gerando PDF e DOCX")
        self._check()
        figdir = self.proj.sub("figuras")
        pdf_by_deck = {dk.idx: self.pdfs[dk.idx - 1] for dk in decks}
        for cap in apost["capitulos"]:
            for sec in cap["secoes"]:
                for b in sec["blocos"]:
                    if b["tipo"] == "figura":
                        m = re.match(r"A(\d+)-p(\d+)$", b["slide"])
                        if not m:
                            continue
                        dest = figdir / f"{b['slide']}.jpg"
                        if not dest.exists():
                            slides_mod.render_figura(pdf_by_deck[int(m.group(1))], int(m.group(2)), dest)
                        b["arquivo"] = str(dest)
        self.destino.mkdir(parents=True, exist_ok=True)
        res = Resultado(duracao_s=trans.duracao_s)
        work = self.proj.sub("composicao")
        pdf_tmp = work / "Apostila_Final.pdf"
        res.paginas = typst_pdf.gerar(apost, pdf_tmp, work)
        self._avanca(1, "PDF composto")
        docx_tmp = work / "Apostila_Final.docx"
        docx_out.gerar(apost, docx_tmp, work)
        self._avanca(0.5, "DOCX composto")
        rel["paginas_pdf"] = res.paginas
        rel["entradas"] = {"txts": [p.name for p in self.txts], "pdfs": [p.name for p in self.pdfs]}
        rel["duracao_s"] = trans.duracao_s
        stats = []
        for llm in self._llms_vistos():
            st = getattr(llm, "stats", None)
            if st and st.tokens_gerados:
                stats.append(f"{llm.nome}: {st.tok_s:.1f} tokens/s na geração, {st.prompt_tok_s:.0f} tokens/s na leitura")
        rel["execucao"] = {"modelos": "; ".join(self.modelos_usados) or "nenhum (sem chamadas ao modelo)",
                           "aceleracao": " | ".join(self.aceleracoes) or "—",
                           "tempo": f"{(time.monotonic() - self.t0) / 60:.1f} min" + (" — " + "; ".join(stats) if stats else "")}
        rel_pdf_tmp = work / "Relatorio_de_Fidelidade.pdf"
        relatorio.gerar(rel, apost, rel_pdf_tmp, work)
        rel_json_tmp = work / "Relatorio_de_Fidelidade.json"
        import json
        rel_json_tmp.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
        # cópia para o destino (nunca sobrescreve sem querer: nomes únicos)
        from ..util import unique_path
        reserved: set = set()
        res.pdf = unique_path(self.destino, "Apostila_Final", ".pdf", reserved)
        res.docx = unique_path(self.destino, "Apostila_Final", ".docx", reserved)
        res.relatorio = unique_path(self.destino, "Relatorio_de_Fidelidade", ".pdf", reserved)
        res.relatorio_json = unique_path(self.destino, "Relatorio_de_Fidelidade", ".json", reserved)
        for src, dst in ((pdf_tmp, res.pdf), (docx_tmp, res.docx), (rel_pdf_tmp, res.relatorio),
                         (rel_json_tmp, res.relatorio_json)):
            tmp = dst.with_name(".~" + dst.name)
            shutil.copyfile(src, tmp)
            tmp.replace(dst)
        res.palavras = rel.get("palavras_apostila", 0)
        res.avisos = self.avisos + rel.get("avisos", [])
        self.proj.save("concluido.json", {"pdf": str(res.pdf), "docx": str(res.docx), "quando": datetime.now().isoformat()})
        (self.proj.dir / "concluido.json").touch()
        self._avanca(1.5, "Concluído")
        return res
