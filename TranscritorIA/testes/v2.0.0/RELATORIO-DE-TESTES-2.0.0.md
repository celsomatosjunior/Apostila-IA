# Relatório de testes — Transcritor IA Local 2.0.0

Data: 18/10/2026. Regra seguida: só consta como aprovado o que foi executado. As evidências brutas
estão em `docs/testes-2.0.0/`.

## Resumo

| Bloco | Resultado |
|---|---|
| Testes automatizados (pytest, Linux) | **47 de 47 aprovados**: 25 de regressão da 1.0, sem alteração, e 22 novos da 2.0 (`pytest-47-testes.log`) |
| Pipeline 2.0 executado com os binários Windows do instalador (Python embutido, PyAV, FFprobe.exe, FFmpeg.exe, ONNX Runtime) no Wine 9 | 15 arquivos: 13 transcritos com texto completo, 2 recusados corretamente (`pipeline-windows-wine.json`) |
| Instalação limpa, atualização sobre a 1.0.0 e desinstalação (Wine 9) | aprovado (`wine-instalacao-atualizacao-desinstalacao.txt`) |
| Interface gráfica | validada no Linux (Qt offscreen, 2 testes). **Não** foi validada no Wine, pela limitação explicada ao final |
| Transcrição com o modelo Whisper real e GPU | **não executada** neste ambiente (sem GPU e sem acesso ao download dos modelos) |

Como a precisão do texto foi medida: os vídeos de teste são reais (codificados pelo FFmpeg) e levam o áudio
de uma aula sintética em português com terminologia obstétrica. Cada palavra dessa aula tem posição
conhecida. Um motor simulado devolve exatamente as palavras inteiras dentro de cada bloco. Assim, qualquer
perda, duplicação ou troca de ordem na leitura, na divisão ou na junção aparece como erro de palavras (WER).
Isso mede a infraestrutura nova. A precisão do Whisper não muda na 2.0, porque o motor é o mesmo da 1.0.

## Os 14 itens exigidos

| # | Item | Teste | Resultado |
|---|---|---|---|
| 1 | MP3 normal | `test_end_to_end_lecture_text_complete_and_ordered` + Wine | aprovado, WER 0 |
| 2 | MP4 com áudio AAC | `test_video_containers…[.mp4]` + Wine | aprovado, WER 0 |
| 3 | MKV com áudio compatível (AC3) | `…[.mkv]` + Wine | aprovado, WER 0 |
| 4 | AVI com áudio (MP3) | `…[.avi]` + Wine | aprovado, WER 0 |
| 5 | MOV com áudio (AAC) | `…[.mov]` + Wine | aprovado, WER 0 |
| — | Também testados: WMV (WMA2), WEBM (Opus), MPG e MPEG (MP2), M4V (AAC), FLV (AAC) | `…[ext]` + Wine | aprovados, WER 0 |
| 6 | Vídeo sem trilha de áudio | `test_video_without_audio_track`, `test_gui_accepts…` | erro claro ("sem trilha de áudio"), fila continua; na interface o arquivo não entra na fila e aparece um aviso |
| 7 | Vídeo com múltiplas trilhas | `test_multiple_tracks_prefers_portuguese`, `…without_language…manual_choice_works` | com trilhas em inglês, português e espanhol, escolheu o português (WER 0). Sem idioma marcado, escolheu a padrão, avisou e a troca manual funcionou |
| 8 | Vídeo com mais de 2 horas | `test_video_longer_than_two_hours` (MP4 de **150 min**, 126 MB) | aprovado: 17.768 palavras, WER < 0,5 %, nenhum temporário grande, original intacto |
| 9 | Fila com MP3 e MP4 juntos | `test_mixed_queue_mp3_and_mp4_with_accented_names` + Wine | aprovado; saídas distintas para nomes iguais |
| 10 | Nomes acentuados | mesmo teste ("Aula de Cardiologia — Pré-eclâmpsia e síndrome HELLP (revisão nº 2)", pastas "Obstetrícia — 2º semestre", "Transcrições ç") + Wine | aprovado |
| 11 | Interrupção e retomada de vídeo | `test_video_interrupt_and_resume` | aprovado. Após uma queda, a retomada não reprocessou nenhum bloco já salvo. Após um cancelamento, nenhum TXT parcial ficou salvo e a retomada concluiu |
| 12 | Arquivos corrompidos ou incompletos | `test_corrupted_and_incomplete_videos` + Wine | MKV cortado em 60 %: transcreveu a parte legível (3 min 3 s de 5 min 7 s) e avisou. MKV com 40 trechos zerados: concluído. Lixo, arquivo vazio e MP4 sem índice: erro claro, sem travar |
| 13 | Funcionamento offline | `test_video_offline` (qualquer tentativa de conexão de rede falha o teste) | aprovado: nenhuma conexão |
| 14 | Reconstrução sem duplicação ou perda | WER em todos os testes acima, mais os testes da 1.0 de sobreposição | aprovado |
| — | Originais intactos | SHA-256 antes e depois em todos os testes de vídeo e nos 15 arquivos do Wine | aprovado |
| — | FFmpeg e FFprobe no pacote | `--diagnostico` no Windows/Wine; `test_ffprobe_used_and_ffmpeg_fallback` | presentes em `engines\ffmpeg`. A análise usou o FFprobe em todos os arquivos. A leitura alternativa pelo ffmpeg.exe deu o mesmo áudio (correlação 1,0) |
| — | Licenças | `ffmpeg -L` | LGPL 2.1+, compilado com `--disable-gpl --disable-nonfree`, nenhum decodificador de vídeo; licença, opções e código-fonte guardados |

## Desempenho da leitura de vídeo

Na mesma aula de 150 min, a leitura do áudio levou **22,1 s no MP4 (AAC 44,1 kHz)** e **10,2 s no MP3**
(CPU de 2 núcleos). A diferença vem da decodificação do AAC, não da imagem, que não é decodificada.
Num computador de 8 núcleos e numa aula de 2 h, é esperado menos de 10 s, contra vários minutos de
transcrição na GPU. Na prática, a transcrição de um MP4 leva o mesmo tempo que a do áudio equivalente.

O pico de memória na leitura é de cerca de 1,5 vez o áudio em 16 kHz, cerca de 700 MB numa aula de 3 h.
Nenhum arquivo temporário é criado, porque a leitura vai direto para a memória.

## Instalação, atualização e desinstalação (Wine 9, instalador final)

SHA-256 `0d6fee66fde84dfbf4a69bf652a85c0d217489e342e4c464445268cbe9855358`

1. Instalação da 1.0.0 e criação de dados de usuário típicos: configuração, glossário editado, calibração,
   modelo baixado, biblioteca CUDA e um trabalho interrompido.
2. Instalação da 2.0.0 por cima. Versão no registro: 2.0.0. A pasta do programa ficou idêntica ao pacote
   2.0, com 3.550 arquivos, inclusive `engines\ffmpeg`. **Os 7 arquivos do usuário ficaram idênticos,
   conferidos por SHA-256.**
3. Diagnóstico do executável instalado: FFprobe, FFmpeg, leitura de áudio, detector de voz e os dois motores
   whisper.cpp encontrados.
4. Desinstalação: pasta, atalhos e registro removidos; os dados do usuário foram mantidos de propósito.

## Limitações conhecidas (não validadas)

- **Interface no Wine**: o Qt 6.12 precisa da biblioteca ICU que o Windows 10/11 traz (`icuuc.dll`) e que o
  Wine não tem. Por isso a janela foi validada no Linux, não no Wine. É o mesmo Qt do Capture Pro 2.0,
  que funciona no Windows real. **Não declaramos validação completa da interface no Windows.**
- No teste do Wine foi usado um substituto, só para o Wine, da função `crealf` (ausente no Wine 9 e usada
  pelo NumPy). Esse substituto não vai no instalador.
- **Transcrição real com Whisper e GPU** (RTX 3070, 4090M, 5070 Ti, Radeon): não executada aqui. A 2.0 não
  mudou os motores. O roteiro de aceitação no computador real está em `docs/VALIDACAO.md`.
