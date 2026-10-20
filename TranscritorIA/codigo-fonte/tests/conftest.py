import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXT = ROOT / "tests" / "_gerados"


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRITOR_DATA_DIR", str(tmp_path / "dados"))
    yield


def lecture(name: str, minutes: float, *extra: str) -> Path:
    """Gera (uma vez) uma aula sintética com partitura de palavras."""
    FIXT.mkdir(exist_ok=True)
    out = FIXT / name
    if not out.exists() or not out.with_suffix(".json").exists():
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "gerar_audio_teste.py"), "aula",
                               str(out), str(minutes), *extra])
    return out


def script_of(path: Path):
    return [tuple(x) for x in json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))]
