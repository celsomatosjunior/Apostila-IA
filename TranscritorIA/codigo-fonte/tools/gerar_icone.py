"""Gera assets/icone.ico: faixa de fala (barras) sobre um quadrado azul-metileno."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BLUE, WHITE, SOFT = (36, 80, 143, 255), (255, 255, 255, 255), (163, 190, 228, 255)


def draw(size: int) -> Image.Image:
    s = 4 * size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BLUE)
    heights = [0.22, 0.46, 0.70, 0.40, 0.58, 0.30, 0.16]
    n = len(heights)
    pad = s * 0.17
    w = (s - 2 * pad) / (n * 1.6)
    for i, h in enumerate(heights):
        x = pad + i * w * 1.6 + w * 0.3
        hh = s * h
        col = WHITE if i < 4 else SOFT  # parte esquerda "já transcrita"
        d.rounded_rectangle([x, s / 2 - hh / 2, x + w, s / 2 + hh / 2], radius=w / 2, fill=col)
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    big = draw(256)
    big.save(ROOT / "assets" / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(ROOT / "assets" / "icone.png")
    print("ok")
