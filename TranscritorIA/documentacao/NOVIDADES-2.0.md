# Transcritor IA Local — o que mudou na 2.0.0

## Novo
- **Videoaulas**: MP4, MKV, AVI, MOV, WMV, WEBM, MPEG/MPG, M4V, FLV (e TS, MTS, 3GP, VOB, OGV, ASF).
- Novo módulo `transcritor/media.py`: análise do contêiner e das trilhas com **FFprobe**, escolha automática da
  trilha (português → padrão → mais canais), leitura **somente do áudio** em streaming para um buffer
  pré-alocado; os quadros de vídeo nunca são decodificados e nada é gravado em disco.
- Leitura alternativa pelo **ffmpeg.exe** (tolerante a trechos danificados), também por pipe, sem temporários.
- **FFmpeg 7.1.1 e FFprobe** incluídos em `engines\ffmpeg` (compilação mínima LGPL, sem GPL/nonfree e sem
  nenhum decodificador de vídeo), com licença, opções de compilação e código-fonte guardados.
- Interface: botão **Adicionar áudio ou vídeo**, etiqueta Áudio/Vídeo, tempo restante por aula, seletor de
  trilha (só aparece em vídeos com várias trilhas), aviso para vídeos sem áudio ou ilegíveis.
- Linha de comando: `--analisar ARQUIVO` (contêiner e trilhas) e `--trilha N`; acentos corretos no Prompt.
- Arquivos incompletos: transcreve a parte legível e informa quanto foi lido.

## Preservado da 1.0
Detecção de hardware, CUDA, Vulkan, CPU, seleção de modelo, segmentação, lotes, VAD, português, glossário
médico, reconstrução, fila, progresso, pausa/retomada/cancelamento, checkpoints, offline, TXT/SRT/TXT com tempos.
Os 25 testes automatizados da 1.0 continuam passando sem alteração.

## Atualização a partir da 1.0
O instalador 2.0 instala por cima da 1.0. Configurações, modelos baixados, bibliotecas CUDA, glossário,
calibração e trabalhos interrompidos ficam em `%LOCALAPPDATA%\TranscritorIA` e são mantidos (validado no Wine).
A calibração da 1.0 continua válida (os motores não mudaram). Checkpoints de aulas em MP3 da 1.0 continuam
reconhecidos (a identificação de cada trabalho só muda para trilhas de áudio diferentes da primeira).
