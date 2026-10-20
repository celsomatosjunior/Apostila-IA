# PyInstaller — gera dist/TranscritorIA/ com:
#   TranscritorIA.exe       (interface gráfica, duplo clique)
#   TranscritorIA-cli.exe   (linha de comando: automação, diagnóstico, testes)
#   _internal/              (bibliotecas, compartilhadas pelos dois executáveis)
#   engines/whispercpp-vulkan/  (whisper.cpp compilado com Vulkan, se presente)
# Os modelos de IA NÃO entram no pacote: são baixados com consentimento no 1º uso.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
ENG = ROOT / "engines"

datas = [(str(ROOT / "assets"), "assets")]
datas += collect_data_files("faster_whisper")          # silero_vad_v6.onnx
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")

excludes = ["tkinter", "matplotlib", "PIL", "cryptography", "hf_xet", "torch", "torchaudio", "scipy", "pandas", "IPython", "jupyter",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
            "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
            "PySide6.QtOpenGL", "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtPrintSupport"]

hidden = ["transcritor.gui.app", "transcritor.cli", "transcritor.engines.ct2_engine",
          "transcritor.engines.whispercpp_engine", "onnxruntime", "ctranslate2"]

a = Analysis([str(ROOT / "TranscritorIA.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=excludes, noarchive=False, optimize=1)
pyz = PYZ(a.pure)
icon = str(ROOT / "assets" / "icone.ico")
version_file = str(ROOT / "build" / "version_info.txt")

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TranscritorIA", console=False,
          icon=icon, version=version_file, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TranscritorIA-cli", console=True,
          icon=icon, version=version_file, upx=False)

coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="TranscritorIA")
