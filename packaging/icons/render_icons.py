"""Render the Toolbox app icon: an SVG plus the raster sizes the installers and favicon need.

The glyph is four tiles (three squares and one turned on its corner) on a rounded blue square.
It is defined once, in a 36-unit design grid, and drawn twice: as SVG, and with Pillow for the
PNG/ICO files (supersampled, with real rounded corners, so both look the same).
"""

from __future__ import annotations

import colorsys
import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
GRID = 36  # design grid, in units
PRIMARY_HEX = "#2362ea"
FOREGROUND_HEX = "#f7f9fb"
TILE_RADIUS = 10  # corner radius of the blue square

STROKE = 1.8
SIDE = 7.0  # the three square tiles
CORNER = 1.5
X0, X1 = 9.2, 19.4  # left/top and right/bottom tile origins
DIAMOND_CENTER = 22.9
DIAMOND_SIDE = 6.0
DIAMOND_CORNER = 1.4

# (x, y) of the upper-left corner of each square tile.
SQUARES = [(X0, X0), (X1, X0), (X0, X1)]


def svg_icon() -> str:
    tiles = "\n    ".join(
        f'<rect x="{x}" y="{y}" width="{SIDE}" height="{SIDE}" rx="{CORNER}"/>' for x, y in SQUARES
    )
    half = DIAMOND_SIDE / 2
    diamond = (
        f'<rect x="{DIAMOND_CENTER - half:.3f}" y="{DIAMOND_CENTER - half:.3f}" '
        f'width="{DIAMOND_SIDE}" height="{DIAMOND_SIDE}" rx="{DIAMOND_CORNER}" '
        f'transform="rotate(45 {DIAMOND_CENTER} {DIAMOND_CENTER})"/>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}">
  <rect width="{GRID}" height="{GRID}" rx="{TILE_RADIUS}" fill="{PRIMARY_HEX}"/>
  <g fill="none" stroke="{FOREGROUND_HEX}" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">
    {tiles}
    {diamond}
  </g>
</svg>
"""


PRIMARY = tuple(int(round(c * 255)) for c in colorsys.hls_to_rgb(221 / 360, 0.53, 0.83))
FOREGROUND = (247, 249, 251)
SUPERSAMPLE = 4


def _rounded_square(
    cx: float, cy: float, side: float, radius: float, angle_deg: float, steps: int = 10
) -> list[tuple[float, float]]:
    """Outline of a rounded square as a closed polyline, turned by ``angle_deg`` about its centre."""
    half = side / 2 - radius
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    points: list[tuple[float, float]] = []
    # Corners in order, each with the angle its arc starts at (screen coordinates, y down).
    for sx, sy, start in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        for i in range(steps + 1):
            a = math.radians(start + 90 * i / steps)
            x = sx * half + radius * math.cos(a)
            y = sy * half + radius * math.sin(a)
            points.append((cx + x * cos_t - y * sin_t, cy + x * sin_t + y * cos_t))
    return points


def draw_icon(size: int) -> Image.Image:
    big = size * SUPERSAMPLE
    k = big / GRID
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=TILE_RADIUS * k, fill=PRIMARY + (255,))

    def outline(cx: float, cy: float, side: float, corner: float, angle: float) -> None:
        pts = [(x * k, y * k) for x, y in _rounded_square(cx, cy, side, corner, angle)]
        draw.line(pts + pts[:2], fill=FOREGROUND + (255,), width=max(1, round(STROKE * k)), joint="curve")

    for x, y in SQUARES:
        outline(x + SIDE / 2, y + SIDE / 2, SIDE, CORNER, 0)
    outline(DIAMOND_CENTER, DIAMOND_CENTER, DIAMOND_SIDE, DIAMOND_CORNER, 45)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    png_path = HERE / "toolbox.png"
    ico_path = HERE / "toolbox.ico"
    svg_path = HERE / "toolbox.svg"
    public = HERE.parent.parent / "web" / "frontend" / "public"
    favicon_svg_path = public / "favicon.svg"
    favicon_path = public / "favicon-32.png"
    sizes = [16, 32, 48, 64, 128, 256]

    icon_svg = svg_icon()
    svg_path.write_text(icon_svg, encoding="utf-8")
    favicon_svg_path.write_text(icon_svg, encoding="utf-8")

    draw_icon(256).save(png_path, format="PNG")
    draw_icon(256).save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    draw_icon(32).save(favicon_path, format="PNG")
    for path in (svg_path, favicon_svg_path, png_path, ico_path, favicon_path):
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
