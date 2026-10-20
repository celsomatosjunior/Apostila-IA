# Transcritor IA Local 2.0

Programa para Windows 10/11 que transcreve gravações de aulas — **em áudio ou em vídeo** — para texto,
**100% no próprio computador**, com o Whisper Large-v3. Nenhum áudio, texto ou dado é enviado à internet.

## Como usar

1. Abra o **TranscritorIA.exe** (duplo clique).
2. Arraste as aulas para a janela, ou clique em **Adicionar áudio ou vídeo** (aceita pastas inteiras
   e filas que misturam MP3 e MP4).
3. Clique em **Escolher pasta de destino**.
4. Clique em **Iniciar transcrição** e deixe o computador trabalhar.

Na primeira vez, o programa mostra o que precisa baixar (modelo de IA e, em placas NVIDIA, as
bibliotecas CUDA) e só baixa com a sua autorização. Depois disso funciona sem internet.
Também na primeira vez ele faz uma **calibração** de 1–3 minutos: transcreve um áudio de
referência para confirmar que a placa de vídeo realmente funciona e medir o melhor tamanho de lote.

Cada aula vira um `.txt` com o mesmo nome-base do arquivo (`Aula de Cardiologia.mp4` → `Aula de Cardiologia.txt`):

```
AULA: FISIOLOGIA CARDIOVASCULAR

Duração original: 02:15:30

TRANSCRIÇÃO

Bom dia, pessoal. Hoje vamos estudar ...
```

Opcional (em Configurações): legenda `.srt` e um `.txt` com marcações de tempo por parágrafo.

### Videoaulas (novo na 2.0)

Formatos: MP4, MKV, AVI, MOV, WMV, WEBM, MPEG/MPG, M4V, FLV (e TS, 3GP, VOB…). Áudio: MP3, WAV, M4A, AAC,
FLAC, OGG, WMA, OPUS e outros.

- O vídeo é tratado **somente como fonte de áudio**: o programa identifica o contêiner e as trilhas
  (FFprobe), lê apenas a trilha de áudio escolhida em streaming direto para a memória e nunca decodifica
  os quadros de imagem — nada de conversão do vídeo, arquivos temporários grandes ou VRAM gasta com imagem.
  A GPU fica inteira para o Whisper.
- O arquivo original é aberto só para leitura e não é alterado.
- Várias trilhas de áudio: escolhe automaticamente a marcada como português. Quando nenhuma está
  identificada, escolhe a trilha padrão e mostra, na própria linha da aula, um seletor para trocar.
- Vídeo sem trilha de áudio, danificado ou incompleto: aviso claro na lista; a fila continua. Em arquivos
  incompletos, transcreve a parte legível e informa quanto foi lido.
- Depois da leitura, o vídeo segue exatamente o caminho dos MP3: mesma segmentação, GPU, lotes,
  checkpoints, retomada e reconstrução do texto.

A lista mostra, para cada aula: tipo (Áudio/Vídeo), duração, estado, percentual e tempo restante.

### Perfis de uso

- **Turbo** — usa todos os recursos para terminar o mais rápido possível.
- **Trabalho** — metade do lote na GPU, metade dos núcleos na CPU e prioridade reduzida, para você
  continuar usando o computador. Pode ser trocado durante a transcrição.

### Pausar, cancelar e quedas de energia

O progresso é salvo a cada parte de ~3 minutos de áudio. Se o computador desligar, o programa
fechar ou você cancelar, ao abrir de novo ele oferece **retomar de onde parou**, sem refazer o
que já foi transcrito. Um texto só aparece na pasta de destino quando está completo.

### Glossário médico

Em Configurações → **Editar glossário**, mantenha um termo por linha (os do topo têm prioridade).
O Whisper usa essa lista apenas para grafar corretamente termos que ouviu — não acrescenta conteúdo.
Se notar termos do glossário aparecendo onde não foram ditos, desative a opção.

## Como o programa decide o hardware

| Placa | Mecanismo tentado primeiro | Plano B automático |
|---|---|---|
| NVIDIA (RTX 3070, 4090M, 5070 Ti…) | CTranslate2 + CUDA, FP16, em lote | whisper.cpp + Vulkan → CPU |
| AMD Radeon (RX 9070 XT…) | whisper.cpp + Vulkan | whisper.cpp na CPU |
| Intel Arc / só GPU integrada | whisper.cpp + Vulkan | CPU |
| Sem GPU utilizável | CTranslate2 na CPU, INT8 | — |

Nenhum mecanismo é usado sem antes passar por um teste real. O painel mostra o acelerador
**efetivamente em uso**; se a GPU falhar no meio do trabalho, o programa avisa e continua na CPU.
Trocar de computador ou conectar uma eGPU dispara nova calibração automaticamente.

Modelo automático: Large-v3 em placas com 6 GB ou mais de VRAM; Large-v3 Turbo com menos VRAM ou só CPU.
Pode ser trocado em Configurações.

## Onde ficam os arquivos

| O quê | Instalado | Portátil |
|---|---|---|
| Programa | `C:\Program Files\TranscritorIA` | pasta do .zip |
| Modelos, bibliotecas CUDA, configurações, temporários, logs | `%LOCALAPPDATA%\TranscritorIA` | `dados\` ao lado do programa |

Espaço: programa ~0,3 GB; Large-v3 ~3 GB; bibliotecas NVIDIA ~2,5 GB extraídas.

## Linha de comando (opcional)

`TranscritorIA-cli.exe` serve para automação e diagnóstico:

```
TranscritorIA-cli.exe --diagnostico
TranscritorIA-cli.exe --cli "D:\Aulas" --saida "D:\Textos" --baixar
TranscritorIA-cli.exe --desempenho        (compara sequencial, lotes e instâncias paralelas)
TranscritorIA-cli.exe --autoteste         (transcreve o áudio de referência e mede o erro)
```

## Compilar

**Método principal (o mesmo do Capture Pro):** `./build/windows/build.sh`, num Linux Ubuntu 24.04.
Monta Python 3.12 embutido para Windows, compila os lançadores nativos `TranscritorIA.exe` e
`TranscritorIA-cli.exe` (C/MinGW), faz a compilação cruzada do whisper.cpp (CPU e Vulkan), verifica
todas as DLLs pelos cabeçalhos PE, pré-compila o bytecode com o próprio Python do Windows (Wine) e gera
o instalador NSIS `dist/TranscritorIA-Setup-<versão>.exe` com o SHA-256.

Alternativa em Windows: `build\build_windows.ps1` (PyInstaller) ou o workflow do GitHub Actions
em `.github/workflows/build-windows.yml`, que também transcreve uma aula de teste com o executável pronto.

Estado da validação em hardware real: veja `docs/VALIDACAO.md`.
