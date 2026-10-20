"""Detecção real do hardware (CPU, RAM, GPUs).

Nada aqui é fixo: tudo vem do sistema operacional. No Windows usamos o registro
(nome da CPU, adaptadores de vídeo e VRAM de 64 bits), IsProcessorFeaturePresent
(AVX/AVX2/AVX-512) e o nvidia-smi que acompanha o driver NVIDIA (VRAM livre).
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import psutil

from . import logs

log = logs.get("hardware")
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

VENDOR_IDS = {"10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel"}

# adaptadores virtuais/remotos que não servem para inferência
_IGNORE_ADAPTERS = re.compile(
    r"basic display|basic render|remote|virtual|parsec|meta virtual|spacedesk|"
    r"idd|indirect|citrix|vmware|virtualbox|hyper-v|displaylink|luminon",
    re.I,
)


@dataclass
class GPUInfo:
    vendor: str
    name: str
    vram_total_mb: int = 0
    vram_free_mb: Optional[int] = None
    index: int = 0  # índice dentro do fabricante (CUDA) — Vulkan usa ordem própria
    integrated: bool = False
    driver: str = ""

    @property
    def label(self) -> str:
        return self.name


@dataclass
class HardwareInfo:
    os_name: str = ""
    cpu_name: str = ""
    cpu_vendor: str = ""
    cores_physical: int = 1
    threads: int = 1
    cpu_features: List[str] = field(default_factory=list)
    cpu_load_percent: float = 0.0
    ram_total_mb: int = 0
    ram_free_mb: int = 0
    gpus: List[GPUInfo] = field(default_factory=list)
    vulkan_loader: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def nvidia_gpus(self) -> List[GPUInfo]:
        return [g for g in self.gpus if g.vendor == "nvidia"]

    @property
    def discrete_gpus(self) -> List[GPUInfo]:
        return [g for g in self.gpus if not g.integrated]

    def best_gpu(self) -> Optional[GPUInfo]:
        cands = sorted(self.gpus, key=lambda g: (not g.integrated, g.vram_total_mb), reverse=True)
        return cands[0] if cands else None

    def fingerprint(self) -> str:
        """Identidade do computador para reutilizar a calibração.

        Muda quando o usuário troca de PC, conecta uma eGPU ou troca a placa.
        """
        key = {
            "cpu": self.cpu_name,
            "threads": self.threads,
            "ram_gb": round(self.ram_total_mb / 1024),
            "gpus": sorted(f"{g.vendor}|{g.name}|{round(g.vram_total_mb / 1024)}" for g in self.gpus),
        }
        return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def _run(cmd: List[str], timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW, encoding="utf-8", errors="replace",
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- CPU
def _cpu_name() -> str:
    if IS_WINDOWS:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    elif os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    return platform.processor() or "CPU desconhecida"


def _cpu_features() -> List[str]:
    feats: List[str] = []
    if IS_WINDOWS:
        try:
            k32 = ctypes.windll.kernel32
            for name, pf in (("SSE4.1", 37), ("SSE4.2", 38), ("AVX", 39), ("AVX2", 40), ("AVX-512", 41)):
                if k32.IsProcessorFeaturePresent(pf):
                    feats.append(name)
        except Exception:
            pass
    elif os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        m = re.search(r"^flags\s*:\s*(.*)$", txt, re.M)
        flags = set(m.group(1).split()) if m else set()
        for name, fl in (("SSE4.1", "sse4_1"), ("SSE4.2", "sse4_2"), ("AVX", "avx"),
                         ("AVX2", "avx2"), ("AVX-512", "avx512f"), ("AVX-VNNI", "avx_vnni")):
            if fl in flags:
                feats.append(name)
    return feats


def _cpu_vendor(name: str) -> str:
    n = name.lower()
    if "intel" in n:
        return "Intel"
    if "amd" in n or "ryzen" in n:
        return "AMD"
    return platform.machine()


# ---------------------------------------------------------------- GPU
def _nvidia_smi() -> List[GPUInfo]:
    exe = shutil.which("nvidia-smi")
    if not exe and IS_WINDOWS:
        cand = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        exe = cand if os.path.exists(cand) else None
    if not exe:
        return []
    out = _run([exe, "--query-gpu=index,name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            gpus.append(GPUInfo(vendor="nvidia", name=parts[1], index=int(parts[0]),
                                vram_total_mb=int(float(parts[2])), vram_free_mb=int(float(parts[3])),
                                driver=parts[4]))
        except ValueError:
            continue
    return gpus


def _windows_adapters() -> List[GPUInfo]:
    gpus: List[GPUInfo] = []
    try:
        import winreg
    except ImportError:
        return gpus
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return gpus
    seen = set()
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        if not sub.isdigit():
            continue
        try:
            with winreg.OpenKey(root, sub) as k:
                def val(n, default=None):
                    try:
                        return winreg.QueryValueEx(k, n)[0]
                    except OSError:
                        return default

                name = str(val("DriverDesc", "") or "")
                dev_id = str(val("MatchingDeviceId", "") or "").lower()
                if not name or _IGNORE_ADAPTERS.search(name):
                    continue
                m = re.search(r"ven_([0-9a-f]{4})", dev_id)
                vendor = VENDOR_IDS.get(m.group(1), "other") if m else "other"
                mem = val("HardwareInformation.qwMemorySize")
                if mem is None:
                    mem = val("HardwareInformation.MemorySize", 0)
                if isinstance(mem, (bytes, bytearray)):
                    mem = int.from_bytes(mem[:8], "little")
                vram = int(mem or 0) // (1024 * 1024)
                key = (name, vram)
                if key in seen:
                    continue
                seen.add(key)
                gpus.append(GPUInfo(vendor=vendor, name=name, vram_total_mb=vram,
                                    driver=str(val("DriverVersion", "") or "")))
        except OSError:
            continue
    return gpus


def _is_integrated(g: GPUInfo) -> bool:
    n = g.name.lower()
    if g.vendor == "intel":
        return "arc" not in n or bool(re.search(r"arc\(tm\) graphics$|arc graphics$", n))
    if g.vendor == "amd":
        # "AMD Radeon(TM) Graphics", "Radeon 780M/890M" = integradas; RX xxxx = dedicadas
        return not re.search(r"\brx\b|radeon pro|instinct|\bw\d{4}", n)
    if g.vendor == "nvidia":
        return False
    return g.vram_total_mb < 1024


def _vulkan_loader_present() -> bool:
    try:
        if IS_WINDOWS:
            ctypes.WinDLL("vulkan-1.dll")
        else:
            ctypes.CDLL("libvulkan.so.1")
        return True
    except OSError:
        return False


def detect() -> HardwareInfo:
    hw = HardwareInfo()
    hw.os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
    hw.cpu_name = _cpu_name()
    hw.cpu_vendor = _cpu_vendor(hw.cpu_name)
    hw.cores_physical = psutil.cpu_count(logical=False) or 1
    hw.threads = psutil.cpu_count(logical=True) or hw.cores_physical
    hw.cpu_features = _cpu_features()
    try:
        hw.cpu_load_percent = psutil.cpu_percent(interval=0.3)
    except Exception:
        pass
    vm = psutil.virtual_memory()
    hw.ram_total_mb = vm.total // (1024 * 1024)
    hw.ram_free_mb = vm.available // (1024 * 1024)

    nvidia = _nvidia_smi()
    adapters = _windows_adapters() if IS_WINDOWS else []
    gpus: List[GPUInfo] = list(nvidia)
    # adiciona AMD/Intel/outros do registro (NVIDIA já veio do nvidia-smi, com VRAM livre)
    for a in adapters:
        if a.vendor == "nvidia" and nvidia:
            continue
        gpus.append(a)
    for g in gpus:
        g.integrated = _is_integrated(g)
    hw.gpus = gpus
    hw.vulkan_loader = _vulkan_loader_present()
    log.info("Hardware detectado: %s", json.dumps(hw.to_dict(), ensure_ascii=False))
    return hw


def nvidia_free_vram_mb(index: int = 0) -> Optional[int]:
    for g in _nvidia_smi():
        if g.index == index:
            return g.vram_free_mb
    return None


def describe(hw: HardwareInfo) -> List[str]:
    lines = [f"CPU: {hw.cpu_name} ({hw.cores_physical} núcleos / {hw.threads} threads)",
             f"RAM: {hw.ram_total_mb / 1024:.0f} GB ({hw.ram_free_mb / 1024:.1f} GB livres)"]
    if not hw.gpus:
        lines.append("GPU: nenhuma placa de vídeo compatível detectada")
    for g in hw.gpus:
        tipo = "integrada" if g.integrated else "dedicada"
        vram = f"{g.vram_total_mb / 1024:.0f} GB" if g.vram_total_mb else "VRAM n/d"
        lines.append(f"GPU: {g.name} ({vram}, {tipo})")
    return lines


if __name__ == "__main__":  # diagnóstico rápido
    logs.setup(verbose=True)
    h = detect()
    print("\n".join(describe(h)))
    print("Recursos CPU:", ", ".join(h.cpu_features))
    print("Vulkan loader:", h.vulkan_loader, "| impressão digital:", h.fingerprint())
