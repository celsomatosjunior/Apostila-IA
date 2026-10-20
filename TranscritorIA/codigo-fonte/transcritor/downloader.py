"""Download com retomada, verificação SHA-256 e cancelamento.

Usado SOMENTE na preparação inicial (modelos e bibliotecas de aceleração), sempre
após consentimento explícito do usuário. Nenhum áudio ou texto é enviado.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from . import __version__, logs

log = logs.get("download")
UA = f"TranscritorIA/{__version__}"
ProgressCB = Callable[[int, int], None]


class DownloadCancelled(Exception):
    pass


class DownloadError(Exception):
    pass


def _open(url: str, headers: Optional[dict] = None, timeout: float = 30.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url: str, retries: int = 3) -> dict:
    last = None
    for attempt in range(retries):
        try:
            with _open(url) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise DownloadError(f"Falha ao consultar {url}: {last}")


def sha256_file(path: Path, chunk: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def download_file(
    url: str,
    dest: Path,
    expected_size: Optional[int] = None,
    sha256: Optional[str] = None,
    progress: Optional[ProgressCB] = None,
    cancel: Optional[threading.Event] = None,
    retries: int = 5,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (expected_size is None or dest.stat().st_size == expected_size):
        if not sha256 or sha256_file(dest) == sha256.lower():
            if progress and expected_size:
                progress(expected_size, expected_size)
            return dest
    part = dest.with_name(dest.name + ".part")
    attempt = 0
    while True:
        done = part.stat().st_size if part.exists() else 0
        if expected_size and done > expected_size:
            part.unlink()
            done = 0
        headers = {"Range": f"bytes={done}-"} if done else {}
        try:
            with _open(url, headers, timeout=60) as r:
                status = getattr(r, "status", 200)
                if done and status != 206:  # servidor ignorou Range
                    done = 0
                total = expected_size or (int(r.headers.get("Content-Length", 0)) + done)
                mode = "ab" if done else "wb"
                with open(part, mode) as f:
                    last_cb = 0.0
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise DownloadCancelled()
                        buf = r.read(1 << 20)
                        if not buf:
                            break
                        f.write(buf)
                        done += len(buf)
                        now = time.monotonic()
                        if progress and now - last_cb > 0.2:
                            progress(done, total)
                            last_cb = now
            if expected_size and done < expected_size:
                raise DownloadError("download incompleto")
            break
        except DownloadCancelled:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, DownloadError) as e:
            attempt += 1
            log.warning("Erro no download (%s), tentativa %d: %s", url, attempt, e)
            if attempt > retries:
                raise DownloadError(f"Não foi possível baixar {url}: {e}") from e
            time.sleep(min(30, 2 ** attempt))
    if expected_size and part.stat().st_size != expected_size:
        part.unlink(missing_ok=True)
        raise DownloadError(f"Tamanho inesperado em {dest.name}")
    if sha256:
        got = sha256_file(part)
        if got != sha256.lower():
            part.unlink(missing_ok=True)
            raise DownloadError(f"Arquivo corrompido (SHA-256 não confere): {dest.name}")
    os.replace(part, dest)
    if progress:
        progress(dest.stat().st_size, dest.stat().st_size)
    return dest


# ------------------------------------------------------------ Hugging Face
HF = "https://huggingface.co"


def hf_list_files(repo: str) -> list:
    """Lista [{path, size, sha256}] do repositório (API pública, sem login)."""
    data = get_json(f"{HF}/api/models/{repo}/tree/main")
    files = []
    for it in data:
        if it.get("type") != "file":
            continue
        lfs = it.get("lfs") or {}
        files.append({
            "path": it["path"],
            "size": lfs.get("size", it.get("size")),
            "sha256": lfs.get("oid"),
        })
    return files


def hf_url(repo: str, path: str) -> str:
    return f"{HF}/{repo}/resolve/main/{path}"
