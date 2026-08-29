"""Render every raster icon from the SVG sources.

The vectors in `app/static/assets/` are the source of truth; everything else
here is generated. Run after changing them:

    pip install cairosvg pillow
    python scripts/build_icons.py

This replaces the old `fix_icon.py`, which tried to knock a black background
out of an already-flattened PNG by flood-filling and eroding an anti-alias
ring. That is what chewed the silhouette edges and left a white halo around the
speed dashes — the artwork is vector now, so there is nothing to knock out.

Outputs, into both `app/static/assets/` and `site/assets/`:
  icon.png        the tile as a raster, for READMEs and social cards
  icon-192.png    full-bleed square, PWA maskable safe zone
  icon-512.png    same, larger
  favicon.ico     multi-size, from the rounded tile
  mark-light.svg  the mark with its figure colour baked in, for CSS that cannot
  mark-dark.svg   resolve `currentColor` (background-image, <img src>)
"""
from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "static" / "assets"
TARGETS = [ASSETS, ROOT / "site" / "assets"]

FIGURE_DARK = "#0e1726"   # --ink, for light surfaces
FIGURE_LIGHT = "#eef2f8"  # for dark surfaces
FAVICON_SIZES = [16, 32, 48, 64]


def render(svg_path: Path, size: int, *, recolor: str | None = None) -> Image.Image:
    """Rasterise an SVG at `size` px square-ish, optionally recoloring the
    `currentColor` figure (mark.svg leaves it to the caller)."""
    svg = svg_path.read_text("utf-8")
    if recolor:
        svg = svg.replace('fill="currentColor"', f'fill="{recolor}"')
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    tile = render(ASSETS / "icon.svg", 512)
    maskable512 = render(ASSETS / "icon-maskable.svg", 512)
    maskable192 = render(ASSETS / "icon-maskable.svg", 192)
    # `currentColor` does not resolve through background-image or <img src>, so
    # bake a variant per surface; the CSS swaps them the same way it swaps tokens.
    mark_svg = (ASSETS / "mark.svg").read_text("utf-8")
    baked = {
        "mark-light.svg": mark_svg.replace('fill="currentColor"', f'fill="{FIGURE_LIGHT}"'),
        "mark-dark.svg": mark_svg.replace('fill="currentColor"', f'fill="{FIGURE_DARK}"'),
    }
    for name, body in baked.items():
        (ASSETS / name).write_text(body, "utf-8")

    favicon = io.BytesIO()
    tile.save(favicon, format="ICO", sizes=[(s, s) for s in FAVICON_SIZES])

    for assets in TARGETS:
        assets.mkdir(parents=True, exist_ok=True)
        tile.save(assets / "icon.png")
        maskable192.save(assets / "icon-192.png")
        maskable512.save(assets / "icon-512.png")
        (assets / "favicon.ico").write_bytes(favicon.getvalue())
        # The vectors themselves ship alongside the site copy.
        for name in ("icon.svg", "icon-maskable.svg", "mark.svg",
                     "mark-light.svg", "mark-dark.svg"):
            if assets != ASSETS:
                (assets / name).write_bytes((ASSETS / name).read_bytes())
        print("updated", assets.relative_to(ROOT))


if __name__ == "__main__":
    main()
