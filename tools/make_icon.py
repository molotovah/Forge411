"""Génère l'icône de Forge411 (PNG + ICO) dans forge411/assets/. Usage : python tools/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "forge411" / "assets"
S = 1024


WIN_FONTS = Path("/mnt/c/Windows/Fonts")      # polices Windows depuis WSL

# Couleurs du logo C411 (vert foncé → vert clair)
GREEN_DARK = (15, 92, 47)
GREEN = (25, 126, 61)
GREEN_LIGHT = (115, 200, 77)


def font(size):
    for name in ("seguibl.ttf", "segoeuib.ttf", "arialbd.ttf", str(WIN_FONTS / "seguibl.ttf"), "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Fond : carré arrondi, dégradé vert foncé → vert C411
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        c = tuple(int(a + (b - a) * t) for a, b in zip(GREEN_DARK, GREEN)) + (255,)
        gd.line([(0, y), (S, y)], fill=c)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)
    # Étincelle de forge (losange) en haut à droite
    cx, cy, r = 760, 250, 90
    d.polygon([(cx, cy - r), (cx + r * 0.35, cy), (cx, cy + r), (cx - r * 0.35, cy)], fill=GREEN_LIGHT + (255,))
    d.polygon([(cx - r, cy), (cx, cy - r * 0.35), (cx + r, cy), (cx, cy + r * 0.35)], fill=GREEN_LIGHT + (255,))
    # Monogramme
    f = font(560)
    d.text((S / 2 - 20, S / 2 + 40), "F", font=f, fill=(255, 255, 255, 255), anchor="mm")
    f2 = font(170)
    d.text((S / 2 + 160, S - 210), "411", font=f2, fill=GREEN_LIGHT + (255,), anchor="mm")
    OUT.mkdir(parents=True, exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(OUT / "forge411.png")
    img.save(OUT / "forge411.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icône écrite dans", OUT)


if __name__ == "__main__":
    make()
