"""Logs locais (nenhuma telemetria: tudo fica no disco do usuário)."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from . import paths

_configured = False


def setup(verbose: bool = False) -> logging.Logger:
    global _configured
    log = logging.getLogger("apostila")
    if _configured:
        return log
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / "apostila.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    log.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
        log.addHandler(sh)
    _configured = True
    return log


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"apostila.{name}")
