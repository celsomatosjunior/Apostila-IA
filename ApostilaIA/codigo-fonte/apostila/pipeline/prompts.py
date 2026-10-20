"""Instruções e esquemas JSON enviados ao modelo local.

Regra central (repetida em todas as etapas): usar SOMENTE a transcrição e os slides.
O conhecimento do modelo serve para linguagem, gramática e organização — nunca como
fonte de afirmações médicas.
"""
from __future__ import annotations

REGRAS = """REGRAS INVIOLÁVEIS:
1. Use exclusivamente as FONTES fornecidas (trechos da transcrição da aula e conteúdo dos slides).
2. Não acrescente conhecimento próprio, dados, números, protocolos, condutas, recomendações, classificações ou exemplos que não estejam nas fontes.
3. Não atribua à professora afirmações que ela não fez. Conteúdo que só aparece no slide é do slide, não da fala.
4. Seu conhecimento serve apenas para corrigir o português, organizar e deixar o texto didático.
5. Se um termo técnico parecer erro de transcrição e o slide trouxer a forma correta, use a forma do slide. Se não houver como confirmar, mantenha o termo e registre-o como duvidoso.
6. Números, porcentagens, medidas e valores: copie exatamente como nas fontes. Se fala e slide divergirem, não escolha: registre a divergência.
7. Escreva em português brasileiro culto, claro e objetivo."""

SISTEMA = ("Você é um editor de apostilas de pós-graduação médica. Transforma aulas gravadas em material "
           "de estudo fiel, sem acrescentar nada que não esteja nas fontes.\n\n" + REGRAS)

SISTEMA_VISAO = ("Você descreve slides de aulas de medicina de forma estritamente factual, sem interpretar além "
                 "do que está visível. Transcreva o texto impresso exatamente como aparece (mantendo acentos, "
                 "siglas, números e símbolos). Não faça diagnósticos nem acrescente conhecimento.")

# ------------------------------------------------------------------ visão
SCHEMA_CARTAO = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "texto_visivel": {"type": "string"},
        "tipo_visual": {"type": "string", "enum": ["ultrassonografia", "esquema_anatomico", "diagrama",
                                                   "tabela", "texto", "foto", "grafico", "misto", "outro"]},
        "descricao": {"type": "string"},
        "tabelas": {"type": "array", "maxItems": 3, "items": {
            "type": "object",
            "properties": {"cabecalho": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                           "linhas": {"type": "array", "maxItems": 25,
                                      "items": {"type": "array", "items": {"type": "string"}, "maxItems": 8}}},
            "required": ["cabecalho", "linhas"]}},
        "referencias": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": ["titulo", "texto_visivel", "tipo_visual", "descricao", "tabelas", "referencias"],
}


def prompt_cartao(texto_camada: str) -> str:
    extra = (f"\nTexto já extraído da camada de texto do PDF (pode estar incompleto):\n\"\"\"\n{texto_camada[:2500]}\n\"\"\"\n"
             if texto_camada.strip() else "")
    return ("Analise a imagem deste slide de aula." + extra + """
Devolva:
- titulo: o título impresso no slide (vazio se não houver);
- texto_visivel: TODO o texto legível do slide, inclusive rótulos de imagens, legendas, setas e itens de lista, uma linha por item;
- tipo_visual: a categoria visual predominante;
- descricao: 1 a 3 frases objetivas sobre O QUE É MOSTRADO (ex.: "Ultrassonografia em corte de quatro câmaras com setas indicando a aorta e a veia cava."), usando apenas o que está escrito ou rotulado no slide;
- tabelas: tabelas do slide transcritas célula a célula (vazio se não houver);
- referencias: referências bibliográficas impressas (autores, livro, revista, ano).
Não invente rótulos que não estejam visíveis.""")


# ------------------------------------------------------------------ notas
TIPOS_NOTA = ["conceito", "definicao", "explicacao", "observacao", "dica_clinica", "atencao", "exemplo",
              "passo_a_passo", "pergunta_resposta", "dado_numerico", "comparacao"]

SCHEMA_NOTAS = {
    "type": "object",
    "properties": {
        "tema": {"type": "string"},
        "resumo": {"type": "string"},
        "itens": {"type": "array", "maxItems": 40, "items": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": TIPOS_NOTA},
                "texto": {"type": "string"},
                "paragrafos": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "importancia": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["tipo", "texto", "paragrafos", "importancia"]}},
        "termos_duvidosos": {"type": "array", "maxItems": 12, "items": {
            "type": "object",
            "properties": {"termo": {"type": "string"}, "sugestao": {"type": "string"},
                           "motivo": {"type": "string"}, "paragrafo": {"type": "string"}},
            "required": ["termo", "sugestao", "motivo", "paragrafo"]}},
        "slides_relacionados": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
    },
    "required": ["tema", "resumo", "itens", "termos_duvidosos", "slides_relacionados"],
}


def prompt_notas(paragrafos: list, contexto_anterior: str, slides: list, correcoes: list) -> str:
    trans = "\n".join(f"[{pid}] {txt}" for pid, txt in paragrafos)
    sl = "\n".join(f"<{s['id']}> {s['titulo']}: {s['texto'][:400]}" for s in slides) or "(nenhum slide correspondente identificado)"
    cor = "\n".join(f"- \"{c['de']}\" → \"{c['para']}\" ({c['motivo']})" for c in correcoes) or "(nenhuma)"
    return f"""TAREFA: extrair, de forma fiel e completa, o conteúdo didático deste trecho da aula.

CONTEXTO ANTERIOR (apenas para entender a continuidade; não extraia daqui):
{contexto_anterior or '(início da aula)'}

SLIDES PROVAVELMENTE EXIBIDOS NESTE TRECHO (para conferir termos; não extraia conteúdo que não foi falado):
{sl}

CORREÇÕES DE TRANSCRIÇÃO SUSTENTADAS PELOS SLIDES:
{cor}

TRANSCRIÇÃO DO TRECHO (cada parágrafo com seu identificador):
{trans}

Produza:
- tema: o assunto principal do trecho (poucas palavras);
- resumo: 1 ou 2 frases;
- itens: cada informação didática relevante dita pela professora, reescrita em português correto e com o MESMO sentido, citando os identificadores dos parágrafos de origem. Classifique:
  conceito/definicao/explicacao — conteúdo teórico;
  observacao — comentário adicional da professora que complementa o slide;
  dica_clinica — experiência ou aplicação prática que ela mencionou;
  atencao — armadilha diagnóstica, erro frequente, alerta;
  exemplo — caso ou exemplo que ela discutiu;
  passo_a_passo — sequência prática ensinada (escreva as etapas na ordem, separadas por " | ");
  pergunta_resposta — pergunta de aluno e a resposta dada;
  dado_numerico — número, porcentagem ou medida citado (copie o valor exato);
  comparacao — diferenças entre duas ou mais condições.
  importancia: 3 = essencial, 2 = relevante, 1 = acessório.
  Ignore saudações, avisos logísticos, piadas e repetições sem conteúdo novo.
- termos_duvidosos: termos que parecem erro de transcrição e NÃO puderam ser confirmados pelos slides;
- slides_relacionados: identificadores <A..-p..> dos slides que a fala de fato comenta."""


# ------------------------------------------------------------------ plano
SCHEMA_PLANO = {
    "type": "object",
    "properties": {
        "titulo_apostila": {"type": "string"},
        "capitulos": {"type": "array", "minItems": 1, "maxItems": 24, "items": {
            "type": "object",
            "properties": {"titulo": {"type": "string"},
                           "inicio": {"type": "integer", "minimum": 0},
                           "secoes": {"type": "array", "items": {"type": "string"}, "maxItems": 10}},
            "required": ["titulo", "inicio", "secoes"]}},
    },
    "required": ["titulo_apostila", "capitulos"],
}


def prompt_plano(janelas: list, decks: list, n_min: int, n_max: int) -> str:
    js = "\n".join(f"{j['i']}. [{j['deck']}] {j['tema']} — {j['resumo']}" + (f" (slides: {j['slides']})" if j['slides'] else "")
                   for j in janelas)
    ds = "\n".join(f"- {d['rotulo']}: {d['estrutura']}" for d in decks) or "(sem slides)"
    return f"""TAREFA: planejar os capítulos da apostila desta aula.

MATERIAIS DE SLIDES (estrutura):
{ds}

TRECHOS DA AULA EM ORDEM (número. [material] tema — resumo):
{js}

Monte de {n_min} a {n_max} capítulos que sigam a ordem da aula. Cada capítulo começa no trecho indicado em "inicio"
(número do trecho) e vai até o trecho anterior ao início do próximo capítulo. O primeiro capítulo começa em 0.
Use títulos curtos e técnicos baseados nos próprios slides e na fala. Em "secoes", liste os subtítulos previstos,
na ordem em que os assuntos aparecem. Não crie capítulos sobre assuntos ausentes da aula.
titulo_apostila: título geral da apostila (baseado nos títulos dos slides)."""


# ------------------------------------------------------------------ capítulo
BLOCOS = ["paragrafo", "topicos", "tabela", "quadro", "figura", "esquema"]
QUADROS = ["observacao", "dica", "atencao", "exemplo", "passo_a_passo"]

SCHEMA_CAPITULO = {
    "type": "object",
    "properties": {
        "secoes": {"type": "array", "minItems": 1, "maxItems": 14, "items": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "blocos": {"type": "array", "minItems": 1, "maxItems": 40, "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "enum": BLOCOS},
                        "subtipo": {"type": "string", "enum": QUADROS + ["sequencia", "comparacao", "nenhum"]},
                        "texto": {"type": "string"},
                        "itens": {"type": "array", "items": {"type": "string"}, "maxItems": 14},
                        "cabecalho": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                        "linhas": {"type": "array", "maxItems": 20,
                                   "items": {"type": "array", "items": {"type": "string"}, "maxItems": 6}},
                        "slide": {"type": "string"},
                        "fontes": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
                    },
                    "required": ["tipo", "subtipo", "texto", "itens", "cabecalho", "linhas", "slide", "fontes"]}},
            },
            "required": ["titulo", "blocos"]}},
    },
    "required": ["secoes"],
}

PERFIL_INSTRUCOES = {
    "compacta": ("PERFIL COMPACTA: condense ao máximo sem perder conteúdo relevante. Prefira tópicos, tabelas e "
                 "esquemas a parágrafos longos. Mantenha observações, alertas e dicas essenciais da professora."),
    "equilibrada": ("PERFIL EQUILIBRADA: preserve todas as explicações relevantes da professora, elimine redundâncias "
                    "e repetições da fala e mantenha leitura confortável, com parágrafos curtos."),
    "fiel": ("PERFIL FIEL E DETALHADA: preserve o máximo de explicações orais, exemplos e comentários da professora, "
             "reescritos em linguagem escrita, eliminando apenas repetições e vícios de linguagem."),
}


def prompt_capitulo(num: int, titulo: str, secoes: list, notas: list, paragrafos: list, slides: list,
                    correcoes: list, perfil: str, palavras_alvo: int, ja_tratados: list, max_figuras: int,
                    professora: str, parte: str = "") -> str:
    ns = "\n".join(f"- ({n['tipo']}, imp {n['importancia']}) {n['texto']} [{', '.join(n['paragrafos'])}]" for n in notas)
    tr = "\n".join(txt if pid == "#" else f"[{pid}] {txt}" for pid, txt in paragrafos)
    sl = "\n".join(
        f"<{s['id']}> ({s['tipo_visual']}{', VISUAL' if s['visual'] else ''}{', só no slide' if s.get('so_slide') else ''}) "
        f"{s['titulo']}: {s['texto'][:600]}" + (f" | Descrição: {s['descricao']}" if s.get('descricao') else "")
        + (f" | Tabela: {s['tabela']}" if s.get('tabela') else "")
        for s in slides) or "(nenhum slide associado)"
    cor = "\n".join(f"- \"{c['de']}\" → \"{c['para']}\"" for c in correcoes) or "(nenhuma)"
    jt = "; ".join(ja_tratados[-30:]) or "(nenhum)"
    sec = "; ".join(secoes) or "(defina conforme o conteúdo)"
    return f"""TAREFA: redigir o CAPÍTULO {num} — "{titulo}"{(' — ' + parte) if parte else ''} da apostila.
Professora (conforme os slides): {professora or 'não identificada'}.

{PERFIL_INSTRUCOES[perfil]}
Extensão aproximada: {palavras_alvo} palavras (referência, não meta: não encha texto).

SUBTÍTULOS PREVISTOS: {sec}
ASSUNTOS JÁ TRATADOS EM CAPÍTULOS ANTERIORES (não repita): {jt}

NOTAS EXTRAÍDAS DA FALA (fiéis, com os parágrafos de origem):
{ns}

TRANSCRIÇÃO DE ORIGEM (para conferir detalhes e o sentido exato):
{tr}

SLIDES ASSOCIADOS A ESTE CAPÍTULO:
{sl}

CORREÇÕES DE TERMOS SUSTENTADAS PELOS SLIDES:
{cor}

COMO ESCREVER:
- Organize em seções ("secoes") com subtítulos claros, na ordem da aula.
- Blocos possíveis:
  paragrafo (texto) — parágrafos curtos, linguagem escrita fluida, sem marcas de oralidade;
  topicos (itens) — listas explicativas;
  tabela (cabecalho, linhas) — comparações e dados que a aula realmente apresentou (no máximo 6 colunas);
  quadro (subtipo + texto) — somente quando houver conteúdo real correspondente:
     observacao = "Observação da professora" (comentário dela que complementa o slide);
     dica = "Dica clínica" (experiência/aplicação prática que ela mencionou);
     atencao = "Ponto de atenção" (armadilha, erro frequente, alerta);
     exemplo = "Exemplo discutido" (caso ou exemplo usado na aula);
     passo_a_passo = "Passo a passo" (use "itens" com as etapas na ordem ensinada);
  figura (slide + texto) — imagem de um slide VISUAL associado (ultrassonografia, esquema); "texto" é a legenda,
     descrevendo apenas o que o slide e a fala sustentam; no máximo {max_figuras} figuras neste capítulo;
  esquema (subtipo sequencia|comparacao + itens) — esquema simples quando ajudar a compreensão e estiver
     sustentado pelas fontes (ex.: sequência de avaliação ensinada). Não invente esquemas.
- Conteúdo marcado "só no slide" pode entrar quando for relevante (ex.: tabela, estatística, classificação do slide),
  sem atribuí-lo à fala da professora.
- Em "fontes" cite os identificadores usados ([P..] dos parágrafos e <A..-p..> dos slides, sem os sinais).
- Campos que não se aplicam ao bloco: deixe texto "", listas vazias, slide "" e subtipo "nenhum".
- Não use frases como "a professora disse" em todo parágrafo; escreva como texto de apostila.
  Use "a professora destaca/observa" apenas nos quadros de observação, quando fizer sentido.
- Não repita o título do capítulo como primeira seção. Não escreva introduções ou conclusões genéricas."""


# ------------------------------------------------------------------ verificação
SCHEMA_VERIFICACAO = {
    "type": "object",
    "properties": {
        "resultados": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"},
                           "veredito": {"type": "string", "enum": ["sustentada", "parcial", "sem_suporte"]},
                           "comentario": {"type": "string"}},
            "required": ["id", "veredito", "comentario"]}},
    },
    "required": ["resultados"],
}


def prompt_verificacao(itens: list) -> str:
    blocos = []
    for it in itens:
        blocos.append(f"### Frase {it['id']}\nFRASE DA APOSTILA: {it['frase']}\nFONTES:\n{it['fontes']}")
    return ("TAREFA: auditoria de fidelidade. Para cada frase, verifique se ela é sustentada pelas FONTES "
            "(trechos da transcrição e slides). 'sustentada' = todo o conteúdo está nas fontes (mesmo com outras "
            "palavras); 'parcial' = parte está nas fontes, mas há acréscimo; 'sem_suporte' = afirmação ausente das "
            "fontes. No comentário, diga em poucas palavras o que está sem suporte.\n\n" + "\n\n".join(blocos))
