"""Arquivos de mídia (áudio e vídeo) como FONTES DE ÁUDIO — versão 2.0.

Regra fundamental: um vídeo é tratado só como contêiner do áudio.
  * A análise (contêiner, trilhas, idioma, duração) usa o FFprobe incluído no pacote
    (ou, na falta dele, as mesmas bibliotecas FFmpeg embutidas no PyAV).
  * A leitura demultiplexa o arquivo e decodifica SOMENTE a trilha de áudio escolhida,
    em streaming, direto para a memória (16 kHz mono). Os quadros de vídeo nunca são
    decodificados, nada é gravado em disco e o arquivo original só é aberto para leitura.
  * Se a leitura principal falhar (arquivo danificado, formato raro), o ffmpeg.exe incluído
    tenta de novo, ignorando os trechos corrompidos (-err_detect ignore_err), também em
    streaming por pipe — sem arquivo temporário.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from . import logs, paths

log = logs.get("media")
SR = 16000
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".flac", ".aac", ".wma", ".opus", ".amr",
              ".mpga", ".m4b", ".aif", ".aiff", ".caf", ".ac3", ".mka", ".w64"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".mpeg", ".mpg", ".m4v", ".flv",
              ".ts", ".mts", ".m2ts", ".3gp", ".vob", ".ogv", ".asf", ".divx", ".f4v"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

_PT_TAGS = {"pt", "por", "pt-br", "pt_br", "ptb", "pob", "pt-pt", "portuguese", "português", "portugues"}


class MediaError(Exception):
    """Erro de leitura com mensagem pronta para o usuário."""


class NoAudioError(MediaError):
    pass


@dataclass
class AudioTrack:
    ordinal: int              # posição entre as trilhas de ÁUDIO (0, 1, 2…) — usada pelo -map 0:a:N
    stream_index: int         # índice absoluto no contêiner
    codec: str = ""
    language: str = ""
    title: str = ""
    channels: int = 0
    sample_rate: int = 0
    default: bool = False
    duration: float = 0.0

    @property
    def is_portuguese(self) -> bool:
        lang = self.language.strip().lower()
        title = self.title.strip().lower()
        return lang in _PT_TAGS or "portugu" in title or "dublado" in title

    def label(self, short: bool = False) -> str:
        parts = [f"Trilha {self.ordinal + 1}"]
        if self.language and self.language.lower() not in ("und", "unknown"):
            parts.append(self.language)
        if self.title:
            parts.append(self.title)
        if short:
            return " · ".join(parts)
        if self.codec:
            parts.append(self.codec.upper())
        if self.channels:
            parts.append({1: "mono", 2: "estéreo"}.get(self.channels, f"{self.channels} canais"))
        return " · ".join(parts)


@dataclass
class MediaInfo:
    path: str
    kind: str                 # "audio" | "video"
    container: str = ""
    duration: float = 0.0
    has_video: bool = False
    tracks: List[AudioTrack] = field(default_factory=list)
    selected: Optional[int] = None    # ordinal da trilha escolhida
    reason: str = ""                  # por que essa trilha
    ambiguous: bool = False           # várias trilhas sem português identificado
    prober: str = ""                  # "ffprobe" | "pyav"

    @property
    def kind_label(self) -> str:
        return "Vídeo" if self.kind == "video" else "Áudio"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------- ferramentas
def tool(name: str) -> Optional[Path]:
    """ffmpeg/ffprobe incluídos no pacote (engines/ffmpeg) ou indicados por variável de ambiente."""
    exe = name + (".exe" if IS_WINDOWS else "")
    env = os.environ.get("TRANSCRITOR_FFMPEG_DIR")
    cands = []
    if env:
        cands.append(Path(env) / exe)
    cands.append(paths.engines_dir() / "ffmpeg" / exe)
    for c in cands:
        if c.is_file():
            return c
    w = shutil.which(exe) if os.environ.get("TRANSCRITOR_ALLOW_SYSTEM_FFMPEG") else None
    return Path(w) if w else None


def kind_from_ext(path: Path) -> str:
    return "video" if Path(path).suffix.lower() in VIDEO_EXTS else "audio"


# ---------------------------------------------------------------------- escolha da trilha
def choose_track(tracks: List[AudioTrack]) -> Tuple[Optional[int], str, bool]:
    """(ordinal, motivo, ambíguo). Prioridade: português > trilha padrão > mais canais > primeira."""
    if not tracks:
        return None, "sem trilha de áudio", False
    if len(tracks) == 1:
        return tracks[0].ordinal, "única trilha de áudio", False
    pt = [t for t in tracks if t.is_portuguese]
    if pt:
        best = sorted(pt, key=lambda t: (not t.default, -t.channels, t.ordinal))[0]
        return best.ordinal, "trilha em português", False
    # várias trilhas e nenhuma identificada como português: escolhe, mas pede conferência
    default = [t for t in tracks if t.default]
    if default:
        return default[0].ordinal, "trilha padrão do arquivo", True
    best = sorted(tracks, key=lambda t: (-t.channels, t.ordinal))[0]
    return best.ordinal, "primeira trilha", True


# ---------------------------------------------------------------------- análise
def _probe_ffprobe(path: Path, exe: Path) -> MediaInfo:
    r = subprocess.run([str(exe), "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                        str(path)], capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise MediaError(r.stderr.decode("utf-8", "replace").strip()[-300:] or "ffprobe falhou")
    data = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    fmt = data.get("format", {})
    info = MediaInfo(str(path), kind_from_ext(path), container=fmt.get("format_name", ""), prober="ffprobe")
    try:
        info.duration = float(fmt.get("duration") or 0.0)
    except ValueError:
        info.duration = 0.0
    n = 0
    for st in data.get("streams", []):
        disp = st.get("disposition", {}) or {}
        tags = {k.lower(): v for k, v in (st.get("tags", {}) or {}).items()}
        if st.get("codec_type") == "video" and not disp.get("attached_pic"):
            info.has_video = True
        if st.get("codec_type") != "audio":
            continue
        try:
            dur = float(st.get("duration") or 0.0)
        except ValueError:
            dur = 0.0
        info.tracks.append(AudioTrack(n, int(st.get("index", n)), st.get("codec_name", ""),
                                      tags.get("language", ""), tags.get("title", ""),
                                      int(st.get("channels") or 0), int(st.get("sample_rate") or 0),
                                      bool(disp.get("default")), dur))
        n += 1
    return info


def _probe_pyav(path: Path) -> MediaInfo:
    import av

    with av.open(str(path)) as c:
        info = MediaInfo(str(path), kind_from_ext(path), container=c.format.name or "", prober="pyav")
        info.duration = float(c.duration) / 1_000_000.0 if c.duration else 0.0
        n = 0
        D = getattr(av.stream, "Disposition", None)
        for st in c.streams:
            disp = int(getattr(st, "disposition", 0) or 0)
            attached = bool(D and disp & int(D.attached_pic))
            if st.type == "video" and not attached:
                info.has_video = True
            if st.type != "audio":
                continue
            md = {k.lower(): v for k, v in (st.metadata or {}).items()}
            dur = float(st.duration * st.time_base) if st.duration and st.time_base else 0.0
            cc = st.codec_context
            info.tracks.append(AudioTrack(n, st.index, (cc.name if cc else "") or "", md.get("language", ""),
                                          md.get("title", ""), int(getattr(cc, "channels", 0) or 0),
                                          int(getattr(cc, "sample_rate", 0) or 0),
                                          bool(D and disp & int(D.default)), dur))
            n += 1
    return info


def probe(path) -> MediaInfo:
    path = Path(path)
    if not path.is_file():
        raise MediaError(f"Arquivo não encontrado: {path.name}")
    if path.stat().st_size == 0:
        raise MediaError(f"{path.name} está vazio (0 bytes)")
    info = None
    exe = tool("ffprobe")
    if exe is not None:
        try:
            info = _probe_ffprobe(path, exe)
        except (MediaError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            log.info("ffprobe não leu %s (%s); usando PyAV", path.name, e)
    if info is None:
        try:
            info = _probe_pyav(path)
        except Exception as e:  # noqa: BLE001
            hint = ""
            if path.suffix.lower() in (".mp4", ".m4v", ".mov", ".3gp", ".f4v"):
                hint = (" Em MP4/MOV isso costuma indicar gravação interrompida ou cópia incompleta: o índice do "
                        "arquivo (moov) fica no final e, sem ele, o vídeo não pode ser lido.")
            raise MediaError(f"Não foi possível ler {path.name}: arquivo danificado ou formato não suportado."
                             f"{hint} ({str(e)[:120]})") from e
    if info.has_video:
        info.kind = "video"
    if not info.duration and info.tracks:
        info.duration = max(t.duration for t in info.tracks)
    info.selected, info.reason, info.ambiguous = choose_track(info.tracks)
    return info


# ---------------------------------------------------------------------- leitura do áudio
class _Sink:
    """Acumula amostras float32 num buffer pré-alocado (cresce se preciso)."""

    def __init__(self, expected_s: float):
        n = int(max(expected_s, 10.0) * SR * 1.02) + SR
        self.buf = np.empty(n, dtype=np.float32)
        self.n = 0

    def add_s16(self, pcm: np.ndarray) -> None:
        k = pcm.shape[0]
        if self.n + k > self.buf.shape[0]:
            new = np.empty(max(self.buf.shape[0] * 3 // 2, self.n + k), dtype=np.float32)
            new[: self.n] = self.buf[: self.n]
            self.buf = new
        np.multiply(pcm, 1.0 / 32768.0, out=self.buf[self.n: self.n + k], casting="unsafe")
        self.n += k

    def result(self) -> np.ndarray:
        out = self.buf[: self.n]
        if self.buf.shape[0] - self.n > SR * 60:  # devolve a sobra grande
            out = out.copy()
        return out


def _decode_pyav(path: Path, ordinal: int, expected: float, cancel) -> Tuple[np.ndarray, int]:
    import av

    sink = _Sink(expected)
    bad = 0
    with av.open(str(path)) as c:
        audio = [s for s in c.streams if s.type == "audio"]
        if not audio:
            raise NoAudioError("Este arquivo não tem trilha de áudio — não há o que transcrever.")
        st = audio[min(ordinal, len(audio) - 1)]
        st.thread_type = "AUTO"
        # descarta os pacotes das demais trilhas já no demultiplexador
        for other in c.streams:
            if other is not st:
                try:
                    other.discard = "all"  # PyAV >= 13
                except Exception:  # noqa: BLE001
                    pass
        rs = av.AudioResampler(format="s16", layout="mono", rate=SR)
        npk = 0
        for packet in c.demux(st):
            npk += 1
            if cancel is not None and npk % 4000 == 0 and cancel.is_set():
                raise MediaError("cancelado")
            try:
                frames = packet.decode()
            except (av.error.InvalidDataError, av.error.ValueError, ValueError) as e:  # pacote danificado
                bad += 1
                if bad <= 3:
                    log.warning("Trecho danificado ignorado em %s: %s", path.name, e)
                continue
            for fr in frames:
                for out in rs.resample(fr):
                    sink.add_s16(out.to_ndarray().reshape(-1))
        for out in rs.resample(None):
            sink.add_s16(out.to_ndarray().reshape(-1))
    return sink.result(), bad


def _decode_ffmpeg(path: Path, ordinal: int, expected: float, cancel) -> np.ndarray:
    exe = tool("ffmpeg")
    if exe is None:
        raise MediaError("ffmpeg não disponível")
    cmd = [str(exe), "-nostdin", "-v", "error", "-err_detect", "ignore_err", "-i", str(path),
           "-map", f"0:a:{ordinal}", "-vn", "-sn", "-dn", "-ac", "1", "-ar", str(SR),
           "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
    sink = _Sink(expected)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    err_chunks: List[bytes] = []
    t = threading.Thread(target=lambda: err_chunks.append(p.stderr.read()), daemon=True)
    t.start()
    rest = b""
    try:
        while True:
            if cancel is not None and cancel.is_set():
                p.kill()
                raise MediaError("cancelado")
            b = p.stdout.read(1 << 20)
            if not b:
                break
            b = rest + b
            usable = len(b) - (len(b) % 2)
            sink.add_s16(np.frombuffer(b[:usable], dtype="<i2"))
            rest = b[usable:]
    finally:
        p.wait()
        t.join(5)
    if sink.n == 0:
        msg = (err_chunks[0] if err_chunks else b"").decode("utf-8", "replace").strip()
        raise MediaError(msg[-300:] or "ffmpeg não produziu áudio")
    return sink.result()


def decode(path, track: Optional[int] = None, expected_duration: float = 0.0, cancel=None,
           info: Optional[MediaInfo] = None) -> np.ndarray:
    """Áudio da trilha escolhida em 16 kHz mono float32 (somente o áudio; vídeo é ignorado)."""
    path = Path(path)
    if info is None:
        info = probe(path)
    if not info.tracks:
        raise NoAudioError(f"{path.name}: este {'vídeo' if info.kind == 'video' else 'arquivo'} não tem trilha "
                           "de áudio — não há o que transcrever.")
    ordinal = info.selected if track is None else track
    ordinal = max(0, min(int(ordinal or 0), len(info.tracks) - 1))
    expected = expected_duration or info.duration
    first_error: Optional[Exception] = None
    try:
        a, bad = _decode_pyav(path, ordinal, expected, cancel)
        if a.size and (bad == 0 or not tool("ffmpeg")):
            return a
        if a.size:
            # trechos danificados: o ffmpeg com tolerância a erros costuma recuperar mais áudio
            try:
                b = _decode_ffmpeg(path, ordinal, expected, cancel)
                return b if b.size > a.size else a
            except MediaError:
                return a
    except NoAudioError:
        raise
    except MediaError as e:
        if str(e) == "cancelado":
            raise
        first_error = e
    except Exception as e:  # noqa: BLE001
        first_error = e
        log.warning("PyAV falhou em %s: %s — tentando ffmpeg", path.name, e)
    try:
        return _decode_ffmpeg(path, ordinal, expected, cancel)
    except MediaError as e:
        if str(e) == "cancelado":
            raise
        raise MediaError(f"Não foi possível ler o áudio de {path.name}: arquivo danificado ou formato não "
                         f"suportado. ({str(first_error or e)[:160]})") from e
