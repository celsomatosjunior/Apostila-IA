"""Utilidades: gravação atômica, JSON com integridade, nomes de arquivo, texto."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Set

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_stem(name: str) -> str:
    s = _INVALID.sub("_", name).strip().rstrip(".")
    return s or "apostila"


def unique_path(folder: Path, stem: str, ext: str, reserved: Optional[Set[str]] = None) -> Path:
    reserved = reserved if reserved is not None else set()
    stem = safe_stem(stem)
    cand = folder / f"{stem}{ext}"
    n = 2
    while cand.exists() or str(cand).lower() in reserved:
        cand = folder / f"{stem} ({n}){ext}"
        n += 1
    reserved.add(str(cand).lower())
    return cand


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".~" + path.stem[:40], suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_json(path: Path, obj) -> None:
    """JSON com hash de integridade (checkpoint)."""
    atomic_write_text(path, json.dumps({"digest": digest(obj), "body": obj}, ensure_ascii=False))


def load_json(path: Path):
    """Lê JSON salvo por save_json; devolve None se ausente ou corrompido."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("digest") != digest(data["body"]):
            raise ValueError("integridade")
        return data["body"]
    except Exception:  # noqa: BLE001
        try:
            path.unlink()
        except OSError:
            pass
        return None


def file_fingerprint(paths: Iterable[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        p = Path(p)
        st = p.stat()
        h.update(f"{p.name}|{st.st_size}|".encode())
        with open(p, "rb") as f:  # conteúdo (arquivos de aula são pequenos)
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ texto
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_WORD = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][0-9A-Za-zÀ-ÖØ-öø-ÿ]+)*")


def words(s: str) -> List[str]:
    return _WORD.findall(s)


def norm_word(w: str) -> str:
    return strip_accents(w.lower())


STOP = set(norm_word(w) for w in """
a o as os um uma uns umas de do da dos das no na nos nas em por para pra pro com sem sob sobre
e ou mas que se nao sim ja mais menos muito muita muitos muitas pouco tambem so como quando onde
eu tu ele ela nos vos eles elas voce voces me te lhe isso isto aquilo esse essa esses essas este esta
estes estas aquele aquela aqui ali la ai entao assim ne ta tah bom ok certo gente pessoal tipo
ser estar ter haver fazer ir vir dar ver poder dizer falar ficar e foi era sao estao esta tem tinha
vai vou vamos fica vez vezes coisa coisas aqui agora depois antes ainda porque pois qual quais
ao aos à às pelo pela pelos pelas num numa seu sua seus suas meu minha nosso nossa dele dela
""".split())


def content_words(s: str) -> List[str]:
    return [norm_word(w) for w in words(s) if len(w) > 2 and norm_word(w) not in STOP]


def est_tokens(s: str) -> int:
    """Estimativa conservadora para português (~3,3 caracteres/token)."""
    return int(len(s) / 3.3) + 1


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def fmt_hms(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
