# Apostila IA — da aula gravada à apostila de estudo, com IA 100% local

Conjunto de dois programas Windows (10/11, 64 bits), desenvolvidos para uso pessoal, que transformam aulas
gravadas de pós-graduação médica em material de estudo. **Tudo acontece no computador do usuário.**
Não há envio de áudio, vídeo, transcrição, PDF ou apostila para servidores externos. Não há login,
assinatura, API paga ou telemetria. A internet só é usada uma vez, com autorização, para baixar os modelos de IA.

```
 Aula gravada (MP3, MP4…)          TXT fiel da fala              Apostila_Final.pdf
 ───────────────────────►  TranscritorIA  ──────────►  ApostilaIA  ──────────►  Apostila_Final.docx
                            (Whisper)          ▲       (llama.cpp + Qwen)       Relatorio_de_Fidelidade.pdf
                                               │
                                  PDFs dos slides da aula
```

| Programa | O que faz | Versão | Instalador |
|---|---|---|---|
| **TranscritorIA** (Transcritor IA Local) | Transcreve aulas em **áudio ou vídeo** para TXT fiel, em português, com Whisper local (GPU NVIDIA/AMD/Intel ou CPU) | **2.0.0** | [`TranscritorIA/instaladores/v2.0.0/`](TranscritorIA/instaladores/v2.0.0/) |
| **ApostilaIA** | Junta a transcrição (TXT) e os PDFs dos slides e gera uma **apostila de estudo** fiel, organizada e diagramada | **1.0.0** | [`ApostilaIA/instaladores/v1.0.0/`](ApostilaIA/instaladores/v1.0.0/) |

---

## 1. TranscritorIA — geração do texto

Transcreve gravações de aulas com **faster-whisper** (CTranslate2/CUDA) ou **whisper.cpp** (Vulkan),
com fallback automático para CPU.

- **Entradas:** MP3, M4A, WAV, OGG, FLAC, AAC, WMA e vídeos (MP4, MKV, AVI, MOV, WMV, WEBM, MPG, M4V e FLV).
  Do vídeo, só o áudio é lido, com FFmpeg LGPL embutido e escolha automática da trilha em português.
- **Saída:** um TXT por aula com o mesmo nome do arquivo. O formato traz cabeçalho `AULA:`, duração e
  parágrafos. SRT e TXT com marcações de tempo são opcionais.
- **Hardware e retomada:** detecta o hardware, calibra o desempenho e tem os modos Turbo e Trabalho.
  Trabalhos interrompidos são retomados, com fila e checkpoints por grupo de blocos.
- **Termos técnicos:** um glossário médico orienta a grafia; trechos incertos são marcados.
- **Instalação:** a NVIDIA baixa o modelo Whisper e as bibliotecas CUDA na primeira execução, com consentimento.

Detalhes: [`TranscritorIA/LEIA-ME.md`](TranscritorIA/LEIA-ME.md) ·
[manual](TranscritorIA/documentacao/MANUAL-COMPLETO.md) ·
[testes 2.0.0](TranscritorIA/testes/v2.0.0/RELATORIO-DE-TESTES-2.0.0.md)

## 2. ApostilaIA — geração das apostilas

Transforma a **transcrição integral** (TXT do TranscritorIA; várias partes são aceitas) e os **PDFs dos slides**
em uma apostila de estudo completa:

1. **Leitura completa dos PDFs** com PyMuPDF: texto, títulos, tabelas, imagens, referências bibliográficas,
   professor(a) e curso da capa. Cada página é renderizada e lida por um **modelo de visão local**
   (Qwen3-VL), porque slides de medicina costumam ser imagens: ultrassonografias, esquemas e slides "achatados".
2. **Segmentação semântica** da fala em trechos de cerca de 1.800 tokens, cortados nas mudanças de assunto.
   Aulas de 5 horas ou mais são aceitas.
3. **Cruzamento fala × slides** por busca semântica local: TF-IDF, n-gramas e um alinhamento que não depende
   só da ordem das páginas. **Nenhuma associação é forçada** quando há incerteza.
4. **Terminologia:** um erro de transcrição só é corrigido quando a forma certa está impressa no slide.
   Exemplo: "sítios solitus" vira "situs solitus". O resto vai para uma lista "a conferir".
5. **Representação intermediária:** notas fiéis de cada trecho, guardando o parágrafo de origem.
   Os tipos são conceito, observação, dica clínica, alerta, exemplo, passo a passo e dado numérico.
6. **Plano de capítulos** e **redação capítulo a capítulo** em três perfis: Compacta, **Equilibrada** (padrão)
   e Fiel e detalhada.
7. **Auditoria de fidelidade** com 10 verificações:
   - frases sem sustentação nas fontes são verificadas pelo modelo e **removidas**;
   - números sem fonte são sinalizados;
   - divergências numéricas entre fala e slide são registradas, **sem escolher um valor**;
   - duplicatas são eliminadas;
   - esquemas inventados são descartados;
   - observações essenciais esquecidas são reinseridas.
8. **Composição:**
   - **PDF** com Typst, fontes IBM Plex embutidas, capa, sumário navegável, cabeçalhos, tabelas e
     figuras dos slides.
   - Quadros de destaque: *Observação da professora*, *Dica clínica*, *Ponto de atenção*,
     *Exemplo discutido* e *Passo a passo*.
   - **DOCX** editável no Word.
   - **Relatório de fidelidade** separado, com omissões, ambiguidades, divergências e o mapa
     capítulo → parágrafos da fala → slides.

Cada leitura de slide, cada trecho e cada capítulo têm checkpoint próprio. O trabalho pode ser pausado,
cancelado, fechado ou interrompido por falta de energia e continua de onde parou. Há modos **Turbo** e
**Trabalho**. RAM e VRAM são monitoradas, com pausa automática quando a memória fica crítica. Apenas um
modelo grande fica carregado por vez.

**Modelos locais** (escolha automática pelo hardware; download único com SHA-256 conferido):

| Conjunto | Para | Texto | Visão | Download |
|---|---|---|---|---|
| A — Qualidade máxima | RAM ≥ 28 GB (ex.: i7-10700 + 32 GB + RTX 3070) | Qwen3-30B-A3B-Instruct-2507 (MoE) | Qwen3-VL-8B | ~22 GB |
| B — Econômico | RAM ≥ 14 GB ou GPU ≥ 8 GB | Qwen3-VL-8B | Qwen3-VL-8B | ~5,4 GB |
| C — Leve | demais | Qwen3-VL-4B | Qwen3-VL-4B | ~2,7 GB |

Motor de inferência: **llama.cpp b11435**. A GPU é usada via Vulkan (NVIDIA, AMD Radeon, Intel Arc) já
incluído no instalador, ou via CUDA 12.4/13.4 baixado sob consentimento. A interface só mostra "GPU" quando o
próprio motor confirma camadas carregadas nela.

Detalhes: [`ApostilaIA/LEIA-ME.md`](ApostilaIA/LEIA-ME.md) ·
[arquitetura](ApostilaIA/documentacao/ARQUITETURA.md) ·
[testes 1.0.0](ApostilaIA/documentacao/RELATORIO_DE_TESTES.md) ·
[exemplo gerado (dados sintéticos)](ApostilaIA/testes/v1.0.0/exemplo-sintetico/)

---

## Instalação (usuário)

1. Instale `TranscritorIA-Setup-2.0.0.exe` e `ApostilaIA-Setup-1.0.0.exe`, com dois cliques em cada.
   Os instaladores não são assinados: no aviso do Windows, clique em *Mais informações* → *Executar assim mesmo*.
2. No TranscritorIA, arraste as aulas, escolha a pasta e clique em **Iniciar transcrição**.
3. No ApostilaIA:
   - clique em **Adicionar transcrição** e escolha os TXT;
   - clique em **Adicionar PDFs da aula** e escolha os slides;
   - escolha a pasta e a extensão;
   - clique em **Gerar apostila**.

Na primeira vez, cada programa pede autorização para baixar os modelos de IA. Depois, tudo funciona offline.
Os checksums SHA-256 estão ao lado de cada instalador. No Windows, confira com
`certutil -hashfile <arquivo> SHA256`.

## Organização deste repositório

```
README.md                  esta descrição
ANOTACOES.md               anotações do projeto: histórico, decisões, aprendizados, pendências
INDICE.md                  versões, instaladores, SHA-256 e como recuperar cada coisa
TranscritorIA/
  codigo-fonte/            projeto completo e compilável (2.0.0)
  documentacao/            instalação, manual, novidades, validação, licenças
  instaladores/v1.0.0/     TranscritorIA-Setup-1.0.0.exe + SHA-256
  instaladores/v2.0.0/     TranscritorIA-Setup-2.0.0.exe + SHA-256
  testes/v2.0.0/           relatório e evidências dos testes
  scripts-compilacao/      como compilar
ApostilaIA/
  codigo-fonte/            projeto completo e compilável (1.0.0)
  documentacao/            arquitetura, instalação, reconstrução, licenças, testes
  instaladores/v1.0.0/     ApostilaIA-Setup-1.0.0.exe + SHA-256
  testes/v1.0.0/           relatório, saídas dos testes, exemplo sintético, telas
  scripts-compilacao/      lançador C, montagem, NSIS, teste no Wine
  configuracoes/           configuração padrão e catálogo de modelos (SHA-256)
backups/
  TranscritorIA/v1.0.0/, v2.0.0/   ZIP do código, instalador, SHA-256, instruções
  ApostilaIA/v1.0.0/               ZIP do código, instalador, scripts, versões fixadas, SHA-256
```

## Como compilar

Os dois programas usam o mesmo método, herdado do Capture Pro e executado a partir do Linux:

- Python 3.12 embutido (python-build-standalone);
- lançador nativo em C compilado com MinGW;
- dependências como wheels `win_amd64` com versões fixadas;
- instalador **NSIS** em português.

- TranscritorIA: `TranscritorIA/codigo-fonte/build/windows/build.sh` (ver
  [`TranscritorIA/scripts-compilacao/LEIA-ME.md`](TranscritorIA/scripts-compilacao/LEIA-ME.md))
- ApostilaIA: `ApostilaIA/codigo-fonte/build/windows/build.sh` (ver
  [`ApostilaIA/documentacao/RECONSTRUIR.md`](ApostilaIA/documentacao/RECONSTRUIR.md))

## Privacidade e regras do repositório

- Nenhum documento, áudio ou PDF de aula real está neste repositório. Os testes e exemplos usam **dados sintéticos**.
- Nunca versionar senhas, tokens, certificados, dados ou imagens de pacientes, nem material didático de terceiros.
- Nunca apagar versões nem backups. Cada versão nova ganha pasta própria em `instaladores/` e `backups/`.
- Licenças de terceiros: [TranscritorIA](TranscritorIA/documentacao/LICENCAS_TERCEIROS.md) ·
  [ApostilaIA](ApostilaIA/documentacao/LICENCAS_TERCEIROS.md).

Autor: Celso Matos Junior.
