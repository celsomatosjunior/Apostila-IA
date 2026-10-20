"""Localização das pastas do aplicativo.

Separação exigida pela especificação:
  - aplicativo (pasta do executável)
  - bibliotecas de aceleração (dados/libs)
  - modelos de IA (dados/modelos)
  - configurações (dados/config)
  - arquivos temporários / checkpoints (dados/trabalhos)
  - logs (dados/logs)

Modo portátil: se existir "portable.txt" ao lado do executável, tudo fica em
<pasta do programa>/dados. Caso contrário, em %LOCALAPPDATA%/TranscritorIA.
A variável de ambiente TRANSCRITOR_DATA_DIR força outro local (usada nos testes).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME

IS_WINDOWS = sys.platform == "win32"
IS_FROZEN = getattr(sys, "frozen", False)


def app_dir() -> Path:
    # lançador nativo (TranscritorIA.exe + Python embutido) informa a pasta do programa
    env = os.environ.get("TRANSCRITOR_APPDIR")
    if env:
        return Path(env)
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_dir() -> Path:
    """Recursos empacotados (assets, motores)."""
    if IS_FROZEN:
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parents[1]


def assets_dir() -> Path:
    return resource_dir() / "assets"


def engines_dir() -> Path:
    # motores nativos (whisper.cpp) ficam ao lado do executável ou nos recursos
    for base in (app_dir(), resource_dir()):
        p = base / "engines"
        if p.is_dir():
            return p
    return app_dir() / "engines"


def is_portable() -> bool:
    return (app_dir() / "portable.txt").exists()


def data_dir() -> Path:
    env = os.environ.get("TRANSCRITOR_DATA_DIR")
    if env:
        p = Path(env)
    elif is_portable():
        p = app_dir() / "dados"
    elif IS_WINDOWS:
        p = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        p = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    return _sub("modelos")


def libs_dir() -> Path:
    return _sub("libs")


def cuda_libs_dir() -> Path:
    p = libs_dir() / "cuda"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    return _sub("config")


def jobs_dir() -> Path:
    return _sub("trabalhos")


def logs_dir() -> Path:
    return _sub("logs")
