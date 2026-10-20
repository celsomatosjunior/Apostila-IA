#!/usr/bin/env bash
# Compila ffmpeg.exe e ffprobe.exe (Windows x64, estáticos, LGPL) por compilação cruzada MinGW.
# Uso: build_ffmpeg.sh <pasta-de-trabalho> [linux]   ("linux" = versão nativa, só para os testes)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${1:?pasta de trabalho}
TARGET=${2:-windows}
VER=n7.1.1
mkdir -p "$WORK"; cd "$WORK"
if [ ! -d src ]; then mkdir src && tar xJf "$HERE/ffmpeg-$VER.tar.xz" -C src --strip-components=1; fi
. "$HERE/ffconf.sh"
rm -rf "b-$TARGET" && cp -r src "b-$TARGET" && cd "b-$TARGET"
if [ "$TARGET" = windows ]; then
  ./configure --target-os=mingw32 --arch=x86_64 --cross-prefix=x86_64-w64-mingw32- --enable-cross-compile \
    --pkg-config=false $COMMON --enable-w32threads --extra-ldflags="-static -static-libgcc" --extra-cflags="-O2"
  make -j"$(nproc)"
  mkdir -p "$WORK/out-windows"
  x86_64-w64-mingw32-strip -o "$WORK/out-windows/ffmpeg.exe" ffmpeg.exe
  x86_64-w64-mingw32-strip -o "$WORK/out-windows/ffprobe.exe" ffprobe.exe
else
  ./configure --pkg-config=false $COMMON --extra-cflags="-O2"
  make -j"$(nproc)"
  mkdir -p "$WORK/out-linux"; cp ffmpeg ffprobe "$WORK/out-linux/"
fi
./ffmpeg* -hide_banner -version 2>/dev/null | head -1 || true
echo "FFmpeg ($TARGET) pronto em $WORK/out-$TARGET"
