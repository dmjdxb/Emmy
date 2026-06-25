#!/usr/bin/env python3
"""Generate Emmy's app icon: a 4-fold-symmetric quatrefoil (Noether symmetry /
conservation motif) on a deep-green -> EnergyIR-green tile. Pure procedural render
so the geometry is exactly symmetric and crisp at every size. Builds .icns/.ico/.png.

Run: .venv-arm2/bin/python scripts/make_emmy_icon.py
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
SS = 4                      # supersample factor
S = 1024                    # final master size
N = S * SS                  # working canvas

TOP = (16, 45, 34)          # deep green   #102d22  (EnergyIR)
BOT = (58, 166, 118)        # energy green #3aa676  (EnergyIR)
INK = (236, 253, 245)       # emerald-white #ECFDF5


def rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def vertical_gradient(size: int, top, bot) -> Image.Image:
    base = Image.new("RGB", (size, size), top)
    px = base.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return base


def build_master() -> Image.Image:
    # Gradient tile on the working (supersampled) canvas.
    tile = vertical_gradient(N, TOP, BOT)

    # Glyph layer (RGBA) so we can stroke smooth rings then composite.
    glyph = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    c = N / 2
    r = 0.205 * N           # petal circle radius
    d = 0.150 * N           # petal center offset from middle
    w = int(0.040 * N)      # ring stroke width
    # Quatrefoil: four overlapping ring outlines at N/E/S/W -> 4-fold symmetry.
    for ang in (0, 90, 180, 270):
        cx = c + d * math.cos(math.radians(ang))
        cy = c + d * math.sin(math.radians(ang))
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=w)
    # Thin framing ring + center dot for balance.
    rr = 0.40 * N
    gd.ellipse([c - rr, c - rr, c + rr, c + rr], outline=INK, width=int(0.018 * N))
    cr = 0.045 * N
    gd.ellipse([c - cr, c - cr, c + cr, c + cr], fill=INK)

    tile = tile.convert("RGBA")
    tile.alpha_composite(glyph)

    # Apply rounded-square (squircle-ish) mask.
    mask = rounded_mask(N, int(0.2235 * N))
    out = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    out.paste(tile, (0, 0), mask)

    return out.resize((S, S), Image.LANCZOS)


def main() -> None:
    master = build_master()
    targets = [
        REPO / "apps/desktop/assets",
        REPO / "apps/bootstrap-installer/src-tauri/icons",
    ]
    for dest in targets:
        dest.mkdir(parents=True, exist_ok=True)
        # icon.png (1024) + icon.ico (multi-size)
        master.save(dest / "icon.png")
        master.save(
            dest / "icon.ico",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        # .iconset -> .icns via iconutil
        iconset = dest / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        spec = [
            (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
        ]
        for sz, name in spec:
            master.resize((sz, sz), Image.LANCZOS).save(iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(dest / "icon.icns")],
            check=True,
        )
        # Tauri also references plain size-named PNGs.
        for sz, name in [(32, "32x32.png"), (128, "128x128.png"), (256, "128x128@2x.png")]:
            p = dest / name
            if dest.name == "icons" or p.exists():
                master.resize((sz, sz), Image.LANCZOS).save(p)
        print(f"wrote icon set -> {dest}")


if __name__ == "__main__":
    main()
