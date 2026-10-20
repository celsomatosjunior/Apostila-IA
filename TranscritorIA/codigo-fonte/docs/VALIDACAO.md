# Estado da validação

## Versão 2.0.0 (vídeos)

Detalhes completos em [`RELATORIO-DE-TESTES-2.0.0.md`](RELATORIO-DE-TESTES-2.0.0.md).
Resumo: 47/47 testes automatizados (25 da 1.0 + 22 da 2.0); pipeline de vídeo executado com os binários
Windows do instalador no Wine (13 arquivos transcritos sem perda, 2 recusados corretamente, originais
intactos); instalação, atualização sobre a 1.0 preservando os dados do usuário e desinstalação aprovadas no
Wine. Interface gráfica validada no Linux, não no Wine. Transcrição com Whisper real e GPU não executada aqui.

**Roteiro de aceitação da 2.0 no seu computador (5 minutos, depois do roteiro da 1.0 abaixo):**
1. Instale a 2.0 por cima da 1.0 e confirme que não pediu novo download do modelo.
2. Arraste juntos um MP3 e um MP4 de aula; a lista deve mostrar "Áudio" e "Vídeo".
3. Transcreva; o TXT do vídeo deve ter o mesmo nome do MP4.
4. Se tiver um vídeo com várias trilhas (ex.: dublado), confira a trilha escolhida no seletor da linha.

---

# Versão 1.0.0

Regra seguida: nada é declarado como funcionando sem ter sido executado. Abaixo, o que foi
**medido**, onde, e o que **ainda depende de teste físico** nos seus computadores.

## 1. Validado no ambiente de desenvolvimento (Linux, 2 núcleos, sem GPU)

25 testes automatizados (`python -m pytest tests`), todos aprovados, com áudio MP3 real
(voz sintética em português com terminologia obstétrica), detector de voz real (Silero) e um
**motor de transcrição simulado** que devolve exatamente as palavras faladas em cada bloco —
isolando a infraestrutura da precisão do modelo:

| Requisito da especificação | Teste | Resultado |
|---|---|---|
| Divisão sem ultrapassar a janela do Whisper e cobrindo toda a fala | `test_chunks_respect_whisper_window_and_cover_speech` | aprovado |
| Sobreposição sem perder nem duplicar palavras (fala contínua de 150 s) | `test_overlap_merge_loses_and_duplicates_nothing` | aprovado, 0 diferenças |
| Aula completa, em ordem | `test_end_to_end_lecture_text_complete_and_ordered` | aprovado |
| Silêncio prolongado (75 s) + ruído de fundo | `test_noise_and_long_silence` | aprovado |
| Nomes iguais e caracteres especiais (acentos, —, &, :, ?) | `test_multiple_files_same_name_and_special_chars`, `test_unique_names...` | aprovado |
| Arquivo corrompido não interrompe a fila | `test_bad_file_does_not_stop_queue` | aprovado |
| Queda no meio → retomada sem reprocessar o que foi salvo | `test_crash_and_resume_from_checkpoint` | aprovado |
| Checkpoint corrompido é descartado e refeito | `test_corrupted_checkpoint_is_discarded` | aprovado |
| Cancelar e retomar; nunca salvar texto incompleto | `test_cancel_then_resume` | aprovado |
| Pausar/continuar | `test_pause_and_continue` | aprovado |
| Falta de memória de vídeo → lote reduzido automaticamente | `test_gpu_out_of_memory_reduces_batch` | aprovado |
| Falha de GPU → continua na CPU e **não** exibe GPU | `test_gpu_failure_falls_back_to_cpu` | aprovado |
| RAM insuficiente → erro claro, sem travar | `test_insufficient_ram_reports_error` | aprovado |
| Interface: fila completa em segundo plano, faixa da aula, mensagem final | `test_gui_full_queue` | aprovado |

Teste de escala (`tools/teste_duracoes.py`, motor simulado, MP3 real decodificado + VAD real):

| Duração | Palavras | Diferenças na reconstrução | Tempo da infraestrutura | RAM do processo |
|---|---|---|---|---|
| 5 min | 617 | 0 | 0,9 s | 144 MB |
| 30 min | 3.562 | 0 | 5,4 s | 213 MB |
| 60 min | 7.127 | 0 | 10,7 s | 234 MB |
| 120 min | 14.228 | 0 | 22,8 s | 364 MB |
| 150 min | 17.768 | 0 | 25,7 s | 422 MB |

Este teste revelou um defeito real (uma palavra duplicada na fronteira de dois blocos, em 60 min),
corrigido antes da entrega.

Outros itens verificados:
- **Privacidade**: o ONNX Runtime 1.29 tenta enviar telemetria à Microsoft por padrão. Isso foi
  detectado (rastreamento de conexões) e desativado; após a correção, 0 conexões de rede durante o uso.
- **Executável**: o pacote PyInstaller foi gerado e iniciado (interface e linha de comando) no Linux; o
  diagnóstico interno do executável (leitura de MP3, detecção de voz, CTranslate2) passou.
- **Motor whisper.cpp**: compilado da versão v1.9.5 e executado pelo módulo do programa com vários blocos
  numa só chamada; argumentos aceitos, saídas JSON geradas e lidas, e a detecção de backend reconheceu
  corretamente que não havia GPU (não afirmou Vulkan).
- Sem internet: o motor roda com `HF_HUB_OFFLINE=1`; só a tela de preparação inicial acessa a rede.

## 2. Instalador Windows gerado e testado no Wine 9 (simulação do Windows)

Mesmo método do Capture Pro. Resultados com o instalador final `TranscritorIA-Setup-1.0.0.exe`:

| Verificação | Resultado |
|---|---|
| Todas as DLLs exigidas pelos 3.500 arquivos do pacote presentes (cabeçalhos PE) | aprovado |
| Instalação silenciosa: 3.542 arquivos idênticos ao pacote, atalhos no Menu Iniciar, registro de desinstalação | aprovado |
| Desinstalação: pasta e registro removidos | aprovado |
| `TranscritorIA-cli.exe --diagnostico`: lançador → Python embutido → CTranslate2, PyAV (leitura de MP3), ONNX Runtime (detector de voz), localização dos dois motores whisper.cpp | aprovado (4,7 s) |
| whisper.cpp CPU e Vulkan (compilados para Windows) processando vários blocos e gravando JSON | aprovado |
| Motor Vulkan sem placa compatível: informa "No devices found" e o programa **não** declara GPU | aprovado |
| Mensagem de erro amigável quando a inicialização falha | aprovado |

Limitações do Wine (não do Windows), documentadas para não confundir:
- o Wine 9 não implementa a função `crealf` da UCRT, usada pelo NumPy 2.5; no teste foi usada uma cópia
  com um substituto apenas para o Wine (não distribuído);
- o Wine não tem a biblioteca ICU do Windows (`icuuc.dll`, presente no Windows 10/11), exigida pelo Qt 6.12;
  por isso a janela gráfica foi validada no Linux, não no Wine. O Capture Pro 2.0 usa o mesmo Qt 6.12 e
  funciona no Windows real.

## 2b. Validação automática no GitHub Actions (opcional)

O workflow roda os 25 testes no Windows, compila o whisper.cpp (Vulkan e CPU), gera o `.exe` e então,
**com o executável final**, transcreve de verdade a aula de 5 min com o Whisper Small:
1. pelo CTranslate2 (CPU, INT8);
2. pelo whisper.cpp (CPU) — valida a integração com o motor usado nas placas AMD;
3. o autoteste com o áudio de referência.
O resumo (WER, tempo, acelerador relatado) aparece na página da execução. A compilação é reprovada
se o texto vier vazio ou com erro de palavras acima de 60 %.

## 3. Ainda NÃO validado fisicamente (depende dos seus computadores)

Os servidores do GitHub não têm placa de vídeo, e o ambiente de desenvolvimento não tinha acesso
ao download dos modelos. Portanto:

| Configuração | Situação |
|---|---|
| NVIDIA RTX 3070 / 4090M / 5070 Ti com CUDA | código pronto, **não testado em placa real**. A calibração do 1º uso comprova (ou reprova) automaticamente. Para a 5070 Ti (Blackwell) a compatibilidade dos kernels do CTranslate2 4.8.3 é a maior incógnita — se falhar, o programa cai para Vulkan e depois para CPU, e mostra o motivo. |
| AMD Radeon RX 9070 XT com Vulkan | código pronto, **não testado em placa real**. Exige driver Adrenalin recente. |
| Intel Arc / iGPU com Vulkan | idem. |
| Velocidade real e precisão (WER) em aulas gravadas de verdade | não medidas; não há números inventados. Use **Configurações → Teste de desempenho completo** para medir no seu PC. |

### Roteiro de aceitação sugerido (10 minutos por computador)
1. Abrir o programa; conferir no painel o nome real da GPU e da CPU.
2. Transcrever uma aula curta real (5–10 min). Na primeira vez, autorizar o download e aguardar a calibração.
3. Conferir no painel **Aceleração: CUDA** (NVIDIA) ou **Vulkan** (AMD). Se aparecer CPU, o aviso
   em destaque na janela explica o motivo; envie o arquivo de log (Configurações → Abrir pasta de dados → logs).
4. Rodar o Teste de desempenho completo e guardar o relatório.
5. Fechar o programa no meio de uma aula longa, reabrir e confirmar que ele retoma.
