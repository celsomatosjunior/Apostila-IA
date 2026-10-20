// Esquema isolado (imagem PNG para o DOCX)
#import "comum.typ": *
#let e = json("esquema.json")
#set text(font: serif, size: 10.5pt, lang: "pt", region: "br")
#set page(width: 16cm, height: auto, margin: 3pt, fill: white)
#esquema(e)
