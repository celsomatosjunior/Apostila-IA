#!/usr/bin/env bash
# Gera o instalador Windows x64 do Transcritor IA Local a partir do Linux
# (mesmo método do Capture Pro: Python embutido + lançador nativo em C + NSIS).
#
# Ubuntu 24.04:
#   sudo apt install nsis gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64 glslc spirv-headers \
#                    cmake git zip wine64 wine32:i386 xvfb
#   pip install pefile
#   ./build/windows/build.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
HERE=$ROOT/build/windows
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+?)\"', open('transcritor/__init__.py').read()).group(1))")
WORK=${WORK:-$ROOT/.build-win}
DIST=$ROOT/dist
PYTAG=20250115
PYVER=3.12.8
WCPP_TAG=v1.9.5
mkdir -p "$WORK" "$DIST"

echo "== 1/9 Python $PYVER para Windows (python-build-standalone)"
if [ ! -d "$WORK/winpy/python" ]; then
  curl -sSL -o "$WORK/py.tar.gz" \
    "https://github.com/astral-sh/python-build-standalone/releases/download/$PYTAG/cpython-$PYVER%2B$PYTAG-x86_64-pc-windows-msvc-install_only.tar.gz"
  mkdir -p "$WORK/winpy" && tar xzf "$WORK/py.tar.gz" -C "$WORK/winpy"
fi

echo "== 2/9 Dependências (wheels win_amd64, versões fixadas em requirements.txt)"
mkdir -p "$WORK/wheels"
python3 -m pip download -q --only-binary=:all: --platform win_amd64 --python-version 3.12 \
  --implementation cp -d "$WORK/wheels" -r requirements.txt

echo "== 3/9 Lançadores nativos (TranscritorIA.exe e TranscritorIA-cli.exe)"
( cd "$HERE"
  x86_64-w64-mingw32-windres launcher.rc -O coff -o "$WORK/launcher.res"
  x86_64-w64-mingw32-gcc -O2 -s -municode -mwindows -Wall -o "$WORK/TranscritorIA.exe" launcher.c "$WORK/launcher.res" \
      -lshell32 -static -static-libgcc
  x86_64-w64-mingw32-gcc -O2 -s -municode -mconsole -DCONSOLE_APP -Wall -o "$WORK/TranscritorIA-cli.exe" launcher.c \
      "$WORK/launcher.res" -lshell32 -static -static-libgcc )

echo "== 4/9 whisper.cpp $WCPP_TAG (CPU e Vulkan), compilação cruzada MinGW"
if [ ! -f "$WORK/engines/whispercpp-vulkan/whisper-cli.exe" ]; then
  [ -d "$WORK/wcpp" ] || git clone -q --depth 1 --branch $WCPP_TAG https://github.com/ggml-org/whisper.cpp "$WORK/wcpp"
  [ -d "$WORK/vkh" ] || git clone -q --depth 1 https://github.com/KhronosGroup/Vulkan-Headers "$WORK/vkh"
  [ -d "$WORK/spvh" ] || git clone -q --depth 1 https://github.com/KhronosGroup/SPIRV-Headers "$WORK/spvh"
  # biblioteca de importação do vulkan-1.dll (a DLL real vem com o driver de vídeo)
  { echo "LIBRARY vulkan-1.dll"; echo EXPORTS
    grep -ohE "VKAPI_ATTR [A-Za-z0-9_\*]+ VKAPI_CALL vk[A-Za-z0-9_]+" \
      "$WORK/vkh/include/vulkan/vulkan_core.h" "$WORK/vkh/include/vulkan/vulkan_win32.h" | awk '{print $4}' | sort -u
  } > "$WORK/vulkan-1.def"
  x86_64-w64-mingw32-dlltool -d "$WORK/vulkan-1.def" -l "$WORK/libvulkan-1.a"
  cat > "$WORK/mingw.cmake" <<'EOF'
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER x86_64-w64-mingw32-gcc-posix)
set(CMAKE_CXX_COMPILER x86_64-w64-mingw32-g++-posix)
set(CMAKE_RC_COMPILER x86_64-w64-mingw32-windres)
set(CMAKE_FIND_ROOT_PATH /usr/x86_64-w64-mingw32)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
EOF
  # AVX2/FMA portáveis (i7-10700, Ryzen, Core Ultra); executável estático (sem DLLs do MinGW)
  COMMON=(-DCMAKE_TOOLCHAIN_FILE="$WORK/mingw.cmake" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF
          -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_OPENMP=OFF -DBUILD_SHARED_LIBS=OFF
          -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF -DWHISPER_SDL2=OFF -DCMAKE_EXE_LINKER_FLAGS=-static
          "-DCMAKE_C_FLAGS=-include $HERE/whispercpp/compat.h" "-DCMAKE_CXX_FLAGS=-I$WORK/spvh/include")
  cmake -S "$WORK/wcpp" -B "$WORK/bcpu" "${COMMON[@]}"
  cmake --build "$WORK/bcpu" -j "$(nproc)" --target whisper-cli
  cmake -S "$WORK/wcpp" -B "$WORK/bvk" "${COMMON[@]}" -DGGML_VULKAN=ON -DVulkan_INCLUDE_DIR="$WORK/vkh/include" \
        -DVulkan_LIBRARY="$WORK/libvulkan-1.a" -DVulkan_GLSLC_EXECUTABLE=/usr/bin/glslc \
        -DSPIRV-Headers_DIR=/usr/share/cmake/SPIRV-Headers
  cmake --build "$WORK/bvk" -j "$(nproc)" --target whisper-cli
  for v in cpu vulkan; do
    b=$WORK/bcpu; [ $v = vulkan ] && b=$WORK/bvk
    mkdir -p "$WORK/engines/whispercpp-$v"
    cp "$b/bin/whisper-cli.exe" "$WORK/engines/whispercpp-$v/"
    cp "$WORK/wcpp/LICENSE" "$WORK/engines/whispercpp-$v/LICENSE-whisper.cpp.txt"
  done
fi

echo "== 5/9 FFmpeg e FFprobe n7.1.1 (LGPL, só leitura de áudio; vídeo nunca é decodificado)"
if [ ! -f "$WORK/ff/out-windows/ffprobe.exe" ]; then
  "$HERE/ffmpeg/build_ffmpeg.sh" "$WORK/ff" windows
fi
mkdir -p "$WORK/engines/ffmpeg"
cp "$WORK/ff/out-windows/ffmpeg.exe" "$WORK/ff/out-windows/ffprobe.exe" "$WORK/engines/ffmpeg/"
cp "$HERE/licencas/FFmpeg-LGPL-2.1.txt" "$WORK/engines/ffmpeg/LICENCA-LGPL-2.1.txt"
cp "$HERE/ffmpeg/ffconf.sh" "$WORK/engines/ffmpeg/configuracao-lgpl.txt"
cat > "$WORK/engines/ffmpeg/LEIA-ME.txt" <<EOF
FFmpeg 7.1.1 (ffmpeg.exe e ffprobe.exe), compilado sem componentes GPL ou nonfree.
Licença: GNU LGPL 2.1 ou posterior (LICENCA-LGPL-2.1.txt). Opções de compilação: configuracao-lgpl.txt.
Código-fonte correspondente: ffmpeg-n7.1.1.tar.xz, guardado junto ao código do Transcritor IA
(scripts-compilacao) e disponível em https://ffmpeg.org/releases/ . Estes programas são executados
como processos separados e podem ser substituídos por outra compilação compatível.
EOF

echo "== 6/9 Montagem da pasta do programa (com verificação de DLLs pelos cabeçalhos PE)"
python3 "$HERE/assemble.py" "$WORK/winpy/python" "$WORK/wheels" "$WORK" "$WORK/engines" "$DIST/TranscritorIA"

echo "== 7/9 Bytecode Python 3.12 (compilado pelo próprio Python do Windows, via Wine)"
export WINEPREFIX=${WINEPREFIX:-$WORK/wine} WINEDEBUG=-all
( cd "$DIST/TranscritorIA" && wine python.exe -I -m compileall -q --invalidation-mode unchecked-hash \
    -x '[\\/](tests?|idle_test)[\\/]' Lib app 2>&1 | tail -3 )

echo "== 8/9 Instalador"
( cd "$HERE" && makensis -V2 -DVERSION="$VERSION" -DDISTDIR="$DIST/TranscritorIA" \
    -DOUTFILE="$DIST/TranscritorIA-Setup-$VERSION.exe" installer.nsi )

echo "== 9/9 SHA-256"
( cd "$DIST" && sha256sum "TranscritorIA-Setup-$VERSION.exe" > "SHA256SUMS-$VERSION.txt" && cat "SHA256SUMS-$VERSION.txt" )
ls -lh "$DIST"
