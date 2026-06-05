"""Render raster icons from the shared Media Tool artwork."""

from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REFERENCE_SIZE = 36
PRIMARY_HEX = "#2362ea"
FOREGROUND_HEX = "#f7f9fb"


def _icon_metrics(size: int = REFERENCE_SIZE) -> tuple[float, float, float, float]:
    pad = size * 8 / 36
    scale = size * 20 / 36 / 24
    stroke = max(1.0, 2 * scale)
    radius = size * 10 / 36
    return pad, scale, stroke, radius


def _pt(pad: float, scale: float, x: float, y: float) -> tuple[float, float]:
    return pad + x * scale, pad + y * scale


def svg_icon(size: int = REFERENCE_SIZE) -> str:
    pad, scale, stroke, radius = _icon_metrics(size)

    def point(x: float, y: float) -> tuple[float, float]:
        return _pt(pad, scale, x, y)

    x1, y1 = point(3, 3)
    x2, y2 = point(21, 21)
    width = x2 - x1
    icon_rx = 2 * scale

    def line(xa: float, ya: float, xb: float, yb: float) -> str:
        ax, ay = point(xa, ya)
        bx, by = point(xb, yb)
        if xa == xb:
            return f'<path d="M{ax:.3f} {ay:.3f}v{by - ay:.3f}"/>'
        return f'<path d="M{ax:.3f} {ay:.3f}h{bx - ax:.3f}"/>'

    paths = "\n    ".join(
        [
            line(7, 3, 7, 21),
            line(17, 3, 17, 21),
            line(3, 7.5, 7, 7.5),
            line(3, 12, 21, 12),
            line(3, 16.5, 7, 16.5),
            line(17, 7.5, 21, 7.5),
            line(17, 16.5, 21, 16.5),
        ]
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">
  <rect width="{size}" height="{size}" rx="{radius:.3f}" fill="{PRIMARY_HEX}"/>
  <g fill="none" stroke="{FOREGROUND_HEX}" stroke-width="{stroke:.3f}" stroke-linecap="round" stroke-linejoin="round">
    <rect x="{x1:.3f}" y="{y1:.3f}" width="{width:.3f}" height="{width:.3f}" rx="{icon_rx:.3f}"/>
    {paths}
  </g>
</svg>
"""


PRIMARY = tuple(
    int(round(c * 255))
    for c in colorsys.hls_to_rgb(221 / 360, 0.53, 0.83)
)
FOREGROUND = (248, 250, 252)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad, scale, stroke, radius = _icon_metrics(size)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=PRIMARY + (255,))

    def pt(x: float, y: float) -> tuple[float, float]:
        return _pt(pad, scale, x, y)

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        draw.line([pt(x1, y1), pt(x2, y2)], fill=FOREGROUND + (255,), width=max(1, round(stroke)))

    x1, y1 = pt(3, 3)
    x2, y2 = pt(21, 21)
    draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=2 * scale,
        outline=FOREGROUND + (255,),
        width=max(1, round(stroke)),
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
    svg_path = HERE / "media-tool.svg"
    favicon_svg_path = HERE.parent.parent / "web" / "frontend" / "public" / "favicon.svg"
    favicon_path = HERE.parent.parent / "web" / "frontend" / "public" / "favicon-32.png"
    sizes = [16, 32, 48, 64, 128, 256]

    icon_svg = svg_icon()
    svg_path.write_text(icon_svg, encoding="utf-8")
    favicon_svg_path.write_text(icon_svg, encoding="utf-8")

    draw_icon(256).save(png_path, format="PNG")
    draw_icon(256).save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
    )
    draw_icon(32).save(favicon_path, format="PNG")
    print(f"Wrote {svg_path}")
    print(f"Wrote {favicon_svg_path}")
    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")
    print(f"Wrote {favicon_path}")


if __name__ == "__main__":
    main()
