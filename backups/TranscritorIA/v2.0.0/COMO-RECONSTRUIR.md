# Como reconstruir o executável da 2.0.0

1. Descompacte `TranscritorIA-2.0.0-codigo-fonte.zip` (ou use `TranscritorIA/codigo-fonte` na branch
   `transcritor-versao-2.0.0`).
2. Num Ubuntu 24.04:
   ```bash
   sudo dpkg --add-architecture i386 && sudo apt update
   sudo apt install nsis gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64 glslc spirv-headers cmake git zip \
                    wine64 wine32:i386 xvfb python3-pip
   pip install pefile
   xvfb-run -a ./build/windows/build.sh
   ```
3. Resultado: `dist/TranscritorIA-Setup-2.0.0.exe` e `dist/SHA256SUMS-2.0.0.txt`.
   O instalador recompilado não é idêntico byte a byte (datas internas), mas tem o mesmo conteúdo.
4. Testes: `pip install -r requirements-build.txt && python -m pytest tests` (47 testes).

Sem recompilar: o instalador pronto está nesta pasta e em `TranscritorIA/instaladores/v2.0.0/`.
