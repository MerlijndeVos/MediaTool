"""Render raster icons from the shared Media Tool artwork."""

from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

PRIMARY = tuple(
    int(round(c * 255))
    for c in colorsys.hls_to_rgb(221 / 360, 0.53, 0.83)
)
FOREGROUND = (248, 250, 252)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = max(1, round(size * 10 / 36))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=PRIMARY + (255,))

    pad = size * 8 / 36
    scale = size * 20 / 36 / 24
    stroke = max(1, round(2 * scale))

    def pt(x: float, y: float) -> tuple[float, float]:
        return pad + x * scale, pad + y * scale

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        draw.line([pt(x1, y1), pt(x2, y2)], fill=FOREGROUND + (255,), width=stroke)

    x1, y1 = pt(3, 3)
    x2, y2 = pt(21, 21)
    draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=2 * scale,
        outline=FOREGROUND + (255,),
        width=stroke,
    )
    line(7, 3, 7, 21)
    line(17, 3, 17, 21)
    line(3, 7.5, 7, 7.5)
    line(3, 12, 21, 12)
    line(3, 16.5, 7, 16.5)
    line(17, 7.5, 21, 7.5)
    line(17, 16.5, 21, 16.5)
    return img


def main() -> None:
    png_path = HERE / "media-tool.png"
    ico_path = HERE / "media-tool.ico"
    favicon_path = HERE.parent.parent / "web" / "frontend" / "public" / "favicon-32.png"
    sizes = [16, 32, 48, 64, 128, 256]

    draw_icon(256).save(png_path, format="PNG")
    draw_icon(256).save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
    )
    draw_icon(32).save(favicon_path, format="PNG")
    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")
    print(f"Wrote {favicon_path}")


if __name__ == "__main__":
    main()
