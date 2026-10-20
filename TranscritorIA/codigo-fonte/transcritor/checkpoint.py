"""Checkpoints por aula: o que já foi transcrito sobrevive a quedas e reinícios.

Estrutura em dados/trabalhos/<id>/:
  plano.json        divisão em blocos e grupos (gerada uma vez por aula)
  grupo_00012.json  resultado de um grupo concluído (com hash de integridade)
O <id> depende do arquivo (caminho, tamanho, data de modificação) e do modelo,
portanto um arquivo alterado nunca reaproveita resultados antigos.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from . import logs, paths
from .engines.base import ChunkResult
from .segmenter import Chunk

log = logs.get("checkpoint")
PLAN_VERSION = 2


def _atomic_json(path: Path, obj) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def job_id(audio_path: Path, model_key: str, track: int = 0) -> str:
    st = Path(audio_path).stat()
    key = f"{Path(audio_path).resolve()}|{st.st_size}|{int(st.st_mtime)}|{model_key}|{PLAN_VERSION}"
    if track:  # 2.0: outra trilha de áudio = outro trabalho (trilha 0 mantém os checkpoints da 1.0)
        key += f"|a{int(track)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


class Job:
    def __init__(self, audio_path: Path, model_key: str, track: int = 0, base: Optional[Path] = None):
        self.audio_path = Path(audio_path)
        self.id = job_id(self.audio_path, model_key, track)
        self.dir = (base or paths.jobs_dir()) / self.id
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ plano
    def load_plan(self) -> Optional[dict]:
        p = self.dir / "plano.json"
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("version") != PLAN_VERSION or data.get("digest") != _digest(data["body"]):
                raise ValueError("plano corrompido")
            body = data["body"]
            body["chunks"] = [Chunk(**c) for c in body["chunks"]]
            return body
        except Exception as e:  # noqa: BLE001
            log.warning("Plano inválido em %s (%s); será recriado", self.dir, e)
            self.reset()
            return None

    def save_plan(self, duration: float, chunks: List[Chunk], groups: List[List[int]],
                  speech_s: float) -> None:
        body = {"audio": str(self.audio_path), "duration": duration, "speech_s": speech_s,
                "chunks": [c.to_dict() for c in chunks], "groups": groups}
        _atomic_json(self.dir / "plano.json", {"version": PLAN_VERSION, "digest": _digest(body), "body": body})

    # ------------------------------------------------------------ grupos
    def _gpath(self, gi: int) -> Path:
        return self.dir / f"grupo_{gi:05d}.json"

    def save_group(self, gi: int, chunk_ids: List[int], results: List[ChunkResult]) -> None:
        body = {"group": gi, "chunk_ids": chunk_ids, "results": [r.to_dict() for r in results]}
        _atomic_json(self._gpath(gi), {"digest": _digest(body), "body": body})

    def load_groups(self, groups: List[List[int]]) -> Dict[int, Dict[int, ChunkResult]]:
        """Grupos válidos já concluídos -> {gi: {chunk_id: ChunkResult}}."""
        done: Dict[int, Dict[int, ChunkResult]] = {}
        for gi, ids in enumerate(groups):
            p = self._gpath(gi)
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                body = data["body"]
                if data.get("digest") != _digest(body) or body.get("chunk_ids") != ids:
                    raise ValueError("integridade")
                res = {r["index"]: ChunkResult.from_dict(r) for r in body["results"]}
                if set(res) != set(ids):
                    raise ValueError("blocos faltando")
                done[gi] = res
            except Exception as e:  # noqa: BLE001
                log.warning("Checkpoint %s descartado (%s)", p.name, e)
                p.unlink(missing_ok=True)
        for stray in self.dir.glob(".tmp_*"):
            stray.unlink(missing_ok=True)
        return done

    def reset(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def work_dir(self) -> Path:
        p = self.dir / "tmp"
        p.mkdir(exist_ok=True)
        return p


# ---------------------------------------------------------------- fila persistida
def queue_file() -> Path:
    return paths.config_dir() / "fila_pendente.json"


def save_queue(state: dict) -> None:
    _atomic_json(queue_file(), state)


def load_queue() -> Optional[dict]:
    p = queue_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def clear_queue() -> None:
    queue_file().unlink(missing_ok=True)
