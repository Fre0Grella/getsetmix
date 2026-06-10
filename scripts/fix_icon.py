"""One-shot asset fix: knock out the black square behind the brand icon.

Figure and background are both pure black; the only separator is the noisy
anti-alias ring (values > 4) along every silhouette edge. So: build an "ink"
mask from that ring + the teal art, dilate it to seal gaps, flood-fill the
outside background, erode the dilation margin back, and drop noise blobs.
Produces:
  - icon.png        transparent bg, dark figure  (for light surfaces)
  - icon-light.png  transparent bg, white figure (for dark surfaces)
  - favicon.ico     multi-size, from the dark variant
"""
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "app" / "static" / "assets", ROOT / "site" / "assets"]

INK_MIN = 5          # any channel above this = silhouette edge or teal art
SEAL = 5             # MaxFilter size used to close gaps in the edge ring
MIN_BLOB = 400       # noise components smaller than this are dropped
NEUTRAL_SPREAD = 40  # max-min below this = grey/neutral pixel (the figure)


def channel_max(im: Image.Image) -> Image.Image:
    r, g, b, _ = im.split()
    return ImageChops.lighter(r, ImageChops.lighter(g, b))


def keep_mask(im: Image.Image) -> Image.Image:
    """255 where the icon artwork is, 0 where the background was."""
    ink = channel_max(im).point(lambda v: 255 if v >= INK_MIN else 0)
    sealed = ink.filter(ImageFilter.MaxFilter(SEAL))
    flooded = sealed.copy()
    ImageDraw.floodfill(flooded, (0, 0), 128)
    kept = flooded.point(lambda v: 0 if v == 128 else 255)
    # The seal dilation widened everything; shrink back, but keep real ink.
    eroded = kept.filter(ImageFilter.MinFilter(SEAL))
    return ImageChops.lighter(eroded, ImageChops.darker(ink, kept))


def drop_small_blobs(mask: Image.Image) -> Image.Image:
    w, h = mask.size
    px = mask.load()
    seen = [[False] * w for _ in range(h)]
    out = Image.new("L", mask.size, 0)
    opx = out.load()
    for sy in range(h):
        for sx in range(w):
            if seen[sy][sx] or px[sx, sy] == 0:
                continue
            blob = [(sx, sy)]
            seen[sy][sx] = True
            queue = deque(blob)
            while queue:
                x, y = queue.popleft()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and px[nx, ny]:
                        seen[ny][nx] = True
                        blob.append((nx, ny))
                        queue.append((nx, ny))
            if len(blob) >= MIN_BLOB:
                for x, y in blob:
                    opx[x, y] = 255
    return out


def build_variants(src: Path) -> tuple[Image.Image, Image.Image]:
    im = Image.open(src).convert("RGBA")
    mask = drop_small_blobs(keep_mask(im))
    # The edge ring is noisy; median-smooth the outline before feathering.
    alpha = mask.filter(ImageFilter.MedianFilter(7)).filter(ImageFilter.GaussianBlur(1.2))

    dark = im.copy()
    dark.putalpha(alpha)

    light = im.copy()
    px, lpx = im.load(), light.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if max(r, g, b) - min(r, g, b) < NEUTRAL_SPREAD:
                lpx[x, y] = (255, 255, 255, 255)
    light.putalpha(alpha)
    return dark, light


def main() -> None:
    dark, light = build_variants(ROOT / "app" / "static" / "assets" / "icon.png")
    for assets in TARGETS:
        dark.save(assets / "icon.png")
        light.save(assets / "icon-light.png")
        dark.save(assets / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
        print("updated", assets)


if __name__ == "__main__":
    main()
