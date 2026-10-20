# Componentes de terceiros

| Componente | Uso | Licença | Distribuição |
|---|---|---|---|
| OpenAI Whisper (pesos dos modelos) | reconhecimento de fala | MIT | baixado no 1º uso (Hugging Face) |
| faster-whisper (SYSTRAN) | motor CTranslate2 | MIT | incluído |
| CTranslate2 (OpenNMT) | inferência CPU/CUDA | MIT | incluído |
| whisper.cpp / ggml | motor Vulkan e CPU | MIT | incluído (compilado do código-fonte) |
| Silero VAD | detecção de voz | MIT | incluído (via faster-whisper) |
| ONNX Runtime | executa o Silero VAD | MIT | incluído — telemetria desativada |
| PyAV / FFmpeg | leitura do áudio de arquivos de áudio e vídeo | BSD / LGPL 2.1+ | incluído (bibliotecas dinâmicas) |
| FFmpeg 7.1.1 — `ffmpeg.exe` e `ffprobe.exe` (2.0) | análise de contêiner/trilhas e leitura alternativa do áudio | LGPL 2.1+ (compilado com `--disable-gpl --disable-nonfree`) | incluído em `engines\ffmpeg`, com licença, opções de compilação e código-fonte (`ffmpeg-n7.1.1.tar.xz`) guardado junto aos scripts de compilação |
| Qt 6 / PySide6 | interface | LGPL 3 | incluído (bibliotecas dinâmicas, substituíveis) |
| NumPy, psutil, tokenizers, huggingface_hub | utilitários | BSD / Apache 2.0 | incluído |
| NVIDIA cuBLAS, cuDNN, NVRTC | aceleração CUDA | NVIDIA Software License | **não redistribuído**: baixado pelo próprio usuário, com consentimento, dos pacotes oficiais da NVIDIA no PyPI |

Bibliotecas LGPL são carregadas dinamicamente a partir da pasta `Lib\site-packages` (ou `_internal`, na compilação PyInstaller), podendo ser substituídas pelo usuário, como exige a licença.
