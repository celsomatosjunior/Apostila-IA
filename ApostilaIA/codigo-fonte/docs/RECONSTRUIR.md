# Como reconstruir o ApostilaIA 1.0.0

O instalador é gerado no Linux (Ubuntu 24.04), pelo mesmo método do Capture Pro e do TranscritorIA:
Python 3.12 embutido (python-build-standalone), lançador nativo em C (MinGW) e instalador NSIS em português.

## 1. Ferramentas

```bash
sudo dpkg --add-architecture i386 && sudo apt update
sudo apt install nsis gcc-mingw-w64-x86-64 zip unzip curl wine64 wine32:i386 xvfb python3-pip
pip install pefile
```

## 2. Gerar

```bash
cd ApostilaIA/codigo-fonte          # (no repositório: pasta com apostila/, assets/, build/, requirements.txt)
WORK=/tmp/bw-apostila WINEPREFIX=/tmp/wp-apostila xvfb-run -a ./build/windows/build.sh
```

Saída: `dist/ApostilaIA-Setup-1.0.0.exe` e `dist/SHA256SUMS-1.0.0.txt`.

O script baixa e confere por SHA-256:
- Python 3.12.8 (tag 20250115) para Windows;
- as wheels win_amd64 das versões fixadas em `requirements.txt`;
- llama.cpp **b11435** oficial (`llama-b11435-bin-win-vulkan-x64.zip` e `...-win-cpu-x64.zip`; SHA-256 dentro de `build.sh`).

Sem internet, coloque os zips do llama.cpp em `$WORK/llama-zips/` e o `py.tar.gz` em `$WORK/`.

Observação: o compileall do passo 6 roda no Python do Windows via Wine. Use `LANG=C.UTF-8` se houver
nomes com acento.

## 3. Testar

```bash
pip install PySide6-Essentials==6.12.0 psutil==7.2.2 PyMuPDF==1.28.2 typst==0.15.0 python-docx==1.2.0 pytest pillow
python -m pytest tests -q                               # 16 testes obrigatórios + extras
APOSTILA_TEST_LLAMA=<llama.cpp linux> APOSTILA_TEST_GGUF=<modelo.gguf> python -m pytest tests -q   # inclui modelo real
xvfb-run -a build/windows/testar_instalador.sh dist/ApostilaIA-Setup-1.0.0.exe /tmp/wt <modelo.gguf>  # Wine
python tools/teste_integracao_llm.py <llama.cpp linux> <modelo.gguf> /tmp/integ   # pipeline com modelo real
```

## 4. Versões fixadas

| Item | Versão |
|---|---|
| Python | 3.12.8 (python-build-standalone 20250115) |
| PySide6-Essentials | 6.12.0 |
| PyMuPDF | 1.28.2 |
| typst | 0.15.0 |
| python-docx | 1.2.0 |
| lxml | 6.1.3 |
| psutil | 7.2.2 |
| typing_extensions | 4.16.0 |
| llama.cpp | b11435 (Vulkan e CPU no instalador; CUDA 12.4 / 13.4 baixado pelo programa) |
| Fontes | IBM Plex Sans/Serif 6.4.1 (TTF convertido do pacote npm `@ibm/plex`, OFL) |

SHA-256 dos pacotes do llama.cpp (release b11435):

```
631b029f7df84aa22d1b8c9c929ea3cc505a70ad091f90ac0eabdb7ef0d05563  llama-b11435-bin-win-vulkan-x64.zip
3ed50261147e260d80f5cdc7bdccfa13a94882be560a4438e7a69fa519c93fb7  llama-b11435-bin-win-cpu-x64.zip
18ef0727457adf843fe0e6dc17da296c019c821e56b7bc5fc88db734538fbfb7  llama-b11435-bin-win-cuda-12.4-x64.zip
8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6  cudart-llama-bin-win-cuda-12.4-x64.zip
3d2d9edf17488f955b7c36ca38eec0398244f83be596abffbd297151f7af705c  llama-b11435-bin-win-cuda-13.4-x64.zip
738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668  cudart-llama-bin-win-cuda-13.4-x64.zip
```
