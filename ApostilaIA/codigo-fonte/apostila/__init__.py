"""ApostilaIA — apostilas de estudo a partir de transcrições e slides, com IA 100% local."""

import os as _os

# Privacidade: nenhuma telemetria, nenhum acesso automático à rede.
for _k, _v in (("HF_HUB_DISABLE_TELEMETRY", "1"), ("HF_HUB_OFFLINE", "1"),
               ("DO_NOT_TRACK", "1"), ("LLAMA_OFFLINE", "1")):
    _os.environ.setdefault(_k, _v)

__version__ = "1.0.0"
APP_NAME = "ApostilaIA"
APP_TITLE = "ApostilaIA"
