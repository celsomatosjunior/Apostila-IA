# ApostilaIA 1.0.0 — Arquitetura

## Visão geral

```
TXT (TranscritorIA) ─┐                          ┌─> Apostila_Final.pdf  (Typst, fontes IBM Plex embutidas)
                     ├─> pipeline com checkpoints ┼─> Apostila_Final.docx (python-docx, editável no Word)
PDFs dos slides ─────┘   (IA local: llama.cpp)   └─> Relatorio_de_Fidelidade.pdf/.json
```

Tudo roda no computador do usuário. A internet só é usada uma vez, com consentimento, para baixar os
modelos (Hugging Face) e, opcionalmente, o llama.cpp CUDA (GitHub oficial do llama.cpp).

## Módulos (`apostila/`)

| Módulo | Função |
|---|---|
| `fontes/transcricao.py` | Lê o TXT do TranscritorIA (cabeçalho, duração, parágrafos, `[hh:mm:ss]`, rodapé). Várias partes em ordem natural. IDs estáveis `P<parte>.<n>`. |
| `fontes/slides.py` | PyMuPDF: texto com tamanhos de fonte, título, tabelas da camada de texto, área de imagens, referências bibliográficas, professor(a)/curso da capa, renderização JPEG das páginas, detecção de páginas duplicadas, classificação (texto/misto/imagem/divisória/capa). |
| `llm/modelos.py` | Catálogo (tamanhos e SHA-256 conferidos) e escolha automática do conjunto A/B/C pelo hardware. |
| `llm/runtime.py` | Localiza o llama.cpp (Vulkan/CPU embutidos; CUDA 12.4 ou 13.4 baixado), lista dispositivos reais com `--list-devices`. |
| `llm/servidor.py` | Processo `llama-server` (127.0.0.1, porta e chave aleatórias), `--fit` automático com margem de VRAM por modo, KV cache q8_0, leitura do log para **verificar** camadas na GPU. |
| `llm/cliente.py` | `/apply-template` + `/completion` com `json_schema` (gramática garante JSON válido), streaming interrompível (Pausar/Cancelar), visão por `multimodal_data` com fallback para a API de chat. |
| `llm/motor.py` | Um modelo por vez; fallback CUDA → Vulkan → CPU; reinício após falha do driver. |
| `llm/simulador.py` | Simulador extrativo determinístico **só para testes** (não é IA). |
| `pipeline/segmentacao.py` | Janelas de ~1.800 tokens cortadas em mudanças de tema (TF-IDF), com contexto anterior. |
| `pipeline/alinhamento.py` | Cruzamento fala × slides em blocos de ~300 tokens: TF-IDF (palavras, bigramas, n-gramas de caracteres) + Viterbi; associações sem evidência não são forçadas; slides não comentados entram "por posição". |
| `pipeline/termos.py` | Correções de transcrição sustentadas pelos slides (contexto de bigramas); demais casos vão para "a conferir". |
| `pipeline/numeros.py` | Divergências numéricas fala × slide; números sem fonte na apostila. |
| `pipeline/prompts.py` | Regras invioláveis de fidelidade, esquemas JSON de cada etapa, perfis de extensão. |
| `pipeline/orquestrador.py` | Etapas, progresso, ETA, pausa, cancelamento, checkpoints por etapa/slide/trecho/capítulo. |
| `pipeline/auditoria.py` | As 10 verificações de fidelidade, remoção de frases sem suporte (verificadas pelo modelo), duplicatas, esquemas sem sustentação, reinserção de observações essenciais, figuras, relatório. |
| `render/typst_pdf.py`, `assets/typst/*.typ` | PDF: capa, sumário navegável, marcadores, cabeçalhos, quadros, tabelas com cabeçalho repetido, figuras proporcionais, esquemas vetoriais. |
| `render/docx_out.py` | DOCX com estilos nativos de título, campo de sumário, quadros como tabelas sombreadas, tabelas com cabeçalho repetido. |
| `render/relatorio.py` | Relatório de fidelidade em PDF. |
| `monitor.py` | RAM/VRAM a cada 2 s; pausa automática com memória crítica e retomada. |
| `preparo.py` | Download com consentimento (retomada + SHA-256). |
| `gui/` | Interface PySide6 em português, arrastar e soltar. |
| `cli.py` | `ApostilaIA-cli.exe --diagnostico / --preparar / --txt ... --pdf ...`. |

## Etapas e checkpoints

`%LOCALAPPDATA%\ApostilaIA\projetos\`:

- `_cache\<id-das-fontes>\` — leitura dos PDFs, renderizações, **um cartão por slide** (visão),
  segmentação, alinhamento, termos e **notas por trecho**. Não depende do perfil: gerar de novo em outro perfil
  reaproveita tudo isso.
- `<id-do-projeto>\` — plano, **um arquivo por capítulo**, revisão, figuras e composição.

Cada checkpoint é JSON com hash SHA-256 do conteúdo; arquivo corrompido é descartado e refeito sozinho.
O id depende do **conteúdo** dos arquivos de entrada: um TXT alterado nunca reaproveita resultados antigos.

## Modelos (conjuntos)

| Conjunto | Quando | Texto | Visão | Download |
|---|---|---|---|---|
| A — Qualidade máxima | RAM ≥ 28 GB (ou ≥ 22 GB com GPU ≥ 12 GB) | Qwen3-30B-A3B-Instruct-2507 UD-Q4_K_XL (MoE, 3B ativos) | Qwen3-VL-8B-Instruct Q4_K_M + mmproj Q8_0 | 21,9 GB |
| B — Econômico | RAM ≥ 14 GB ou GPU ≥ 8 GB | Qwen3-VL-8B (mesmo modelo) | idem | 5,4 GB |
| C — Leve | demais | Qwen3-VL-4B | idem | 2,7 GB |

Nos computadores-alvo (i7-10700 + 32 GB + RTX 3070 8 GB; RTX 4090M; RTX 5070 Ti; RX 9070 XT) o
conjunto A é escolhido; o llama.cpp coloca na GPU o que couber (`--fit`), deixando os especialistas
restantes do MoE na RAM. Texto e visão são carregados em sequência, nunca juntos.

## Fidelidade (como é garantida)

1. Prompts com regras invioláveis em todas as etapas; o modelo recebe apenas trechos da transcrição e
   cartões dos slides.
2. Representação intermediária: notas fiéis por trecho, com IDs dos parágrafos de origem.
3. Redação por capítulo com a transcrição marcada com os slides exibidos em cada trecho.
4. Auditoria: frases com baixa cobertura lexical ou números sem fonte são verificadas pelo modelo contra
   os trechos de origem; "sem suporte" é removida e registrada; esquemas sem sustentação são descartados.
5. Correções de termos apenas quando a forma correta está impressa nos slides; o resto é sinalizado.
6. Divergências numéricas fala × slide nunca são "resolvidas" — vão para o relatório e para o apêndice.
