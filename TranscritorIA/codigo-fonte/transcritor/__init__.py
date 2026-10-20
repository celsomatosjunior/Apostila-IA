"""Transcritor IA Local — transcrição de aulas 100% local (Whisper)."""

import os as _os

# Privacidade: nenhuma telemetria. O ONNX Runtime (usado pelo detector de voz)
# envia eventos à Microsoft por padrão nas versões recentes; isto o desliga
# ANTES de ser carregado. O Hugging Face Hub também fica sem telemetria/offline.
for _k, _v in (("ORT_DISABLE_TELEMETRY", "1"), ("HF_HUB_DISABLE_TELEMETRY", "1"),
               ("HF_HUB_OFFLINE", "1"), ("DO_NOT_TRACK", "1")):
    _os.environ.setdefault(_k, _v)

__version__ = "2.0.0"
APP_NAME = "TranscritorIA"
APP_TITLE = "Transcritor IA Local"
