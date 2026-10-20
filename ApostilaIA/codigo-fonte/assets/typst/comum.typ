// ApostilaIA — definições visuais comuns (apostila, relatório e esquemas para o DOCX)
#let azul = rgb("#1F4E79")
#let azul2 = rgb("#2E75B6")
#let cinza = rgb("#5B6470")
#let linha = rgb("#C9D3DE")
#let sans = ("IBM Plex Sans", "DejaVu Sans")
#let serif = ("IBM Plex Serif", "Libertinus Serif")

#let cores = (
  observacao: (rgb("#EDF4FB"), rgb("#2E75B6"), "OBSERVAÇÃO DA PROFESSORA"),
  dica: (rgb("#EDF7F0"), rgb("#2E7D4F"), "DICA CLÍNICA"),
  atencao: (rgb("#FDF4E4"), rgb("#B86E00"), "PONTO DE ATENÇÃO"),
  exemplo: (rgb("#F2F0F8"), rgb("#5E4FA2"), "EXEMPLO DISCUTIDO"),
  passo_a_passo: (rgb("#EAF5F5"), rgb("#1C7C7D"), "PASSO A PASSO"),
)

// texto com **negrito** (único realce aceito na saída do modelo)
#let rich(s) = {
  let partes = str(s).split("**")
  for (i, p) in partes.enumerate() {
    if calc.odd(i) { strong(p) } else { p }
  }
}

#let quadro(b) = {
  let c = cores.at(b.subtipo)
  block(width: 100%, fill: c.at(0), stroke: (left: 3pt + c.at(1)), inset: (x: 11pt, y: 9pt), radius: (right: 3pt),
        breakable: true, above: 1.1em, below: 1.1em)[
    #text(font: sans, size: 8.4pt, weight: "bold", fill: c.at(1), tracking: 0.06em)[#c.at(2)]
    #v(-0.2em)
    #set text(size: 10pt)
    #if b.texto != "" { par(rich(b.texto)) }
    #if b.itens.len() > 0 {
      if b.subtipo == "passo_a_passo" { enum(..b.itens.map(i => rich(i))) } else { list(..b.itens.map(i => rich(i))) }
    }
  ]
}

#let esquema(b) = {
  let n = b.itens.len()
  let caixa(t) = box(fill: rgb("#EDF4FB"), stroke: 0.8pt + azul2, radius: 3pt, inset: (x: 7pt, y: 6pt),
                     text(font: sans, size: 8.8pt, fill: azul, hyphenate: false)[#rich(t)])
  block(width: 100%, above: 1.1em, below: 1.1em, breakable: false)[
    #if b.texto != "" { align(center, text(font: sans, size: 9pt, weight: "semibold", fill: azul)[#b.texto]); v(0.2em) }
    #if b.subtipo == "comparacao" {
      let cols = calc.min(n, 3)
      grid(columns: (1fr,) * cols, column-gutter: 8pt, row-gutter: 8pt,
        ..b.itens.map(i => {
          let p = i.split(":")
          block(width: 100%, fill: rgb("#F5F8FB"), stroke: 0.8pt + azul2, radius: 3pt, inset: 8pt)[
            #set par(justify: false)
            #if p.len() > 1 {
              text(font: sans, size: 9pt, weight: "bold", fill: azul)[#p.at(0)]
              linebreak()
              text(size: 9pt)[#rich(p.slice(1).join(":").trim())]
            } else { text(size: 9pt)[#rich(i)] }
          ]
        }))
    } else if n <= 5 and b.itens.map(i => i.len()).fold(0, (a, x) => a + x) < 150 {
      align(center, {
        for (k, it) in b.itens.enumerate() {
          caixa(it)
          if k < n - 1 { h(4pt); text(fill: azul2, size: 12pt)[→]; h(4pt) }
        }
      })
    } else {
      align(center, stack(spacing: 3pt,
        ..b.itens.enumerate().map(((k, it)) => {
          let s = (block(width: 78%, fill: rgb("#EDF4FB"), stroke: 0.8pt + azul2, radius: 3pt, inset: (x: 8pt, y: 5pt),
                         align(center, text(font: sans, size: 9pt, fill: azul)[#rich(it)])),)
          if k < n - 1 { s.push(text(fill: azul2, size: 11pt)[↓]) }
          s
        }).flatten()))
    }
  ]
}

