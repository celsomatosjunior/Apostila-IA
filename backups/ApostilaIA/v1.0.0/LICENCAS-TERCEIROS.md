# Licenças de terceiros — ApostilaIA 1.0.0

| Componente | Versão | Licença | Uso |
|---|---|---|---|
| Python (python-build-standalone) | 3.12.8 | PSF License | interpretador embutido |
| PySide6-Essentials / Qt 6 | 6.12.0 | LGPL-3.0 | interface gráfica (bibliotecas dinâmicas, substituíveis) |
| PyMuPDF / MuPDF | 1.28.2 | AGPL-3.0 (ou licença comercial Artifex) | leitura e renderização dos PDFs |
| typst (Python) | 0.15.0 | Apache-2.0 | composição do PDF da apostila |
| python-docx | 1.2.0 | MIT | geração do DOCX |
| lxml | 6.1.3 | BSD-3-Clause | XML do DOCX |
| psutil | 7.2.2 | BSD-3-Clause | memória/CPU |
| llama.cpp (ggml) | b11435 | MIT | motor de inferência local (Vulkan/CPU; CUDA baixado sob consentimento) |
| IBM Plex Sans / Serif | 6.4.1 | SIL Open Font License 1.1 | fontes embutidas no PDF |
| Modelos Qwen3 / Qwen3-VL (baixados pelo usuário) | 2507 / VL | Apache-2.0 | modelos de linguagem e visão |

Observação sobre PyMuPDF (AGPL-3.0): o ApostilaIA é de uso pessoal e não é distribuído a terceiros nem
oferecido como serviço em rede. Se um dia for distribuído, o código-fonte completo (já versionado no
repositório privado) deve acompanhar a distribuição, ou deve-se obter licença comercial da Artifex.
Os textos completos das licenças estão em `app/assets/fonts/OFL-IBM-Plex.txt` e nos pacotes correspondentes
(`Lib/site-packages/*/LICENSE*`, `llama/*/LICENSE`).
