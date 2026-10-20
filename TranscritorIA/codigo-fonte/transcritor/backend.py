"""Seleção de backend, calibração automática e gerenciamento do motor em execução.

Ordem de tentativa (cada uma é VALIDADA executando uma transcrição real de
referência antes de ser usada — nada é presumido):
  NVIDIA:            CTranslate2 + CUDA  ->  whisper.cpp + Vulkan  ->  CPU
  AMD / Intel (dGPU): whisper.cpp + Vulkan  ->  CPU
  Só GPU integrada:   whisper.cpp + Vulkan (só se superar a CPU)  ->  CPU
O perfil calibrado é salvo por "impressão digital" do hardware; trocar de PC
ou conectar uma eGPU muda a impressão digital e dispara nova calibração.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from . import __version__, audio, cuda_libs, hardware, logs, metrics, models, paths
from .engines.base import (Cancelled, ChunkResult, DecodeOptions, Engine, EngineError, GpuFailure,
                           GpuOutOfMemory)
from .segmenter import Chunk

log = logs.get("backend")
# Muda somente quando motores/modelos mudam. A 2.0 não altera os motores, então a
# calibração feita pela 1.0.0 continua válida após a atualização.
CALIBRATION_VERSION = "1"
Notify = Callable[[str], None]


@dataclass
class EngineChoice:
    family: str                 # ct2 | whispercpp
    device: str                 # cuda | vulkan | cpu
    model_key: str
    gpu_index: int = 0
    gpu_name: str = ""
    compute_type: str = "auto"
    batch_size: int = 8
    threads: int = 0
    rtf: float = 0.0            # velocidade medida: minutos de áudio por minuto real
    wer_ref: Optional[float] = None
    validated: bool = False
    measurements: List[dict] = field(default_factory=list)

    @property
    def accel(self) -> str:
        return {"cuda": "CUDA", "vulkan": "Vulkan", "cpu": "CPU"}[self.device]

    @property
    def fmt(self) -> str:
        return "ct2" if self.family == "ct2" else "ggml"

    @property
    def is_gpu(self) -> bool:
        return self.device != "cpu"

    def key(self) -> str:
        return f"{self.family}|{self.device}|{self.gpu_index}|{self.model_key}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "EngineChoice":
        return EngineChoice(**d)


# ------------------------------------------------------------------ escolhas
def auto_model(vram_mb: int, device: str, ram_mb: int) -> str:
    if device in ("cuda", "vulkan"):
        if vram_mb >= 6000:
            return "large-v3"
        if vram_mb >= 3500:
            return "large-v3-turbo"
        return "small"
    return "large-v3-turbo" if ram_mb >= 8000 else "small"


def default_threads(hw: hardware.HardwareInfo, profile: str) -> int:
    phys = max(1, hw.cores_physical)
    return max(2, phys // 2) if profile == "trabalho" else phys


def build_candidates(hw: hardware.HardwareInfo, model_pref: str = "auto", engine_pref: str = "auto",
                     profile: str = "turbo") -> List[EngineChoice]:
    from .engines import whispercpp_engine

    threads = default_threads(hw, profile)
    cands: List[EngineChoice] = []
    if engine_pref == "wcpp-cpu":  # uso interno: valida a integração whisper.cpp sem GPU (CI)
        key = model_pref if model_pref != "auto" else "small"
        return [EngineChoice("whispercpp", "cpu", key, threads=threads, batch_size=8)]
    have_wcpp = whispercpp_engine.available() and (hw.vulkan_loader or sys.platform != "win32")

    def model_for(vram, dev):
        return model_pref if model_pref != "auto" else auto_model(vram, dev, hw.ram_total_mb)

    nvidia = [g for g in hw.gpus if g.vendor == "nvidia"]
    others = [g for g in hw.gpus if g.vendor != "nvidia" and not g.integrated]
    integrated = [g for g in hw.gpus if g.vendor != "nvidia" and g.integrated]

    if engine_pref in ("auto", "cuda"):
        for g in sorted(nvidia, key=lambda g: -g.vram_total_mb):
            cands.append(EngineChoice("ct2", "cuda", model_for(g.vram_total_mb, "cuda"), g.index, g.name,
                                      threads=threads))
    if engine_pref in ("auto", "vulkan") and have_wcpp:
        vk = sorted(others, key=lambda g: -g.vram_total_mb) + sorted(nvidia, key=lambda g: -g.vram_total_mb)
        if not vk or engine_pref == "vulkan":
            vk += integrated
        for g in vk:
            cands.append(EngineChoice("whispercpp", "vulkan", model_for(g.vram_total_mb, "vulkan"), -1, g.name,
                                      threads=threads, batch_size=16))
        if vk and not nvidia and engine_pref == "auto":
            # plano B sem novo download: o mesmo modelo GGML rodando na CPU
            cands.append(EngineChoice("whispercpp", "cpu", cands[-1].model_key, threads=threads, batch_size=8))
    if engine_pref in ("auto", "cpu") or not cands:
        cands.append(EngineChoice("ct2", "cpu", model_for(0, "cpu"), threads=threads, batch_size=4))
    return cands


def cpu_fallback_for(choice: EngineChoice, hw: hardware.HardwareInfo, profile: str) -> EngineChoice:
    """Plano B na CPU usando o MESMO arquivo de modelo (sem novo download)."""
    t = default_threads(hw, profile)
    if choice.family == "whispercpp":
        return EngineChoice("whispercpp", "cpu", choice.model_key, threads=t, batch_size=8)
    return EngineChoice("ct2", "cpu", choice.model_key, threads=t, batch_size=4)


def missing_components(choice: EngineChoice) -> List[dict]:
    need = []
    if choice.family == "ct2" and choice.device == "cuda" and sys.platform == "win32" and not cuda_libs.installed():
        need.append({"kind": "cuda", "label": "Bibliotecas NVIDIA CUDA (cuBLAS + cuDNN)",
                     "size_mb": 1265})
    if not models.installed(choice.model_key, choice.fmt):
        spec = models.MODELS[choice.model_key]
        size = spec.approx_mb if choice.fmt == "ct2" else int(spec.approx_mb * 0.98)
        need.append({"kind": "model", "key": choice.model_key, "fmt": choice.fmt,
                     "label": f"{spec.label} — formato {'CTranslate2' if choice.fmt == 'ct2' else 'GGML'}",
                     "size_mb": size})
    return need


def install_components(items: List[dict], progress: Callable[[str, int, int], None],
                       cancel: Optional[threading.Event] = None) -> None:
    for it in items:
        if it["kind"] == "cuda":
            cuda_libs.install(progress, cancel)
        elif it["kind"] == "model":
            models.download(it["key"], it["fmt"], progress, cancel)


def make_engine(choice: EngineChoice, work_dir=None) -> Engine:
    if choice.family == "ct2":
        from .engines.ct2_engine import CT2Engine

        e = CT2Engine(choice.model_key, device="cuda" if choice.device == "cuda" else "cpu",
                      compute_type=choice.compute_type, batch_size=choice.batch_size,
                      cpu_threads=choice.threads, device_index=max(0, choice.gpu_index))
        e.gpu_name = choice.gpu_name if choice.device == "cuda" else ""
        return e
    from .engines.whispercpp_engine import WhisperCppEngine

    e = WhisperCppEngine(choice.model_key, use_gpu=choice.device == "vulkan", threads=choice.threads or 4,
                         gpu_device=max(0, choice.gpu_index), work_dir=work_dir)
    e.set_batch_size(choice.batch_size)
    return e


# ------------------------------------------------------------------ calibração
def reference() -> Tuple[np.ndarray, str]:
    a = audio.decode(paths.assets_dir() / "referencia_calibracao.mp3")
    txt = (paths.assets_dir() / "referencia_calibracao.txt").read_text(encoding="utf-8").strip()
    return a, txt


def _tiled(ref: np.ndarray, n: int) -> Tuple[np.ndarray, List[Chunk]]:
    gap = np.zeros(8000, np.float32)
    parts, chunks, t = [], [], 0.0
    L = len(ref) / 16000
    for i in range(n):
        parts += [ref, gap]
        chunks.append(Chunk(i, round(t, 3), round(t + L, 3)))
        t += L + 0.5
    return np.concatenate(parts), chunks


def _measure(engine: Engine, ref: np.ndarray, ref_txt: str, n: int, opts: DecodeOptions,
             cancel: Optional[threading.Event]) -> Tuple[float, float]:
    a, chunks = _tiled(ref, n)
    t0 = time.perf_counter()
    res = engine.transcribe(a, chunks, opts, cancel=cancel)
    el = max(1e-6, time.perf_counter() - t0)
    speed = sum(c.duration for c in chunks) / el
    txt = " ".join(s.text for s in res[0].segments)
    return speed, metrics.wer(ref_txt, txt)


def _batch_ladder(choice: EngineChoice, vram_mb: int) -> List[int]:
    if choice.device == "cuda":
        if vram_mb >= 14000:
            return [1, 8, 16, 24]
        if vram_mb >= 10000:
            return [1, 8, 12, 16]
        if vram_mb >= 7000:
            return [1, 4, 8, 12]
        return [1, 2, 4]
    return [choice.batch_size]


MAX_VALID_WER = 0.8  # acima disso o motor produziu lixo -> backend reprovado


def calibrate(choice: EngineChoice, hw: hardware.HardwareInfo, notify: Notify,
              cancel: Optional[threading.Event] = None) -> Tuple[EngineChoice, Engine]:
    """Executa transcrição real de referência; devolve escolha validada e motor carregado."""
    ref, ref_txt = reference()
    opts = DecodeOptions(language="pt", prompt="", beam_size=5)
    gpu_vram = next((g.vram_total_mb for g in hw.gpus if g.name == choice.gpu_name), 0)

    if choice.family == "whispercpp" and choice.device == "vulkan":
        # o ggml-vulkan expõe as GPUs dedicadas (ou a 1ª integrada, se não houver
        # dedicada); testamos cada uma e ficamos com a mais rápida que usou a GPU
        n_dev = max(1, len([g for g in hw.gpus if not g.integrated]))
        best: Optional[Tuple[float, int, float]] = None
        for dev in range(n_dev):
            c = EngineChoice(**{**choice.to_dict(), "gpu_index": dev})
            eng = make_engine(c)
            eng.load()
            notify(f"Testando Vulkan (dispositivo {dev})…")
            try:
                speed, w = _measure(eng, ref, ref_txt, 4, opts, cancel)
            except (EngineError, GpuFailure, GpuOutOfMemory) as e:
                log.warning("Vulkan dev %d falhou: %s", dev, e)
                continue
            log.info("Vulkan dev %d: %.1fx, WER %.2f, backend %s, gpu=%s", dev, speed, w,
                     eng.actual_backend, eng.gpu_name)
            choice.measurements.append({"vulkan_device": dev, "speed_x": round(speed, 2), "wer": round(w, 3),
                                        "gpu": eng.gpu_name, "backend": eng.actual_backend})
            if eng.uses_gpu and w <= MAX_VALID_WER and (best is None or speed > best[0]):
                best = (speed, dev, w)
            if eng.gpu_name and choice.gpu_name and choice.gpu_name.lower()[:12] in eng.gpu_name.lower():
                break
        if best is None:
            raise GpuFailure("whisper.cpp não conseguiu usar a GPU via Vulkan")
        choice.gpu_index, choice.rtf, choice.wer_ref = best[1], best[0], best[2]
        choice.validated = True
        eng = make_engine(choice)
        eng.load()
        return choice, eng

    eng = make_engine(choice)
    notify(f"Carregando {models.MODELS[choice.model_key].label} ({choice.accel})…")
    eng.load()
    if isinstance(getattr(eng, "compute_type", None), str):
        choice.compute_type = eng.compute_type
    # aquecimento (inicialização de kernels) + validação de texto
    notify(f"Validando {choice.accel} com áudio de referência…")
    eng.set_batch_size(1)
    speed, w = _measure(eng, ref, ref_txt, 1, opts, cancel)
    if w > MAX_VALID_WER:
        raise GpuFailure(f"Saída inválida no teste (WER {w:.2f})") if choice.is_gpu else \
            EngineError(f"Saída inválida no teste (WER {w:.2f})")
    choice.wer_ref = w
    best_bs, best_speed = 1, speed
    if choice.device == "cuda":
        for bs in _batch_ladder(choice, gpu_vram):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            eng.set_batch_size(bs)
            notify(f"Calibrando lote de {bs} blocos na GPU…")
            try:
                s, _ = _measure(eng, ref, ref_txt, max(2, bs * 2), opts, cancel)
            except GpuOutOfMemory:
                choice.measurements.append({"batch": bs, "oom": True})
                break
            free = hardware.nvidia_free_vram_mb(max(0, choice.gpu_index))
            choice.measurements.append({"batch": bs, "speed_x": round(s, 2), "vram_free_mb": free})
            if s > best_speed * 1.05:
                best_bs, best_speed = bs, s
    else:
        bs = choice.batch_size
        eng.set_batch_size(bs)
        notify("Medindo velocidade na CPU…")
        s, _ = _measure(eng, ref, ref_txt, 2, opts, cancel)
        choice.measurements.append({"batch": bs, "speed_x": round(s, 2)})
        best_bs, best_speed = bs, s
    choice.batch_size, choice.rtf, choice.validated = best_bs, best_speed, True
    eng.set_batch_size(best_bs)
    log.info("Calibração %s: lote %d, %.1fx tempo real", choice.key(), best_bs, best_speed)
    return choice, eng


# ------------------------------------------------------------------ perfil salvo
def _profile_path():
    return paths.config_dir() / "perfil_hardware.json"


def load_profile(fp: str, model_pref: str, engine_pref: str) -> Optional[EngineChoice]:
    p = _profile_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        d = data.get(fp, {}).get(f"{model_pref}|{engine_pref}")
        if d and d.get("calib_version", d.get("app_version")) in (CALIBRATION_VERSION, "1.0.0"):
            d = {k: v for k, v in d.items() if k not in ("app_version", "calib_version")}
            return EngineChoice.from_dict(d)
    except Exception:  # noqa: BLE001
        return None
    return None


def save_profile(fp: str, model_pref: str, engine_pref: str, choice: EngineChoice) -> None:
    p = _profile_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        data = {}
    data.setdefault(fp, {})[f"{model_pref}|{engine_pref}"] = {**choice.to_dict(), "calib_version": CALIBRATION_VERSION,
                                                       "app_version": __version__}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def forget_profiles() -> None:
    _profile_path().unlink(missing_ok=True)


# ------------------------------------------------------------------ prioridade do processo
def set_process_priority(profile: str) -> None:
    try:
        import psutil

        proc = psutil.Process()
        if sys.platform == "win32":
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if profile == "trabalho" else psutil.NORMAL_PRIORITY_CLASS)
        elif profile == "trabalho":
            proc.nice(max(proc.nice(), 10))
    except Exception as e:  # noqa: BLE001
        log.debug("Prioridade não alterada: %s", e)


# ------------------------------------------------------------------ gerenciador em execução
class EngineManager:
    def __init__(self, hw: hardware.HardwareInfo, model_pref: str = "auto", engine_pref: str = "auto",
                 profile: str = "turbo", notify: Optional[Notify] = None):
        self.hw = hw
        self.model_pref = model_pref
        self.engine_pref = engine_pref
        self.profile = profile
        self.notify = notify or (lambda m: None)
        self.choice: Optional[EngineChoice] = None
        self.engine: Optional[Engine] = None
        self.full_batch = 1
        self.events: List[str] = []
        self._lock = threading.Lock()

    # ---- seleção
    def candidates(self) -> List[EngineChoice]:
        return build_candidates(self.hw, self.model_pref, self.engine_pref, self.profile)

    def pending_downloads(self) -> List[dict]:
        """Componentes que faltam para o melhor candidato (para pedir consentimento)."""
        cands = self.candidates()
        return missing_components(cands[0]) if cands else []

    def start(self, cancel: Optional[threading.Event] = None) -> EngineChoice:
        fp = self.hw.fingerprint()
        saved = load_profile(fp, self.model_pref, self.engine_pref)
        if saved is not None and not missing_components(saved):
            try:
                eng = make_engine(saved)
                self.notify(f"Carregando {models.MODELS[saved.model_key].label} ({saved.accel})…")
                eng.load()
                self._set(saved, eng)
                return saved
            except (EngineError, GpuFailure, GpuOutOfMemory) as e:
                log.warning("Perfil salvo falhou (%s); recalibrando", e)
                self.events.append(f"Configuração anterior falhou ({e}); nova calibração realizada.")
        errors = []
        for c in self.candidates():
            if missing_components(c):
                log.info("Candidato %s ignorado: componentes ausentes", c.key())
                continue
            try:
                self.notify(f"Calibrando {c.accel} — primeira execução neste computador…")
                c, eng = calibrate(c, self.hw, self.notify, cancel)
                save_profile(fp, self.model_pref, self.engine_pref, c)
                self._set(c, eng)
                return c
            except Cancelled:
                raise
            except (EngineError, GpuFailure, GpuOutOfMemory) as e:
                errors.append(f"{c.accel}: {e}")
                log.warning("Candidato %s reprovado: %s", c.key(), e)
                self.events.append(f"{c.accel} ({c.gpu_name or 'CPU'}) indisponível: {str(e)[:160]}")
        raise EngineError("Nenhum mecanismo de transcrição funcionou:\n" + "\n".join(errors))

    def _set(self, choice: EngineChoice, eng: Engine) -> None:
        self.choice, self.engine = choice, eng
        self.full_batch = choice.batch_size
        self.apply_profile(self.profile)

    def apply_profile(self, profile: str) -> None:
        self.profile = profile
        set_process_priority(profile)
        if self.engine is None:
            return
        bs = self.full_batch if profile == "turbo" else max(1, self.full_batch // 2)
        self.engine.set_batch_size(bs)
        self.engine.set_threads(default_threads(self.hw, profile))

    def info(self) -> Dict[str, str]:
        c, e = self.choice, self.engine
        d = {"cpu": self.hw.cpu_name, "ram": f"{self.hw.ram_total_mb / 1024:.0f} GB"}
        if c and e:
            d["modelo"] = models.MODELS[c.model_key].label.split(" (")[0]
            d["aceleracao"] = e.accel if e.family == "whispercpp" else c.accel
            if (e.uses_gpu or c.device == "cuda") and c.device != "cpu":
                g = next((g for g in self.hw.gpus if g.name == c.gpu_name), None)
                d["gpu"] = e.gpu_name or c.gpu_name
                if g and g.vram_total_mb:
                    d["vram"] = f"{g.vram_total_mb / 1024:.0f} GB"
            else:
                d["gpu"] = "não utilizada (processamento na CPU)"
            d["lote"] = str(e.batch_size)
            d["velocidade"] = f"{c.rtf:.1f}× tempo real (calibração)" if c.rtf else ""
        return d

    # ---- execução com recuperação
    def transcribe(self, audio_arr, chunks, opts, progress=None, cancel=None) -> List[ChunkResult]:
        with self._lock:
            while True:
                eng = self.engine
                if eng is None:
                    raise EngineError("Motor não iniciado")
                try:
                    return eng.transcribe(audio_arr, chunks, opts, progress, cancel)
                except GpuOutOfMemory as e:
                    if eng.batch_size > 1:
                        nb = max(1, eng.batch_size // 2)
                        self.full_batch = max(1, min(self.full_batch, nb if self.profile == "turbo" else nb * 2))
                        eng.set_batch_size(nb)
                        msg = f"Memória de vídeo no limite: lote reduzido para {nb}."
                        log.warning("%s (%s)", msg, e)
                        self.notify(msg)
                        self.events.append(msg)
                        continue
                    if getattr(eng, "compute_type", "") == "float16":
                        self.notify("Memória de vídeo insuficiente: usando precisão INT8/FP16.")
                        eng.close()
                        eng.compute_type = "int8_float16"
                        eng.load()
                        self.choice.compute_type = "int8_float16"
                        continue
                    self._fallback_cpu(f"memória de vídeo insuficiente ({e})")
                except GpuFailure as e:
                    self._fallback_cpu(str(e))

    def _fallback_cpu(self, reason: str) -> None:
        if self.choice is None or not self.choice.is_gpu:
            raise EngineError(f"Falha no processamento: {reason}")
        fb = cpu_fallback_for(self.choice, self.hw, self.profile)
        msg = f"A GPU falhou ({reason[:140]}). Continuando automaticamente na CPU — mais lento."
        log.error(msg)
        self.notify(msg)
        self.events.append(msg)
        try:
            if self.engine:
                self.engine.close()
        except Exception:  # noqa: BLE001
            pass
        eng = make_engine(fb)
        eng.load()
        fb.validated = True
        self.choice, self.engine = fb, eng
        self.full_batch = fb.batch_size
        self.apply_profile(self.profile)
        # a próxima abertura recalibra (a GPU pode ter sido desconectada)
        forget_profiles()

    def close(self) -> None:
        if self.engine:
            self.engine.close()
        self.engine = None
