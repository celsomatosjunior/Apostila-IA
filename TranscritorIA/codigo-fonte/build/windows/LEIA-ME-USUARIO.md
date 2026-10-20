# Transcritor IA Local 2.0.0

Transcreve gravações de aulas — em áudio ou em vídeo — para texto, inteiramente neste computador.

1. Abra **TranscritorIA.exe**.
2. Arraste as aulas para a janela (ou use *Adicionar áudio ou vídeo*). Pode misturar MP3 e MP4 na mesma fila.
3. Escolha a pasta de destino e clique em **Iniciar transcrição**.

Cada aula vira um TXT com o mesmo nome do arquivo (ex.: `Aula de Cardiologia.mp4` → `Aula de Cardiologia.txt`).

**Vídeos** (MP4, MKV, AVI, MOV, WMV, WEBM, MPG, M4V, FLV): somente o áudio é lido; a imagem não é
processada e o arquivo original não é alterado. Se o vídeo tiver mais de uma trilha de áudio, o programa
escolhe a trilha em português; quando não consegue identificar, mostra na lista qual escolheu para você conferir.

Na primeira transcrição o programa pede autorização para baixar o modelo de IA (cerca de 3 GB) e, em
placas NVIDIA, as bibliotecas CUDA (cerca de 1,3 GB). Depois funciona sem internet. Quem já usava a 1.0
não baixa nada de novo: modelos, configurações, glossário e trabalhos interrompidos são mantidos.

Nenhum áudio, vídeo ou texto sai do computador.

Problemas: Configurações → Abrir pasta de dados → `logs\transcritor.log`.
Diagnóstico pelo Prompt de Comando: `TranscritorIA-cli.exe --diagnostico`
Ver as trilhas de um vídeo: `TranscritorIA-cli.exe --analisar "aula.mp4"`
