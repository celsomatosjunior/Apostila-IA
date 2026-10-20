// ApostilaIA — Relatório de fidelidade (omissões, ambiguidades, divergências e referências internas)
#import "comum.typ": *
#let r = json("relatorio.json")

#set document(title: "Relatório de fidelidade — " + r.titulo)
#set text(font: sans, size: 9.5pt, lang: "pt", region: "br")
#set par(justify: false, leading: 0.6em, spacing: 0.8em)
#set page(paper: "a4", margin: (x: 2cm, top: 2.2cm, bottom: 2cm),
  header: context { set text(size: 7.5pt, fill: cinza); [Relatório de fidelidade — #r.titulo]; v(-0.4em); line(length: 100%, stroke: 0.4pt + linha) },
  footer: context { set text(size: 8pt, fill: cinza); align(center, counter(page).display("1 / 1", both: true)) })
#show heading: set text(fill: azul)
#show heading.where(level: 1): set text(size: 13pt)
#set table(stroke: 0.5pt + linha, inset: (x: 5pt, y: 4pt))
#show table.cell.where(y: 0): set text(fill: white, weight: "bold")
#let tab(cols, cab, linhas) = table(columns: cols, fill: (x, y) => if y == 0 { azul } else if calc.even(y) { rgb("#F4F7FA") },
  table.header(..cab.map(c => [#c])), ..linhas.flatten().map(c => [#c]))
#let vazio(t) = text(fill: cinza, style: "italic")[#t]

#text(size: 18pt, weight: "semibold", fill: azul)[Relatório de fidelidade]
#v(-0.3em)
#text(size: 11pt, fill: cinza)[#r.titulo]
#v(0.3em)
#line(length: 100%, stroke: 1pt + azul2)

#grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 5pt,
  [*Gerado em*], [#r.data — ApostilaIA #r.versao, processamento 100% local],
  [*Transcrição*], [#r.entradas.txts.join(", ") (#r.palavras_fala palavras#if r.duracao != "" [, #r.duracao de aula])],
  [*Slides*], [#if r.entradas.pdfs.len() > 0 { r.entradas.pdfs.join(", ") } else { "nenhum" }],
  [*Perfil*], [#r.perfil — #r.palavras_apostila palavras, #r.paginas_pdf páginas no PDF],
  [*Modelos*], [#r.execucao.modelos],
  [*Aceleração*], [#r.execucao.aceleracao],
  [*Tempo*], [#r.execucao.tempo],
)

= 1. Verificações da auditoria
#tab((auto, 1fr, 2fr, auto), ("Nº", "Verificação", "Resultado", ""),
  r.checagens.map(c => (str(c.n), c.item, c.resultado, if c.ok { text(fill: rgb("#2E7D4F"))[✓ ok] } else { text(fill: rgb("#B86E00"))[! revisar] })))

= 2. Mapa da apostila (referências internas)
Cada capítulo com os trechos da transcrição (parte e parágrafo §) e os slides usados.
#v(0.3em)
#tab((auto, 1.4fr, 1.2fr, 1.6fr), ("Cap.", "Título", "Transcrição", "Slides"),
  r.mapa.map(m => (str(m.capitulo), m.titulo, m.fala, m.slides)))

= 3. Divergências entre fala e slides
#if r.divergencias.len() == 0 [#vazio("Nenhuma divergência numérica detectada.")] else [
  Valores diferentes para o mesmo assunto. A apostila não escolheu um deles por suposição: confira na aula.
  #tab((1fr, auto, auto, 1.2fr), ("Assunto", "Na fala", "No slide", "Onde"),
    r.divergencias.map(d => (d.assunto, d.fala, d.slide, d.onde)))
]

= 4. Termos
== Corrigidos com base na grafia dos slides
#if r.termos_corrigidos.len() == 0 [#vazio("Nenhum.")] else [
  #tab((1fr, 1fr, auto, 2fr), ("Na transcrição", "Na apostila", "Ocorr.", "Motivo"),
    r.termos_corrigidos.map(c => (c.de, c.para, str(c.ocorrencias), c.motivo)))
]
== Ambíguos — não corrigidos (conferir)
#if r.termos_conferir.len() + r.termos_duvidosos_modelo.len() == 0 [#vazio("Nenhum.")] else [
  #tab((1fr, 1fr, 2fr), ("Termo", "Possível forma", "Observação"),
    r.termos_conferir.map(c => (c.de, c.para, c.motivo)) + r.termos_duvidosos_modelo.map(t => (t.termo, t.sugestao, t.motivo + " [" + t.paragrafo + "]")))
]

= 5. Conteúdo sem sustentação nas fontes
== Removido da apostila
#if r.removidas.len() == 0 [#vazio("Nenhuma frase removida.")] else [
  #tab((auto, 2fr, 1fr), ("Cap.", "Frase", "Motivo"), r.removidas.map(x => (str(x.capitulo), x.frase, x.comentario)))
]
== Parcialmente sustentado (mantido; conferir)
#if r.parciais.len() == 0 [#vazio("Nenhum.")] else [
  #tab((auto, 2fr, 1fr), ("Cap.", "Frase", "Observação"), r.parciais.map(x => (str(x.capitulo), x.frase, x.comentario)))
]
== Números sem correspondência nas fontes
#if r.numeros_sem_fonte.len() == 0 [#vazio("Nenhum.")] else [
  #tab((auto, 2fr, auto), ("Cap.", "Frase", "Número"), r.numeros_sem_fonte.map(x => (str(x.capitulo), x.frase, x.numeros.join(", "))))
]

= 6. Possíveis omissões
Itens relevantes da fala com pouca correspondência no texto final (comparação automática por vocabulário; confira).
#if r.omissoes.len() == 0 [#vazio("Nenhuma omissão relevante detectada.")] else [
  #tab((auto, 2.4fr, 1fr), ("Tipo", "Conteúdo da fala", "Onde"), r.omissoes.map(o => (o.tipo, o.texto, o.onde)))
]
#if r.reinseridas.len() > 0 [
  == Reinseridos pela auditoria
  Observações, dicas e alertas essenciais que o redator não incluiu e foram acrescentados ao fim do capítulo:
  #tab((auto, auto, 2fr), ("Cap.", "Quadro", "Texto"), r.reinseridas.map(x => (str(x.capitulo), x.tipo, x.texto)))
]
#if r.duplicados.len() > 0 [
  == Repetições removidas (até 40 exemplos; total na verificação 6)
  #tab((auto, 2fr, auto), ("Cap.", "Trecho", "Repetia o cap."), r.duplicados.map(x => (str(x.capitulo), x.texto, str(x.igual_a_capitulo))))
]
#if r.esquemas_removidos.len() > 0 [
  == Esquemas descartados por falta de sustentação
  #for e in r.esquemas_removidos [- Cap. #e.capitulo: #e.etapas.join(" → ")]
]

= 7. Slides e associação com a fala
"fala" = slide comentado na transcrição; "posição" = não comentado, incluído pela ordem do material; "nenhuma" = não utilizado.
#v(0.3em)
#tab((auto, 2fr, auto, auto, auto, auto), ("Slide", "Título", "Cap.", "Associação", "Figura", "Visão"),
  r.slides.map(s => (s.slide, s.titulo, if s.capitulo == none { "—" } else { str(s.capitulo) }, s.associacao,
                     if s.figura { "sim" } else { "" }, if s.visao { "sim" } else { "não" })))
#if r.janelas_sem_slide.len() > 0 [
  #v(0.4em)
  Trechos da fala sem slide correspondente (associação não forçada): #r.janelas_sem_slide.map(j => str(j + 1)).join(", ").
]

#if r.avisos.len() > 0 [
  = 8. Avisos
  #for a in r.avisos [- #a]
]
