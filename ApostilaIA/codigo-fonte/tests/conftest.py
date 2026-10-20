import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
GER = ROOT / "tests" / "_gerados"


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("APOSTILA_DATA_DIR", str(tmp_path / "dados"))
    yield


@pytest.fixture
def bloquear_rede(monkeypatch):
    """Qualquer conexão que não seja 127.0.0.1 falha (prova de funcionamento offline)."""
    import socket
    tentativas = []
    orig = socket.socket.connect

    def connect(self, addr):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("127.0.0.1", "localhost", "::1"):
            tentativas.append(host)
            raise OSError(f"rede bloqueada no teste: {host}")
        return orig(self, addr)
    monkeypatch.setattr(socket.socket, "connect", connect)
    orig_gai = socket.getaddrinfo

    def gai(host, *a, **k):
        if host not in ("127.0.0.1", "localhost", "::1", None):
            tentativas.append(host)
            raise OSError(f"DNS bloqueado no teste: {host}")
        return orig_gai(host, *a, **k)
    monkeypatch.setattr(socket, "getaddrinfo", gai)
    return tentativas


def llama_linux_dir():
    d = os.environ.get("APOSTILA_TEST_LLAMA")
    return Path(d) if d else None


def tiny_model():
    m = os.environ.get("APOSTILA_TEST_GGUF")
    return Path(m) if m and Path(m).exists() else None
