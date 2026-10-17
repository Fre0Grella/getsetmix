"""Render every raster icon from the SVG sources.

The vectors in `app/static/assets/` are the source of truth; everything else
here is generated. Run after changing them:

    pip install playwright pillow
    playwright install chromium
    python scripts/build_icons.py

This replaces the old `fix_icon.py`, which knocked the background out of a
flattened PNG by flood-filling it. That is what chewed the silhouette edges
and left a halo around the speed dashes; the artwork is vector now.

Outputs, into both `app/static/assets/` and `site/assets/`:
  icon.png        the rounded tile, for READMEs and social cards
  icon-192.png    full-bleed square (PWA maskable, apple-touch-icon)
  icon-512.png    same, larger
  favicon.ico     multi-size, from the rounded tile
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "static" / "assets"
SITE = ROOT / "site" / "assets"
SVGS = ("icon.svg", "icon-maskable.svg", "mark.svg", "mark-light.svg")
FAVICON_SIZES = [16, 32, 48, 64]


def render(page, svg: Path, size: int) -> Image.Image:
    """Rasterise a square SVG at `size` px with a transparent background."""
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(
        "<style>html,body{margin:0;background:transparent}"
        f"img{{display:block;width:{size}px;height:{size}px}}</style>"
        f'<img src="data:image/svg+xml;base64,{_b64(svg)}">'
    )
    page.wait_for_function("document.images[0].complete")
    png = page.screenshot(omit_background=True)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _b64(path: Path) -> str:
    import base64

    return base64.b64encode(path.read_bytes()).decode()


def main() -> None:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # no bundled browser downloaded: use the installed Chrome
            browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        tile = render(page, ASSETS / "icon.svg", 512)
        maskable = {n: render(page, ASSETS / "icon-maskable.svg", n) for n in (192, 512)}
        favicon = render(page, ASSETS / "icon.svg", 256)
        browser.close()

    tile.save(ASSETS / "icon.png", optimize=True)
    for n, im in maskable.items():
        im.save(ASSETS / f"icon-{n}.png", optimize=True)
    favicon.save(ASSETS / "favicon.ico", sizes=[(s, s) for s in FAVICON_SIZES])

    for name in ("icon.png", "icon-192.png", "icon-512.png", "favicon.ico", *SVGS):
        shutil.copyfile(ASSETS / name, SITE / name)
    print("icons written to", ASSETS.relative_to(ROOT), "and", SITE.relative_to(ROOT))


if __name__ == "__main__":
    main()
