# Versões fixadas — Transcritor IA Local 2.0.0

| Componente | Versão | Origem |
|---|---|---|
| Python para Windows | 3.12.8 (python-build-standalone 20250115) | github.com/astral-sh/python-build-standalone |
| Pacotes Python | ver `requirements.txt` (faster-whisper 1.2.1, ctranslate2 4.8.3, av 19.0.1, onnxruntime 1.29.0, numpy 2.5.3, psutil 7.2.2, tokenizers 0.23.3, huggingface_hub 2.2.0, PySide6-Essentials 6.12.0) | PyPI (wheels win_amd64) |
| whisper.cpp (motores CPU e Vulkan) | v1.9.5, AVX2/FMA, estático (MinGW-w64 13) | github.com/ggml-org/whisper.cpp |
| Cabeçalhos Vulkan / SPIR-V | KhronosGroup Vulkan-Headers e SPIRV-Headers (branch principal no dia da compilação) | github.com/KhronosGroup |
| FFmpeg / FFprobe | n7.1.1, LGPL, `ffconf.sh` (código-fonte incluído: `ffmpeg-n7.1.1.tar.xz`) | ffmpeg.org |
| Bibliotecas NVIDIA (baixadas no 1º uso) | cuBLAS 12.9.2.10, NVRTC 12.9.86, cuDNN 9.10.2.21 | PyPI (pacotes oficiais NVIDIA) |
| Instalador | NSIS 3 (Ubuntu 24.04) | |
