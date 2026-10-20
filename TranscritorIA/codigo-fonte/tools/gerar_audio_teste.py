"""Gera áudios sintéticos em português (eSpeak NG) com texto de referência conhecido.

Uso:
  python tools/gerar_audio_teste.py referencia   -> assets/referencia_calibracao.mp3 (+ .txt)
  python tools/gerar_audio_teste.py aula SAIDA.mp3 MINUTOS [--ruido] [--silencio SEG]
     aula sintética longa com terminologia médica e "partitura" JSON (início/fim de cada frase)

Requer: pip install espeakng-loader numpy av
"""
from __future__ import annotations

import ctypes
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

REFERENCIA = (
    "Bom dia, pessoal. Hoje vamos estudar a pré-eclâmpsia, uma síndrome hipertensiva da gestação. "
    "Ela aparece depois da vigésima semana e pode evoluir para eclâmpsia. "
    "O tratamento inclui sulfato de magnésio e controle da pressão arterial."
)

FRASES = [
    "Bom dia, pessoal, vamos começar a aula de obstetrícia.",
    "A pré-eclâmpsia é definida pela hipertensão arterial após a vigésima semana de gestação.",
    "Na ultrassonografia avaliamos a biometria fetal e o volume de líquido amniótico.",
    "O Doppler da artéria umbilical ajuda a identificar a restrição de crescimento fetal.",
    "O sulfato de magnésio é usado na prevenção da eclâmpsia.",
    "A ocitocina é a primeira escolha na prevenção da hemorragia pós-parto.",
    "O diabetes gestacional é rastreado com a curva glicêmica entre vinte e quatro e vinte e oito semanas.",
    "A placenta prévia costuma causar sangramento indolor no terceiro trimestre.",
    "O corticoide antenatal reduz a síndrome do desconforto respiratório do recém-nascido.",
    "A cardiotocografia avalia a frequência cardíaca fetal e as contrações uterinas.",
    "Pacientes com Rh negativo devem receber imunoglobulina anti-D quando indicado.",
    "A toxoplasmose e a sífilis devem ser investigadas em todo pré-natal.",
    "O partograma registra a evolução do trabalho de parto.",
    "A betametasona atravessa a placenta e acelera a maturação pulmonar.",
    "A hemorragia pós-parto é uma das principais causas de morte materna.",
    "Vamos agora discutir os casos clínicos da semana.",
]


class Espeak:
    def __init__(self, voice: str = "pt-br", rate: int = 165):
        import espeakng_loader as el

        self.lib = ctypes.CDLL(el.get_library_path())
        self.sr = self.lib.espeak_Initialize(0x02, 0, el.get_data_path().encode(), 0)  # SYNCHRONOUS
        if self.sr <= 0:
            raise RuntimeError("espeak_Initialize falhou")
        self.buf: list = []
        CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)

        def cb(wav, n, _ev):
            if n > 0:
                self.buf.append(np.ctypeslib.as_array(wav, shape=(n,)).copy())
            return 0

        self._cb = CB(cb)
        self.lib.espeak_SetSynthCallback(self._cb)
        self.lib.espeak_SetVoiceByName(voice.encode())
        self.lib.espeak_SetParameter(1, rate, 0)  # espeakRATE

    def say(self, text: str) -> np.ndarray:
        self.buf = []
        b = text.encode("utf-8")
        self.lib.espeak_Synth(b, len(b) + 1, 0, 1, 0, 1, None, None)  # POS_CHARACTER, CHARS_UTF8
        pcm = np.concatenate(self.buf) if self.buf else np.zeros(1, np.int16)
        return pcm.astype(np.float32) / 32768.0


def resample(x: np.ndarray, sr_in: int, sr_out: int = 16000) -> np.ndarray:
    n = int(len(x) * sr_out / sr_in)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def save_audio(path: Path, x: np.ndarray, sr: int = 16000) -> None:
    import av

    path.parent.mkdir(parents=True, exist_ok=True)
    codec = {".mp3": "mp3", ".wav": "pcm_s16le", ".m4a": "aac", ".ogg": "libvorbis"}[path.suffix.lower()]
    with av.open(str(path), "w") as out:
        st = out.add_stream(codec, rate=sr)
        st.layout = "mono"
        pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
        step = 1152 * 8
        for i in range(0, len(pcm), step):
            fr = av.AudioFrame.from_ndarray(pcm[i:i + step].reshape(1, -1), format="s16", layout="mono")
            fr.sample_rate = sr
            for p in st.encode(fr):
                out.mux(p)
        for p in st.encode(None):
            out.mux(p)


def make_reference() -> None:
    es = Espeak()
    x = resample(es.say(REFERENCIA), es.sr)
    x = np.concatenate([np.zeros(8000, np.float32), x * 0.9, np.zeros(8000, np.float32)])
    save_audio(ROOT / "assets" / "referencia_calibracao.mp3", x)
    (ROOT / "assets" / "referencia_calibracao.txt").write_text(REFERENCIA + "\n", encoding="utf-8")
    print(f"referência: {len(x) / 16000:.1f} s")


def words_script(sentences):
    """Converte (início, fim, frase) em (início, fim, palavra) proporcional ao tamanho."""
    out = []
    for s, e, text in sentences:
        words = text.split()
        weights = [len(w) + 1 for w in words]
        tot = sum(weights)
        t = s
        for w, wt in zip(words, weights):
            d = (e - s) * wt / tot
            out.append([round(t, 3), round(t + d, 3), w])
            t += d
    return out


def make_lecture(out: Path, minutes: float, noise: bool = False, long_silence: float = 0.0,
                 seed: int = 7) -> None:
    rng = random.Random(seed)
    es = Espeak()
    said = {f: resample(es.say(f), es.sr) for f in FRASES}
    target = minutes * 60 * 16000
    parts, script, t = [], [], 0
    k = 0
    while t < target:
        f = FRASES[k % len(FRASES)]
        k += 1
        a = said[f]
        start = t / 16000
        parts.append(a)
        t += len(a)
        script.append([round(start, 3), round(t / 16000, 3), f])
        gap = int(rng.uniform(0.25, 1.6) * 16000)
        if long_silence and k == 6:
            gap = int(long_silence * 16000)
        parts.append(np.zeros(gap, np.float32))
        t += gap
    x = np.concatenate(parts)
    if noise:
        x = x + np.random.default_rng(seed).normal(0, 0.02, len(x)).astype(np.float32)
    save_audio(out, x)
    out.with_suffix(".json").write_text(json.dumps(words_script(script), ensure_ascii=False), encoding="utf-8")
    print(f"{out.name}: {len(x) / 16000 / 60:.1f} min, {len(script)} frases")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "referencia":
        make_reference()
    elif len(sys.argv) >= 4 and sys.argv[1] == "aula":
        sil = 0.0
        if "--silencio" in sys.argv:
            sil = float(sys.argv[sys.argv.index("--silencio") + 1])
        make_lecture(Path(sys.argv[2]), float(sys.argv[3]), "--ruido" in sys.argv, sil)
    else:
        print(__doc__)
