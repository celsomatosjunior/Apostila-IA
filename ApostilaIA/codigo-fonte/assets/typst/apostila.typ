// ApostilaIA 1.0.0 — modelo de composição (Typst). Os dados vêm de dados.json;
// nenhum texto é interpretado como marcação (sem risco de caracteres especiais).
#let d = json("dados.json")

#import "comum.typ": *

#set document(title: d.titulo, author: d.professores)
#set text(font: serif, size: 10.5pt, lang: "pt", region: "br", hyphenate: true)
#set par(justify: true, leading: 0.66em, spacing: 0.9em)
#set list(indent: 0.6em, body-indent: 0.5em, spacing: 0.55em, marker: (text(fill: azul2)[•], text(fill: azul2)[–]))
#set enum(indent: 0.6em, body-indent: 0.5em, spacing: 0.55em)
#set heading(numbering: "1.1")
#show heading: set text(font: sans, fill: azul)
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  v(0.6cm)
  block(width: 100%, below: 0.9em)[
    #if it.numbering != none {
      text(size: 10pt, weight: "medium", fill: azul2, tracking: 0.08em)[CAPÍTULO #counter(heading).display("1")]
      v(-0.35em)
    }
    #text(size: 19pt, weight: "semibold", fill: azul, it.body)
    #v(-0.45em)
    #line(length: 100%, stroke: 1.2pt + azul2)
  ]
}
#show heading.where(level: 2): it => block(above: 1.35em, below: 0.7em, sticky: true)[
  #text(size: 13pt, weight: "semibold", fill: azul)[#if it.numbering != none [#counter(heading).display() #h(0.35em)]#it.body]
]
#show figure.caption: it => text(font: sans, size: 8.6pt, fill: cinza)[#it.supplement #context it.counter.display(it.numbering) — #it.body]
#show figure.where(kind: table): set block(breakable: true)
#show figure.where(kind: table): set figure.caption(position: top)
#set figure(gap: 0.6em)
#set table(stroke: 0.5pt + linha)
#show table.cell: set par(justify: false)
#show table.cell: set text(font: sans, size: 8.8pt)

// ------------------------------------------------------------------ CAPA
#page(margin: 0cm, header: none, footer: none)[
  #block(width: 100%, height: 7.2cm, fill: azul, inset: (x: 2.4cm, top: 2.6cm), below: 0pt)[
    #set text(fill: white, font: sans)
    #text(size: 10pt, tracking: 0.12em, weight: "medium")[#upper(if d.curso != "" { d.curso } else { "Apostila de estudo" })]
  ]
  #block(width: 100%, height: 0.18cm, fill: azul2, above: 0pt)[]
  #pad(x: 2.4cm, bottom: 2cm)[
    #v(2.2cm)
    #text(font: sans, size: 30pt, weight: "semibold", fill: azul)[#d.titulo]
    #v(0.5cm)
    #line(length: 3.2cm, stroke: 2pt + azul2)
    #v(0.6cm)
    #set text(font: sans, size: 11.5pt, fill: cinza)
    #if d.professores.len() > 0 [
      #text(weight: "medium", fill: azul)[#if d.professores.len() == 1 [Professora] else [Professoras]]: #d.professores.join(", ")
      #v(0.2cm)
    ]
    #if d.aulas.len() > 1 [
      #v(0.3cm)
      #for a in d.aulas [
        #text(size: 10pt)[• #a.rotulo#if a.professor != "" [ — #a.professor]] \
      ]
    ]
  ]
  #place(bottom + left, dx: 2.4cm, dy: -2cm, block(width: 21cm - 4.8cm, inset: (top: 0.5cm), stroke: (top: 0.6pt + linha))[
    #set text(font: sans, size: 9pt, fill: cinza)
    Apostila de estudo elaborada exclusivamente a partir da transcrição da aula e dos slides apresentados.
    Perfil: #d.perfil_rotulo. Gerada em #d.data pelo ApostilaIA #d.versao (processamento local).
  ])
]

// ------------------------------------------------------------------ CORPO
#set page(
  paper: "a4",
  margin: (x: 2.3cm, top: 2.6cm, bottom: 2.3cm),
  header: context {
    let n = counter(page).get().first()
    let pg = here().page()
    let nesta = query(heading.where(level: 1)).filter(h => h.location().page() == pg)
    let hs = query(heading.where(level: 1).before(here()))
    let cap = if nesta.len() > 0 { nesta.first().body } else if hs.len() > 0 { hs.last().body } else { [] }
    set text(font: sans, size: 8pt, fill: cinza)
    grid(columns: (1fr, auto), align: (left, right), d.titulo_curto, cap)
    v(-0.5em)
    line(length: 100%, stroke: 0.4pt + linha)
  },
  footer: context {
    set text(font: sans, size: 8.5pt, fill: cinza)
    align(center, counter(page).display("1"))
  },
)
#counter(page).update(1)

#outline(title: [Sumário], depth: 2, indent: auto)

#let bloco(b) = {
  if b.tipo == "paragrafo" { par(rich(b.texto)) }
  else if b.tipo == "topicos" {
    if b.at("texto", default: "") != "" { par(rich(b.texto)) }
    list(..b.itens.map(i => rich(i)))
  }
  else if b.tipo == "quadro" { quadro(b) }
  else if b.tipo == "esquema" { esquema(b) }
  else if b.tipo == "tabela" {
    let n = b.cabecalho.len()
    figure(kind: table, supplement: [Tabela], caption: if b.texto != "" [#b.texto] else { none },
      table(columns: (1fr,) * n, inset: (x: 6pt, y: 5pt), align: left + horizon,
        fill: (x, y) => if y == 0 { azul } else if calc.even(y) { rgb("#F4F7FA") } else { white },
        table.header(..b.cabecalho.map(c => text(fill: white, weight: "bold")[#c])),
        ..b.linhas.flatten().map(c => [#rich(c)])))
  }
  else if b.tipo == "figura" {
    figure(kind: image, supplement: [Figura],
      block(stroke: 0.5pt + linha, inset: 2pt, image(b.arquivo, width: 100%, height: auto)),
      caption: [#b.texto#if b.texto != "" [ ]#text(style: "italic")[(#b.origem)]])
  }
}

#for cap in d.capitulos [
  = #cap.titulo
  #for sec in cap.secoes [
    #if sec.titulo != "" [
      == #sec.titulo
    ]
    #for b in sec.blocos { bloco(b) }
    #if d.mostrar_fontes and sec.at("fontes_rotulo", default: "") != "" [
      #text(font: sans, size: 7.5pt, fill: cinza)[Fontes: #sec.fontes_rotulo]
    ]
  ]
]

#if d.pontos_conferir.len() > 0 [
  #heading(numbering: none)[Termos e pontos a conferir]
  #text(size: 9.5pt, fill: cinza)[Itens que a revisão automática não pôde confirmar pelas fontes. Não foram corrigidos por suposição.]
  #v(0.4em)
  #set text(size: 9.5pt)
  #list(..d.pontos_conferir.map(p => [#if p.tipo == "divergencia" [*Divergência:* ]#p.texto]))
]

#if d.referencias.len() > 0 [
  #heading(numbering: none)[Referências citadas nos slides]
  #text(size: 9.5pt, fill: cinza)[Obras e artigos impressos nos slides da aula (o conteúdo da apostila não foi complementado com elas).]
  #v(0.4em)
  #set text(size: 9.5pt)
  #set par(justify: false)
  #list(..d.referencias.map(r => [#r]))
]
