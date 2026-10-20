"""Gerador de dados SINTÉTICOS de teste (nenhum conteúdo de aula real).

Produz transcrições no formato do TranscritorIA (fala com marcas de oralidade,
erros típicos de reconhecimento de fala) e PDFs de slides com:
  - capa com "Professor:" e nome; páginas de texto; página divisória;
  - slides "achatados" em imagem (sem texto extraível);
  - imagens que imitam ultrassonografia (ruído speckle + rótulos);
  - tabela; referência bibliográfica impressa.
O texto é fictício e serve apenas para testar o programa.
"""
from __future__ import annotations

import io
import random
from pathlib import Path
from typing import List

TOPICOS = [
    {
        "slide": ("Situs solitus", ["Arranjo habitual dos órgãos", "Átrio morfologicamente direito à direita",
                                    "Estômago à esquerda", "Eixo cardíaco: 25 a 65 graus"]),
        "fala": [
            "Bom, pessoal, vamos começar falando do sítios solitus, né, que é o arranjo habitual dos órgãos. "
            "O átrio morfologicamente direito fica à direita e o estômago fica à esquerda, tá?",
            "Uma coisa importante: o eixo cardíaco normal fica entre 25 e 65 graus. Se o eixo estiver fora disso, "
            "a gente tem que olhar com mais cuidado, porque isso pode indicar alguma alteração.",
            "Na prática eu sempre começo identificando o estômago, depois a posição do coração. É uma dica que "
            "facilita muito o exame no dia a dia.",
        ],
    },
    {
        "slide": ("Situs inversus", ["Imagem em espelho do situs solitus", "Estômago à direita",
                                     "Átrio morfologicamente direito à esquerda"]),
        "fala": [
            "Já o sítios inversus é a imagem em espelho do sítios solitus. Então o estômago vai estar à direita "
            "e o átrio morfologicamente direito vai estar à esquerda.",
            "Cuidado para não confundir com erro de lateralidade do transdutor. Esse é um erro frequente: se você "
            "não conferir a posição fetal antes, pode achar que é inversus quando não é.",
        ],
    },
    {
        "slide": ("Situs ambíguo e isomerismos", ["Isomerismo direito: asplenia", "Isomerismo esquerdo: poliesplenia",
                                                  "Interrupção da veia cava inferior: 59 – 75%"]),
        "fala": [
            "No sítios ambíguo a gente fala de isomerismo. No isomerismo direito geralmente tem asplenia, e no "
            "isomerismo esquerdo tem poliesplenia.",
            "A interrupção da veia cava inferior no isomerismo esquerdo acontece em 90% dos casos, então quando "
            "você vê a continuação pela ázigos, pensa em isomerismo esquerdo.",
            "Por exemplo, teve um caso que eu atendi de uma gestante de 22 semanas em que a primeira pista foi "
            "justamente a ázigos dilatada ao lado da aorta.",
        ],
    },
    {
        "slide": ("Dextroposição × dextrocardia", ["Dextroposição: coração deslocado para a direita",
                                                   "Dextrocardia: ápice voltado para a direita",
                                                   "Causas de dextroposição: hérnia diafragmática, derrame pleural"]),
        "fala": [
            "Agora vamos diferenciar destroposição de destrocardia. Na dextroposição o coração está deslocado "
            "para a direita, mas o ápice continua apontando para a esquerda.",
            "Na destrocardia o próprio ápice aponta para a direita. Então o que define é para onde aponta o ápice.",
            "As causas de dextroposição que a gente mais vê são hérnia diafragmática e derrame pleural, que "
            "empurram o coração.",
        ],
    },
    {
        "slide": ("Sequência de avaliação", ["Situs", "Posição cardíaca", "Conexões venosas",
                                             "Conexões atrioventriculares", "Conexões ventriculoarteriais"]),
        "fala": [
            "Então a sequência que eu ensino é: primeiro o situs, depois a posição cardíaca, em seguida as "
            "conexões venosas, depois as conexões atrioventriculares e por último as conexões ventriculoarteriais.",
            "Se você seguir sempre essa ordem, você não esquece nenhuma etapa. É o passo a passo da análise "
            "sequencial segmentar.",
        ],
    },
    {
        "slide": ("Atriosseptostomia de Rashkind", ["Procedimento pós-natal", "Ampliação da comunicação interatrial"]),
        "fala": [
            "Em alguns casos o bebê vai precisar do RASC logo depois do nascimento, que é a atriosseptostomia, "
            "para ampliar a comunicação interatrial.",
            "Observem que isso muda o planejamento do parto, que deve acontecer num centro com cardiologia "
            "pediátrica.",
        ],
    },
]

FILLERS = ["né", "tá", "então assim", "beleza?", "okay"]
VARIACOES = [
    "Repetindo esse ponto com outras palavras para quem chegou agora: {x}",
    "Alguém perguntou sobre isso no intervalo. {x}",
    "Voltando ao que eu falei antes, {x}",
    "Vejam bem, {x}",
]


def _oralizar(t: str, rnd: random.Random) -> str:
    ws = t.split(" ")
    if len(ws) > 8 and rnd.random() < 0.5:
        k = rnd.randint(3, len(ws) - 3)
        ws.insert(k, rnd.choice(FILLERS) + ",")
    return " ".join(ws)


def transcricao(path: Path, titulo: str, minutos: int, seed: int = 1, topicos=None, com_tempo: bool = False) -> Path:
    """~150 palavras por minuto de fala; repete os tópicos com variações até atingir a duração."""
    rnd = random.Random(seed)
    tops = topicos or TOPICOS
    alvo = minutos * 150
    paras: List[str] = []
    n = 0
    ciclo = 0
    while n < alvo:
        for t in tops:
            for f in t["fala"]:
                txt = _oralizar(f, rnd)
                if ciclo > 0:
                    txt = rnd.choice(VARIACOES).format(x=txt[0].lower() + txt[1:]) + f" (revisão {ciclo})"
                paras.append(txt)
                n += len(txt.split())
                if n >= alvo:
                    break
            if n >= alvo:
                break
        ciclo += 1
    hh, mm = divmod(minutos, 60)
    linhas = [f"AULA: {titulo.upper()}", "", f"Duração original: {hh:02d}:{mm:02d}:00", "", "TRANSCRIÇÃO", ""]
    t = 0
    for p in paras:
        if com_tempo:
            linhas.append(f"[{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}] {p}")
            t += max(5, len(p.split()) * 60 // 150)
        else:
            linhas.append(p)
        linhas.append("")
    linhas += ["—" * 40, "Transcrição automática local — teste sintético.", ""]
    path.write_text("\n".join(linhas), encoding="utf-8")
    return path


def _ultrassom(w=640, h=420, rotulos=("VCI", "AO"), seed=0) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    im = Image.new("L", (w, h), 0)
    px = im.load()
    cx, cy = w // 2, h // 2
    for y in range(h):
        for x in range(w):
            d = ((x - cx) / (w / 2)) ** 2 + ((y - cy) / (h / 2)) ** 2
            base = 120 if d < 0.8 else 20
            px[x, y] = max(0, min(255, int(base + rnd.gauss(0, 45))))
    im = im.filter(ImageFilter.GaussianBlur(1.2)).convert("RGB")
    dr = ImageDraw.Draw(im)
    for k, r in enumerate(rotulos):
        dr.text((60 + 160 * k, 40 + 30 * k), r, fill=(255, 230, 0))
        dr.line((60 + 160 * k, 60 + 30 * k, 120 + 160 * k, 140 + 30 * k), fill=(255, 230, 0), width=2)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85)
    return b.getvalue()


def slides(path: Path, titulo: str, professor: str, topicos=None, achatar: tuple = (), ultrassons: int = 2,
           tabela: bool = True, divisoria: str = "Malformações", referencia: bool = True, curso: str = "Curso de teste – Módulo 1") -> Path:
    import pymupdf

    tops = topicos or TOPICOS
    doc = pymupdf.open()
    W, H = 960, 540
    fdir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    FONTES = {"helv": fdir / "IBMPlexSans-Regular.ttf", "hebo": fdir / "IBMPlexSans-Bold.ttf"}
    _orig_new_page = doc.new_page

    def new_page(**kw):
        pg = _orig_new_page(**kw)
        orig = pg.insert_textbox

        def itb(rect, text, fontname="helv", **k2):
            nome = "plexb" if fontname == "hebo" else "plexr"
            return orig(rect, text, fontname=nome, fontfile=str(FONTES.get(fontname, FONTES["helv"])), **k2)
        pg.insert_textbox = itb
        return pg
    doc.new_page = new_page

    def page_texto(tit, linhas, ref=None):
        p = doc.new_page(width=W, height=H)
        p.insert_textbox(pymupdf.Rect(40, 30, W - 40, 110), tit, fontsize=36, fontname="hebo", color=(0.1, 0.3, 0.5))
        y = 130
        for ln in linhas:
            p.insert_textbox(pymupdf.Rect(60, y, W - 60, y + 40), "• " + ln, fontsize=22, fontname="helv")
            y += 46
        if ref:
            p.insert_textbox(pymupdf.Rect(40, H - 40, W - 40, H - 10), ref, fontsize=10, fontname="helv", color=(0.4, 0.4, 0.4))
        return p

    capa = doc.new_page(width=W, height=H)
    capa.insert_textbox(pymupdf.Rect(40, 20, 500, 50), "www.exemplo-curso.com.br", fontsize=18, fontname="helv")
    capa.insert_textbox(pymupdf.Rect(40, 380, 300, 410), "Professor:", fontsize=17, fontname="helv")
    capa.insert_textbox(pymupdf.Rect(40, 410, 500, 440), professor, fontsize=18, fontname="helv")
    capa.insert_textbox(pymupdf.Rect(40, 150, W - 40, 260), titulo, fontsize=54, fontname="hebo")
    capa.insert_textbox(pymupdf.Rect(40, 265, W - 40, 330), curso, fontsize=26, fontname="helv")
    ref_txt = "A Practical Guide Of Testing – Normal Cases. Autor Exemplo, MD; Outro Autor, MD." if referencia else None
    for k, t in enumerate(tops):
        tit, linhas = t["slide"]
        p = page_texto(tit, linhas, ref_txt if k == 0 else None)
        if k in achatar:  # slide inteiro vira imagem (texto não extraível)
            pix = p.get_pixmap(dpi=96)
            png = pix.tobytes("png")
            doc.delete_page(-1)
            q = doc.new_page(width=W, height=H)
            q.insert_image(pymupdf.Rect(0, 0, W, H), stream=png)
        if k == 1 and divisoria:
            d = doc.new_page(width=W, height=H)
            d.insert_textbox(pymupdf.Rect(40, 220, W - 40, 300), divisoria, fontsize=40, fontname="hebo")
    for u in range(ultrassons):
        p = doc.new_page(width=W, height=H)
        p.insert_textbox(pymupdf.Rect(40, 20, W - 40, 70), ["Isomerismo esquerdo – ázigos", "Dextroposição"][u % 2],
                         fontsize=28, fontname="hebo")
        p.insert_image(pymupdf.Rect(120, 80, 840, 520), stream=_ultrassom(seed=u, rotulos=("AZ", "AO") if u % 2 == 0 else ("VD", "VE")))
    if tabela:
        p = doc.new_page(width=W, height=H)
        p.insert_textbox(pymupdf.Rect(40, 20, W - 40, 70), "Isomerismos – comparação", fontsize=30, fontname="hebo")
        cab = ["Achado", "Isomerismo direito", "Isomerismo esquerdo"]
        rows = [["Baço", "Asplenia", "Poliesplenia"], ["Veia cava inferior", "Contínua", "Interrompida"],
                ["Bloqueio AV", "Raro", "Frequente"]]
        x0, y0, cw, rh = 60, 100, 280, 50
        for i, r in enumerate([cab] + rows):
            for j, c in enumerate(r):
                rect = pymupdf.Rect(x0 + j * cw, y0 + i * rh, x0 + (j + 1) * cw, y0 + (i + 1) * rh)
                p.draw_rect(rect, color=(0, 0, 0), width=1)
                p.insert_textbox(rect + (6, 12, -6, -4), c, fontsize=16, fontname="hebo" if i == 0 else "helv")
    doc.save(str(path))
    doc.close()
    return path
