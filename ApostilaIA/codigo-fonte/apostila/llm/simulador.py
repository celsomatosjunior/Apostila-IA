"""Simulador determinístico do modelo (somente para testes automatizados e diagnóstico).

Não é "inteligência artificial": produz saídas EXTRATIVAS a partir das próprias
fontes recebidas (frases da transcrição limpas de oralidade, textos dos slides),
no mesmo formato JSON do modelo real. Serve para testar todo o pipeline (checkpoints,
alinhamento, composição do PDF/DOCX, auditoria) sem GPU e sem baixar modelos.
Opcionalmente injeta frases "externas" para provar que a auditoria as detecta.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from typing import List, Optional

from ..pipeline.texto import frases, limpar_oralidade
from ..util import content_words
from .cliente import Controle, LLMBase, LLMCancelado, LLMInterrompido

_TIPOS = [
    ("atencao", re.compile(r"\b(cuidado|aten[çc][ãa]o|armadilha|erro|confund|n[ãa]o (pode|deve)|perigo|engan)", re.I)),
    ("dica_clinica", re.compile(r"\b(dica|na pr[áa]tica|no dia a dia|eu costumo|minha experi[êe]ncia|truque)", re.I)),
    ("exemplo", re.compile(r"\b(por exemplo|exemplo|caso|paciente|gestante)\b", re.I)),
    ("passo_a_passo", re.compile(r"\b(primeiro|segundo passo|depois|em seguida|por [úu]ltimo|passo)\b", re.I)),
    ("dado_numerico", re.compile(r"\d+\s*(%|por cento|mm|semanas)")),
    ("observacao", re.compile(r"\b(observ|lembr|importante|repar|veja|percebam)", re.I)),
    ("pergunta_resposta", re.compile(r"\?\s")),
]


def _tipo(t: str) -> str:
    for nome, rx in _TIPOS:
        if rx.search(t):
            return nome
    return "explicacao"


def _tema(textos: List[str]) -> str:
    c = Counter(w for t in textos for w in content_words(t) if len(w) > 4)
    return " ".join(w for w, _ in c.most_common(3)) or "conteúdo"


class Simulador(LLMBase):
    nome = "Simulador (testes)"
    suporta_visao = True
    descricao_aceleracao = "CPU (simulador de testes)"
    n_ctx = 1_000_000

    def __init__(self, atraso: float = 0.0, injetar_externo: bool = False, falhar_em: Optional[str] = None):
        self.atraso = atraso
        self.injetar_externo = injetar_externo
        self.falhar_em = falhar_em
        self.chamadas = Counter()

    def _espera(self, controle: Optional[Controle]):
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.atraso:
            if controle:
                controle.check()
            time.sleep(0.01)
        if controle:
            controle.check()

    def json(self, tarefa, sistema, usuario, schema, max_tokens, temperatura=0.2, ctx=None, controle=None, on_token=None):
        self.chamadas[tarefa] += 1
        if self.falhar_em and self.falhar_em == f"{tarefa}:{self.chamadas[tarefa]}":
            raise RuntimeError(f"falha simulada em {self.falhar_em}")
        self._espera(controle)
        ctx = ctx or {}
        return getattr(self, "_" + tarefa)(ctx)

    def visao(self, tarefa, sistema, usuario, imagem, schema, max_tokens, ctx=None, controle=None):
        self.chamadas["visao"] += 1
        self._espera(controle)
        p = (ctx or {}).get("pagina", {})
        txt = p.get("texto", "") if isinstance(p, dict) else ""
        tipo = p.get("tipo", "texto") if isinstance(p, dict) else "texto"
        return {"titulo": p.get("titulo", "") if isinstance(p, dict) else "", "texto_visivel": txt,
                "tipo_visual": "ultrassonografia" if tipo == "imagem" else ("misto" if tipo == "misto" else "texto"),
                "descricao": "", "tabelas": [], "referencias": []}

    # ------------------------------------------------------------ tarefas
    def _notas(self, ctx):
        paras = ctx.get("paragrafos", [])
        itens = []
        for pid, t in paras:
            limpo = limpar_oralidade(t)
            for fr in frases(limpo):
                if len(fr.split()) < 5:
                    continue
                tp = _tipo(fr)
                imp = 3 if tp in ("atencao", "dica_clinica", "exemplo", "observacao") else 2
                itens.append({"tipo": tp, "texto": fr, "paragrafos": [pid], "importancia": imp})
        tema = _tema([t for _, t in paras])
        return {"tema": tema, "resumo": (itens[0]["texto"] if itens else "")[:200], "itens": itens[:40],
                "termos_duvidosos": [], "slides_relacionados": [s["id"] for s in ctx.get("slides", [])[:3]]}

    def _plano(self, ctx):
        js = ctx.get("janelas", [])
        caps = []
        last = None
        for j in js:
            if j["i"] == 0 or (j["deck"] != last and j["deck"] != "—"):
                tit = (j["slides"].split(";")[0].strip() if j["slides"] else "") or j["tema"].capitalize()
                caps.append({"titulo": tit[:80] or f"Parte {len(caps) + 1}", "inicio": j["i"], "secoes": []})
            last = j["deck"] if j["deck"] != "—" else last
        n_max = ctx.get("n_max", 99)
        return {"titulo_apostila": "", "capitulos": caps[:n_max]}

    def _capitulo(self, ctx):
        notas = ctx.get("notas", [])
        slides = ctx.get("slides", [])
        secoes = []
        atual = {"titulo": "", "blocos": []}
        mapa_q = {"observacao": "observacao", "dica_clinica": "dica", "atencao": "atencao", "exemplo": "exemplo"}
        vazio = {"subtipo": "nenhum", "texto": "", "itens": [], "cabecalho": [], "linhas": [], "slide": "", "fontes": []}
        por_par = []
        for n in notas:
            if por_par and por_par[-1][0] == n["paragrafos"][0]:
                por_par[-1][1].append(n)
            else:
                por_par.append((n["paragrafos"][0], [n]))
        k = 0
        for pid, ns in por_par:
            if k % 6 == 0:
                if atual["blocos"]:
                    secoes.append(atual)
                tema = _tema([n["texto"] for n in ns]).capitalize()
                atual = {"titulo": tema, "blocos": []}
            k += 1
            corpo = [n for n in ns if n["tipo"] not in mapa_q]
            if corpo:
                atual["blocos"].append(dict(vazio, tipo="paragrafo", texto=" ".join(n["texto"] for n in corpo),
                                            fontes=[pid]))
            for n in ns:
                if n["tipo"] in mapa_q:
                    atual["blocos"].append(dict(vazio, tipo="quadro", subtipo=mapa_q[n["tipo"]], texto=n["texto"],
                                                fontes=[pid]))
        if atual["blocos"]:
            secoes.append(atual)
        figs = [s for s in slides if s.get("visual")][: ctx.get("max_figuras", 2)]
        for i, s in enumerate(figs):
            alvo = secoes[min(i, len(secoes) - 1)] if secoes else None
            if alvo is not None:
                alvo["blocos"].append(dict(vazio, tipo="figura", slide=s["id"], texto=s["titulo"] or "Slide da aula",
                                           fontes=[s["id"]]))
        for s in slides:
            if s.get("tabela") and secoes:
                partes = [r.split(" | ") for r in s["tabela"].split(" / ")]
                if len(partes) >= 2:
                    secoes[-1]["blocos"].append(dict(vazio, tipo="tabela", cabecalho=partes[0], linhas=partes[1:],
                                                     texto=s["titulo"], fontes=[s["id"]]))
        if self.injetar_externo and secoes:
            secoes[0]["blocos"].append(dict(vazio, tipo="paragrafo", fontes=[],
                                            texto="Segundo diretrizes internacionais recentes, recomenda-se repetir o exame "
                                                  "com ressonância magnética fetal em 97% dos casos."))
        if not secoes:
            secoes = [{"titulo": ctx.get("titulo", ""), "blocos": [dict(vazio, tipo="paragrafo", texto="(sem conteúdo)")]}]
        return {"secoes": secoes}

    def _verificar(self, ctx):
        out = []
        for it in ctx.get("itens", []):
            fv = set(content_words(it["fontes"]))
            cw = content_words(it["frase"])
            cov = sum(1 for w in cw if w in fv) / max(1, len(cw))
            nums = re.findall(r"\d+", it["frase"])
            nums_ok = all(n in it["fontes"] for n in nums)
            v = "sustentada" if (cov >= 0.6 and nums_ok) else ("parcial" if cov >= 0.4 and nums_ok else "sem_suporte")
            out.append({"id": it["id"], "veredito": v, "comentario": "" if v == "sustentada" else "termos ausentes das fontes"})
        return {"resultados": out}


class ProvedorSimulado:
    """Provedor para o pipeline usando o simulador (testes)."""

    def __init__(self, sim: Optional[Simulador] = None):
        self.sim = sim or Simulador()
        self.cargas = Counter()
        self._atual = None

    def obter(self, papel, cancel=None):
        if self._atual != papel:
            self.cargas[papel] += 1  # registra trocas de modelo (nunca dois carregados juntos)
            self._atual = papel
        return self.sim

    def reiniciar(self, papel, cancel=None):
        self._atual = None
        return self.obter(papel, cancel)

    def liberar(self):
        self._atual = None

    def descricao(self):
        return "CPU (simulador de testes)"
