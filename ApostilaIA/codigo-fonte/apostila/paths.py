"""Localização das pastas do aplicativo.

Separação exigida pela especificação:
  - aplicativo (pasta do executável)
  - bibliotecas de aceleração CUDA baixadas (dados/libs)
  - modelos de IA (dados/modelos)
  - configurações (dados/config)
  - projetos em andamento / checkpoints (dados/projetos)
  - logs (dados/logs)

Modo portátil: se existir "portable.txt" ao lado do executável, tudo fica em
<pasta do programa>/dados. Caso contrário, em %LOCALAPPDATA%/ApostilaIA.
A variável de ambiente APOSTILA_DATA_DIR força outro local (usada nos testes).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME

IS_WINDOWS = sys.platform == "win32"
IS_FROZEN = getattr(sys, "frozen", False)


def app_dir() -> Path:
    # lançador nativo (ApostilaIA.exe + Python embutido) informa a pasta do programa
    env = os.environ.get("APOSTILA_APPDIR")
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


def runtime_dir() -> Path:
    """llama.cpp empacotado (Vulkan/CPU) ao lado do executável."""
    env = os.environ.get("APOSTILA_LLAMA_DIR")
    if env:
        return Path(env)
    for base in (app_dir(), resource_dir()):
        p = base / "llama"
        if p.is_dir():
            return p
    return app_dir() / "llama"


def is_portable() -> bool:
    return (app_dir() / "portable.txt").exists()


def data_dir() -> Path:
    env = os.environ.get("APOSTILA_DATA_DIR")
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


def cuda_runtime_dir(variant: str) -> Path:
    """llama.cpp CUDA baixado sob consentimento (variant: '12.4' ou '13.4')."""
    p = libs_dir() / f"llama-cuda-{variant}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    return _sub("config")


def jobs_dir() -> Path:
    return _sub("projetos")


def logs_dir() -> Path:
    return _sub("logs")
