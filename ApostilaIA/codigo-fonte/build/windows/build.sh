#!/usr/bin/env bash
# Gera o instalador Windows x64 do ApostilaIA a partir do Linux
# (mesmo método do Capture Pro e do TranscritorIA: Python embutido + lançador nativo em C + NSIS).
#
# Ubuntu 24.04:
#   sudo apt install nsis gcc-mingw-w64-x86-64 zip unzip wine64 wine32:i386 xvfb
#   pip install pefile
#   ./build/windows/build.sh
#
# Variáveis opcionais: WORK (pasta de trabalho), WINEPREFIX, LLAMA_ZIPS (pasta com os zips já baixados).
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
HERE=$ROOT/build/windows
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+?)\"', open('apostila/__init__.py').read()).group(1))")
WORK=${WORK:-$ROOT/.build-win}
DIST=$ROOT/dist
PYTAG=20250115
PYVER=3.12.8
LLAMA=b11435
LLAMA_ZIPS=${LLAMA_ZIPS:-$WORK/llama-zips}
mkdir -p "$WORK" "$DIST" "$LLAMA_ZIPS"

echo "== 1/8 Python $PYVER para Windows (python-build-standalone)"
if [ ! -d "$WORK/winpy/python" ]; then
  [ -f "$WORK/py.tar.gz" ] || curl -sSL -o "$WORK/py.tar.gz" \
    "https://github.com/astral-sh/python-build-standalone/releases/download/$PYTAG/cpython-$PYVER%2B$PYTAG-x86_64-pc-windows-msvc-install_only.tar.gz"
  mkdir -p "$WORK/winpy" && tar xzf "$WORK/py.tar.gz" -C "$WORK/winpy"
fi

echo "== 2/8 Dependências (wheels win_amd64, versões fixadas em requirements.txt)"
mkdir -p "$WORK/wheels"
python3 -m pip download -q --only-binary=:all: --platform win_amd64 --python-version 3.12 \
  --implementation cp -d "$WORK/wheels" -r requirements.txt

echo "== 3/8 Lançadores nativos (ApostilaIA.exe e ApostilaIA-cli.exe)"
( cd "$HERE"
  x86_64-w64-mingw32-windres launcher.rc -O coff -o "$WORK/launcher.res"
  x86_64-w64-mingw32-gcc -O2 -s -municode -mwindows -Wall -o "$WORK/ApostilaIA.exe" launcher.c "$WORK/launcher.res" \
      -lshell32 -static -static-libgcc
  x86_64-w64-mingw32-gcc -O2 -s -municode -mconsole -DCONSOLE_APP -Wall -o "$WORK/ApostilaIA-cli.exe" launcher.c \
      "$WORK/launcher.res" -lshell32 -static -static-libgcc )

echo "== 4/8 llama.cpp $LLAMA (Vulkan + CPU), binários oficiais com SHA-256 conferido"
declare -A SHA=(
  ["llama-$LLAMA-bin-win-vulkan-x64.zip"]=631b029f7df84aa22d1b8c9c929ea3cc505a70ad091f90ac0eabdb7ef0d05563
  ["llama-$LLAMA-bin-win-cpu-x64.zip"]=3ed50261147e260d80f5cdc7bdccfa13a94882be560a4438e7a69fa519c93fb7
)
rm -rf "$WORK/llama" && mkdir -p "$WORK/llama"
for v in vulkan cpu; do
  z="llama-$LLAMA-bin-win-$v-x64.zip"
  [ -f "$LLAMA_ZIPS/$z" ] || curl -sSL -o "$LLAMA_ZIPS/$z" "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA/$z"
  echo "${SHA[$z]}  $LLAMA_ZIPS/$z" | sha256sum -c -
  mkdir -p "$WORK/llama/$v"
  unzip -q -o "$LLAMA_ZIPS/$z" -d "$WORK/llama/$v"
  # mantém só o servidor e as bibliotecas (ferramentas de linha de comando não são usadas)
  ( cd "$WORK/llama/$v"
    for f in *.exe; do [ "$f" = "llama-server.exe" ] || rm -f "$f"; done
    for f in *-impl.dll; do [ "$f" = "llama-server-impl.dll" ] || rm -f "$f"; done
    rm -f ggml-rpc.dll )
  cp "$HERE/licencas/LICENSE-llama.cpp.txt" "$WORK/llama/$v/LICENSE-llama.cpp.txt"
done
cat > "$WORK/llama/LEIA-ME.txt" <<EOF
llama.cpp $LLAMA (https://github.com/ggml-org/llama.cpp, licença MIT), compilações oficiais:
  vulkan\\  GPU via Vulkan (NVIDIA, AMD Radeon, Intel Arc) + backends de CPU otimizados
  cpu\\     somente CPU (contingência)
A versão CUDA (NVIDIA) é baixada pelo programa, com autorização, para %LOCALAPPDATA%\\ApostilaIA\\libs.
EOF

echo "== 5/8 Montagem da pasta do programa (com verificação de DLLs pelos cabeçalhos PE)"
python3 "$HERE/assemble.py" "$WORK/winpy/python" "$WORK/wheels" "$WORK" "$WORK/llama" "$DIST/ApostilaIA"

echo "== 6/8 Bytecode Python 3.12 (compilado pelo próprio Python do Windows, via Wine)"
export WINEPREFIX=${WINEPREFIX:-$WORK/wine} WINEDEBUG=-all
( cd "$DIST/ApostilaIA" && wine python.exe -I -m compileall -q --invalidation-mode unchecked-hash \
    -x '[\\/](tests?|idle_test)[\\/]' Lib app 2>&1 | tail -3 )

echo "== 7/8 Instalador"
( cd "$HERE" && makensis -V2 -DVERSION="$VERSION" -DDISTDIR="$DIST/ApostilaIA" \
    -DOUTFILE="$DIST/ApostilaIA-Setup-$VERSION.exe" installer.nsi )

echo "== 8/8 SHA-256"
( cd "$DIST" && sha256sum "ApostilaIA-Setup-$VERSION.exe" > "SHA256SUMS-$VERSION.txt" && cat "SHA256SUMS-$VERSION.txt" )
ls -lh "$DIST"
