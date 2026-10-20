"""Exportação: TXT limpo (padrão), TXT com marcações de tempo e SRT (opcionais).

Gravação atômica: escreve em arquivo temporário na mesma pasta e só então troca
pelo nome final (os.replace). Um texto incompleto nunca aparece como finalizado.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Set

from .audio import fmt_hms
from .engines.base import Seg
from .textproc import Paragraph

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_stem(name: str) -> str:
    s = _INVALID.sub("_", name).strip().rstrip(".")
    return s or "aula"


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


def atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".~" + path.stem[:40], suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def lesson_title(stem: str) -> str:
    t = re.sub(r"[_]+", " ", stem)
    t = re.sub(r"\s+", " ", t).strip()
    return t.upper()


def build_txt(stem: str, duration: float, paras: List[Paragraph], footer: str = "") -> str:
    lines = [f"AULA: {lesson_title(stem)}", "", f"Duração original: {fmt_hms(duration)}", "",
             "TRANSCRIÇÃO", ""]
    if not paras:
        lines += ["[Nenhuma fala detectada no áudio]", ""]
    for p in paras:
        lines += [p.text, ""]
    if footer:
        lines += ["—" * 40, footer, ""]
    return "\n".join(lines)


def build_txt_timestamps(stem: str, duration: float, paras: List[Paragraph]) -> str:
    lines = [f"AULA: {lesson_title(stem)}", "", f"Duração original: {fmt_hms(duration)}", "",
             "TRANSCRIÇÃO COM MARCAÇÕES DE TEMPO", ""]
    for p in paras:
        lines += [f"[{fmt_hms(p.start)}] {p.text}", ""]
    return "\n".join(lines)


def _srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"


def build_srt(segs: Iterable[Seg]) -> str:
    out = []
    for i, s in enumerate(segs, 1):
        end = max(s.end, s.start + 0.5)
        out += [str(i), f"{_srt_time(s.start)} --> {_srt_time(end)}", s.text.strip(), ""]
    return "\n".join(out)


def footer_line(model_label: str, accel: str, elapsed: float) -> str:
    return (f"Transcrição automática local — {model_label} — aceleração: {accel} — "
            f"processada em {fmt_hms(elapsed)} — {datetime.now():%d/%m/%Y %H:%M}. "
            "Revise termos técnicos antes de uso clínico ou acadêmico.")
