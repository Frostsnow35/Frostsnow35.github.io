#!/usr/bin/env python3
"""生成社交分享图 public/og.png（1200x630），与站内色场同色。

用法：
    python scripts/build_og.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "og.png"
FONT = ROOT / ".fontwork" / "shs.otf"

W, H = 1200, 630
STOPS = [
    (0.00, (0xF5, 0x81, 0x1F)),
    (0.26, (0xF0, 0xA4, 0x5E)),
    (0.47, (0xCF, 0xD2, 0xBF)),
    (0.70, (0x8F, 0xD4, 0xE3)),
    (1.00, (0x3C, 0xC3, 0xE8)),
]
INK = (0x14, 0x16, 0x1A)
DIM = (0x14, 0x16, 0x1A)


def gradient() -> Image.Image:
    # 对齐 CSS 的 101deg：向右偏上
    xs = np.linspace(0, 1, W)[None, :]
    ys = np.linspace(0, 1, H)[:, None]
    t = (xs * 0.98 + ys * 0.19)
    t = (t - t.min()) / (t.max() - t.min())

    pos = np.array([s[0] for s in STOPS])
    cols = np.array([s[1] for s in STOPS], dtype=float)
    r = np.interp(t, pos, cols[:, 0])
    g = np.interp(t, pos, cols[:, 1])
    b = np.interp(t, pos, cols[:, 2])
    arr = np.stack([r, g, b], axis=-1).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def main() -> None:
    img = gradient()
    d = ImageDraw.Draw(img)

    name_font = ImageFont.truetype(str(FONT), 168)
    tag_font = ImageFont.truetype(str(FONT), 34)
    url_font = ImageFont.truetype(str(FONT), 22)

    x = 92
    y_name = 200
    name = "Frostsnow"
    d.text((x, y_name), name, font=name_font, fill=INK)
    bottom = d.textbbox((x, y_name), name, font=name_font)[3]

    # 名字与签名之间留白，不加分隔线：左对齐下短横会被读成下划线
    d.text((x, bottom + 42), "Ce bas monde est le paradis unique.", font=tag_font, fill=DIM)

    url = "frostsnow35.github.io"
    w = d.textlength(url, font=url_font)
    d.text((W - 92 - w, H - 76), url, font=url_font, fill=(0x14, 0x16, 0x1A))

    img.save(OUT, optimize=True)
    print(f"{OUT} {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
