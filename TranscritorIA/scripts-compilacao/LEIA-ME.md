# Scripts de compilação do Transcritor IA

Os scripts ficam **dentro do código-fonte** (`../codigo-fonte/build/`), para que o projeto continue
compilável exatamente como está. Cópias compactadas de cada versão ficam em
`backups/TranscritorIA/vX.Y.Z/scripts-compilacao-X.Y.Z.zip`.

| Arquivo (em `codigo-fonte/`) | Função |
|---|---|
| `build/windows/build.sh` | **Método principal** (mesmo do Capture Pro): gera `dist/TranscritorIA-Setup-<versão>.exe` num Linux Ubuntu 24.04 |
| `build/windows/assemble.py` | Monta a pasta do programa e confere todas as DLLs (cabeçalhos PE) |
| `build/windows/launcher.c`, `launcher.rc`, `TranscritorIA.exe.manifest` | Lançadores nativos `TranscritorIA.exe` / `TranscritorIA-cli.exe` |
| `build/windows/installer.nsi` | Instalador NSIS em português |
| `build/windows/ffmpeg/` | FFmpeg/FFprobe LGPL: código-fonte `ffmpeg-n7.1.1.tar.xz`, configuração e script |
| `build/windows/whispercpp/compat.h` | Ajuste para compilar o whisper.cpp com MinGW |
| `requirements.txt` | Dependências Python com versões fixadas |
| `build/build_windows.ps1`, `.github/workflows/build-windows.yml` | Alternativa em Windows (PyInstaller) |

## Reconstruir o instalador

```bash
sudo apt install nsis gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64 glslc spirv-headers cmake git zip \
                 wine64 wine32:i386 xvfb
pip install pefile
cd TranscritorIA/codigo-fonte
xvfb-run -a ./build/windows/build.sh        # ~30 min na 1ª vez (compila whisper.cpp e FFmpeg)
```
Testes: `pip install -r requirements-build.txt && python -m pytest tests`
(para os testes de FFprobe/FFmpeg: `TRANSCRITOR_FFMPEG_DIR=<pasta com ffmpeg e ffprobe nativos>`;
compile-os com `build/windows/ffmpeg/build_ffmpeg.sh <pasta> linux`).
