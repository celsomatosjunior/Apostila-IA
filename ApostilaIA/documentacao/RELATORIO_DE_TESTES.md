# Relatório de testes — ApostilaIA 1.0.0

Data: 19/10/2026. Ambiente de compilação e teste: contêiner Linux x86-64 (2 núcleos, 8 GB de RAM,
**sem GPU**), Python 3.13 para os testes nativos e Wine 9 para os binários Windows.
Não havia Windows real nem placa de vídeo disponível. Essas limitações estão declaradas abaixo.
Nenhum teste foi declarado aprovado sem ter sido executado.

## Resumo

| Bateria | Resultado |
|---|---|
| `pytest tests` (16 obrigatórios + extras + 8 testes de módulos) | **26 aprovados, 0 falhas** (92 s) |
| Instalador no Wine (`build/windows/testar_instalador.sh`) | **20 verificações, 0 falhas** |
| Pipeline completo com modelo GGUF **real** no llama.cpp (`tools/teste_integracao_llm.py`) | concluído: PDF de 7 páginas gerado em 12 min (CPU, 2 threads) |
| Avaliação com os documentos de referência do usuário (local, fora do repositório) | concluída; resultados agregados abaixo |

## Os 16 testes obrigatórios

Os testes de pipeline usam **dados sintéticos** gerados por `tests/sintetico.py`. São transcrições
fictícias no formato do TranscritorIA, com oralidade e erros típicos ("sítios solitus", "destrocardia",
"RASC"), e PDFs com capa, páginas de texto, slides achatados em imagem, imagens que imitam ultrassonografia,
tabela e referência bibliográfica. Nenhum material de aula real foi para o repositório.

Nesses testes, o modelo de IA é substituído por um **simulador extrativo** (`apostila/llm/simulador.py`).
Por isso eles validam a mecânica (leitura, cruzamento, checkpoints, auditoria e composição) e **não** a
qualidade da redação do Qwen.

| Nº | Teste | Execução real | Resultado |
|---|---|---|---|
| 1 | TXT curto e PDF simples | aula de 6 min + PDF de 4 páginas → PDF, DOCX e relatório na pasta escolhida, com os nomes `Apostila_Final.*` | aprovado |
| 2 | Aula com vários PDFs | 2 TXT + 2 PDFs passados fora de ordem; ordem natural restaurada; slides dos dois PDFs associados à fala; as duas professoras na capa | aprovado |
| 3 | Transcrição de mais de 2 horas | 130 min (~19.500 palavras): segmentada em trechos de no máximo 2.520 tokens, uma chamada de notas por trecho, ≥ 2 capítulos, progresso monotônico com estimativa de tempo | aprovado (3,7 s com o simulador) |
| 4 | Transcrição de ~5 horas | 300 min (~45.000 palavras): mesmas verificações; capítulos grandes divididos automaticamente | aprovado (5,7 s com o simulador) |
| 5 | Slides com muitas imagens | 30 páginas de imagem (6 slides achatados e 24 ultrassonografias): todas classificadas como "imagem" e enviadas ao modelo de visão (≥ 28 chamadas) | aprovado |
| 6 | Slides com ultrassonografias | slides de ultrassom marcados como visuais e incluídos como figuras; proporção 16:9 preservada (sem deformação) | aprovado |
| 7 | PDFs com pouco texto extraível | slides achatados: 0 palavras extraíveis, tipo "imagem", exigem visão; com a visão desligada o relatório avisa | aprovado |
| 8 | Tabelas e esquemas | tabela lida da camada de texto do PDF; esquema sustentado mantido (vetorial no PDF, imagem no DOCX); esquema inventado descartado pela auditoria; tabela no PDF e no DOCX | aprovado |
| 9 | Terminologia médica | "sítios"→"situs" corrigido (forma impressa no slide); "destrocardia" e "Catia"→"Katia" (nome da professora) marcados para conferência; nome da professora correto na apostila | aprovado |
| 10 | Geração de PDF | marcadores, links do sumário, fontes IBM Plex embutidas, nenhuma página vazia, numeração no rodapé, nenhum bloco de texto fora da página | aprovado |
| 11 | Geração de DOCX | estilos de título nativos, campo de sumário, quadros, imagens; reaberto, editado e salvo com python-docx | aprovado (Microsoft Word não estava disponível; ver limitações) |
| 12 | Retomada após interrupção | cancelado logo após o 1º capítulo; na nova execução nenhuma nota ou leitura visual foi refeita, só os capítulos que faltavam; checkpoint corrompido é descartado e refeito; pausa e continuação também testadas | aprovado |
| 13 | Funcionamento offline | geração completa com toda conexão de rede bloqueada (exceto 127.0.0.1), sem nenhuma tentativa de acesso; modelo GGUF real no llama.cpp sem rede devolvendo JSON válido no esquema das notas | aprovado |
| 14 | Uso efetivo da GPU | **sem GPU no ambiente.** Testado: a GPU só é declarada quando o log do llama.cpp mostra camadas e buffer na GPU (0/49 camadas → "CPU"); argumentos de CPU nunca pedem GPU; `--fit` com margem do modo Trabalho; escolha do conjunto A para i7-10700 + 32 GB + RTX 3070; CUDA 13.4 para RTX 5070 Ti | parcial: lógica aprovada; aceleração real **não medida** |
| 15 | Instalação e desinstalação Windows | no Wine: instalação silenciosa, arquivos, registro, atalho, programa instalado executando, geração completa no Python do Windows, `llama-server.exe` do Windows com modelo real, desinstalação | aprovado no Wine; Windows real **não testado** |
| 16 | Fidelidade transcrição × slides × apostila | frase externa injetada ("diretrizes internacionais… 97%") detectada e removida; divergência 90% (fala) × 59–75% (slide) registrada sem escolher valor; exemplos, observações e assuntos preservados; ≤ 3 frases com baixa cobertura; mapa de referências internas; referência bibliográfica no apêndice | aprovado |

## Instalação e desinstalação (Wine 9)

`ApostilaIA-Setup-1.0.0.exe` (67 MB), testado com `build/windows/testar_instalador.sh`:

- Instalação silenciosa em `C:\Program Files\ApostilaIA`, com registro de desinstalação (versão 1.0.0) e
  atalho no Menu Iniciar.
- `ApostilaIA-cli.exe --diagnostico` abre e detecta CPU, RAM, recursos AVX/AVX2 e a GPU virtual do Wine.
- **Geração completa no Python do Windows instalado** (PyMuPDF, Typst e python-docx do instalador). O
  simulador entra no lugar do modelo. Resultado: PDF de 9 páginas com 16 marcadores, DOCX e relatório.
- **`llama-server.exe` (Windows, CPU)** carregou um GGUF real e devolveu JSON válido pela gramática.
- Desinstalação silenciosa: programa, registro e atalhos removidos; as apostilas do usuário são preservadas.

## Pipeline com modelo real (Linux, CPU)

`tools/teste_integracao_llm.py` passa pelo `Motor` real: descoberta de backends, carga do llama-server,
`/apply-template` + `/completion` com `json_schema`, notas, plano, capítulo, auditoria, PDF e DOCX.

Modelo usado: TinyLlama 1.1B IQ2_XXS (o único GGUF acessível; o Hugging Face está bloqueado neste
ambiente). Resultados:

- 10 chamadas ao modelo, 6.278 tokens gerados.
- Velocidade: 9,7 tokens/s na geração e 47 tokens/s na leitura.
- Tempo total: 742 s.
- O relatório registrou a aceleração como "CPU (2 threads)". O programa não declarou GPU.

Esse teste encontrou e corrigiu problemas reais:

- Respostas cortadas pelo limite de tokens: agora o JSON é reparado e os elementos completos são aproveitados.
- Contexto pequeno do modelo: o trecho é dividido ao meio.
- Falha persistente do modelo num trecho: agora existe a "contingência extrativa". O trecho é montado direto
  da fonte, continua fiel e fica registrado nos avisos do relatório. Assim um trecho problemático não perde
  horas de trabalho.

A qualidade do texto do TinyLlama é inútil e **não** representa o Qwen.

## Avaliação com os documentos de referência (local, autorizada)

Feita com a apostila "MODULO 2" (texto usado como substituto da transcrição) e os três PDFs de slides reais.
Nada disso foi para o repositório.

- As 173 páginas foram lidas e renderizadas sem erro.
- 68 slides associados ao texto e 97 por posição.
- O PDF "Análise sequencial segmentar" (só imagens) ficou sem associação. Era o esperado: sem o modelo de
  visão não há texto para comparar, e isso confirma que a visão é indispensável para esse material.
- Duas divergências numéricas reais entre texto e slides foram detectadas.

A primeira versão do corretor de termos **propôs 24 correções, a maioria falsa** (ex.: "vias"→"veias",
"direitos"→"direita"). As regras foram endurecidas:

- variantes de flexão são ignoradas;
- o termo do slide precisa estar (quase) ausente da fala;
- a semelhança mínima passou a 0,72;
- é preciso ter ao menos 2 ocorrências em contexto.

Depois disso restaram 2 correções automáticas plausíveis ("hidropsia"→"hidropisia",
"porto-sistêmico"→"portosistêmico") e 13 itens enviados para conferência ("sítios/situs", "destroposição",
"destrocardia", nome da professora escrito com outra letra, grafia de um epônimo no slide…).

## Limitações (declaradas expressamente)

1. **Qualidade com o Qwen não medida.** O Hugging Face está bloqueado neste ambiente. Os modelos Qwen3-30B-A3B
   e Qwen3-VL-8B/4B não puderam ser baixados. Os tamanhos e SHA-256 foram conferidos na API pública, e o
   download será verificado no seu computador. A redação real, a leitura visual dos slides e a remoção de
   frases sem suporte com o Qwen só serão avaliadas no primeiro uso real.
2. **Sem GPU.** O uso efetivo de CUDA/Vulkan não foi medido. O programa só mostra "GPU" quando o llama.cpp
   confirma camadas na GPU.
3. **Sem Windows real.** A interface gráfica foi validada no Linux, em modo sem tela; capturas estão em
   `testes/`. No Wine só a parte de linha de comando foi validada. Falta conferir no seu Windows a
   aparência, o arrastar e soltar e a janela de download.
4. **DOCX no Word.** Validado com python-docx. Não foi aberto no Microsoft Word. O sumário é um campo que o
   Word atualiza ao abrir (ou com F9).
5. **Transcrições reais.** As TXT do Módulo 2 Dia 1 não foram recebidas. O teste de fidelidade com a fala
   real fica pendente.
6. O `--list-devices` do llama.cpp não responde no Wine (sem driver Vulkan). O programa espera no máximo
   30 s por backend e segue com a CPU.
