"""The cover thumbnails of the Library list: GET /api/library/{id}/cover?size=thumb
and app/thumbs.py (design 4.5)."""
import io
import threading
import time

import pytest
from mutagen.id3 import APIC, ID3
from PIL import Image
from test_library_api import _client, listing, rescan

from app import tagger, thumbs

YEAR = "private, max-age=31536000, immutable"


def picture(kind: str = "JPEG", size=(1200, 900), mode: str = "RGB", seed: int = 1) -> bytes:
    """A picture with some texture, so that it has a realistic weight."""
    noise = Image.effect_noise(size, 40 + seed).convert("L")
    ramp = Image.linear_gradient("L").resize(size)
    img = Image.merge("RGB", (noise, ramp, ramp.point(lambda p: 255 - p)))
    if mode != "RGB":
        img = img.convert(mode)
    out = io.BytesIO()
    img.save(out, kind, **({"quality": 95} if kind == "JPEG" else {}))
    return out.getvalue()


def put_cover(music, rel: str, data: bytes, mime: str = "image/jpeg") -> None:
    path = music.path(rel)
    tags = ID3(path)
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="", data=data))
    tags.save(path, v2_version=4)
    music.age(rel, 3600)  # the index only takes files that have settled


@pytest.fixture()
def api(tmp_path, monkeypatch, music):
    with _client(tmp_path, monkeypatch) as c:
        yield c


def the_track(api, music, data: bytes | None, name: str = "Ann - Cover.mp3"):
    """One MP3 (with `data` as its cover when given), indexed; its listing item."""
    music.mp3(name, seed=1, title="Cover", artist="Ann")
    if data is not None:
        put_cover(music, name, data)
    rescan(api)
    [item] = listing(api)["items"]
    return item


def thumb_url(item, **extra):
    query = {"size": "thumb", "v": item["content_rev"], **extra}
    return f"/api/library/{item['id']}/cover", {k: v for k, v in query.items() if v is not None}


def get_thumb(api, item, **extra):
    url, params = thumb_url(item, **extra)
    return api.get(url, params=params)


def stored(tmp_path):
    folder = tmp_path / "data" / "thumbs"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


# ----------------------------------------------------------- the thumbnail
def test_the_thumbnail_is_a_small_square_jpeg_of_a_few_kilobytes(api, music):
    big = picture("JPEG", (1200, 900))
    item = the_track(api, music, big)

    r = get_thumb(api, item)

    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert tagger.image_type(r.content) == "image/jpeg"
    with Image.open(io.BytesIO(r.content)) as thumb:
        assert thumb.format == "JPEG" and thumb.size == (thumbs.THUMB_PX, thumbs.THUMB_PX)
    assert len(r.content) < 20 * 1024 and len(r.content) * 10 < len(big)


@pytest.mark.parametrize("kind, mode, mime", [
    ("PNG", "RGB", "image/png"), ("PNG", "RGBA", "image/png"), ("PNG", "P", "image/png"),
    ("WEBP", "RGB", "image/webp"), ("JPEG", "L", "image/jpeg"),
])
def test_every_stored_format_gets_a_jpeg_thumbnail(api, music, kind, mode, mime):
    item = the_track(api, music, picture(kind, (600, 400), mode), name="x.mp3")
    r = get_thumb(api, item)
    assert r.status_code == 200 and tagger.image_type(r.content) == "image/jpeg"
    with Image.open(io.BytesIO(r.content)) as thumb:
        assert thumb.size == (thumbs.THUMB_PX, thumbs.THUMB_PX) and thumb.mode == "RGB"


def test_a_picture_smaller_than_the_thumbnail_is_not_enlarged():
    out = thumbs.make_thumb(picture("PNG", (60, 40)))
    with Image.open(io.BytesIO(out)) as thumb:
        assert thumb.size == (40, 40)


def test_a_rotated_picture_is_turned_upright():
    img = Image.new("RGB", (300, 200), (0, 0, 255))
    img.paste((255, 0, 0), (0, 0, 150, 200))  # the left half is red
    exif = Image.Exif()
    exif[0x0112] = 6  # shown turned 90 degrees clockwise: the red half ends up on top
    out = io.BytesIO()
    img.save(out, "JPEG", quality=95, exif=exif)
    with Image.open(io.BytesIO(thumbs.make_thumb(out.getvalue()))) as thumb:
        top, bottom = thumb.getpixel((70, 10)), thumb.getpixel((70, 130))
    assert top[0] > 200 > top[2] and bottom[2] > 200 > bottom[0]


# ------------------------------------------------------------- the cache
def test_the_thumbnail_is_kept_on_disk_and_used_again(api, music, tmp_path, monkeypatch):
    item = the_track(api, music, picture())
    first = get_thumb(api, item).content
    assert stored(tmp_path) == [f"{item['id']}-{item['content_rev']}.jpg"]
    assert (tmp_path / "data" / "thumbs" / stored(tmp_path)[0]).read_bytes() == first

    def no_work(*args):
        raise AssertionError("the thumbnail was made again")

    monkeypatch.setattr(thumbs, "make_thumb", no_work)
    monkeypatch.setattr(tagger, "read_cover", no_work)
    assert get_thumb(api, item).content == first
    assert not [n for n in stored(tmp_path) if n.endswith(".part")]


def test_a_new_cover_makes_a_new_thumbnail_and_drops_the_old_one(api, music, tmp_path):
    item = the_track(api, music, picture("JPEG", seed=1))
    old = get_thumb(api, item).content
    assert len(stored(tmp_path)) == 1

    r = api.post(f"/api/library/{item['id']}/cover",
                 files={"file": ("new.png", picture("PNG", (500, 500), seed=30), "image/png")})
    assert r.status_code == 200
    new_item = r.json()
    assert new_item["content_rev"] > item["content_rev"]

    new = get_thumb(api, new_item).content
    assert new != old
    assert stored(tmp_path) == [f"{item['id']}-{new_item['content_rev']}.jpg"]


def test_thumbnails_of_other_files_are_left_alone(api, music, tmp_path):
    music.mp3("a.mp3", seed=1, title="A")
    music.mp3("b.mp3", seed=2, title="B")
    put_cover(music, "a.mp3", picture(seed=1))
    put_cover(music, "b.mp3", picture(seed=2))
    rescan(api)
    first, second = listing(api, sort="title")["items"]
    get_thumb(api, first)
    get_thumb(api, second)
    assert len(stored(tmp_path)) == 2
    thumbs.drop(first["id"])
    assert stored(tmp_path) == [f"{second['id']}-{second['content_rev']}.jpg"]


def test_a_purge_from_the_trash_removes_the_thumbnail(api, music, tmp_path):
    item = the_track(api, music, picture())
    get_thumb(api, item)
    assert len(stored(tmp_path)) == 1
    assert api.delete(f"/api/library/{item['id']}").status_code == 200
    assert len(stored(tmp_path)) == 1  # a trashed track can still be looked at
    assert api.delete("/api/library/trash").json() == {"purged": 1}
    assert stored(tmp_path) == []


def test_a_disk_that_cannot_be_written_still_answers(api, music, tmp_path, monkeypatch):
    item = the_track(api, music, picture())

    def refuse(src, dst):
        raise PermissionError(13, "read only")

    monkeypatch.setattr(thumbs.os, "replace", refuse)
    r = get_thumb(api, item)
    assert r.status_code == 200 and tagger.image_type(r.content) == "image/jpeg"
    assert stored(tmp_path) == []  # no thumbnail, and no half-written file either


def test_thumbnails_are_made_one_at_a_time(api, music, monkeypatch):
    item = the_track(api, music, picture())
    running, most = [0], [0]
    real = thumbs.make_thumb

    def watched(data):
        running[0] += 1
        most[0] = max(most[0], running[0])
        time.sleep(0.05)
        try:
            return real(data)
        finally:
            running[0] -= 1

    monkeypatch.setattr(thumbs, "make_thumb", watched)
    made = []
    path = music.path(item["path"])
    workers = [threading.Thread(target=lambda rev=rev: made.append(thumbs.get(item["id"], rev, path)))
               for rev in range(1, 5)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert most[0] == 1 and len(made) == 4 and all(made)


# ------------------------------------------------------------- the fallback
def test_a_picture_that_cannot_be_decoded_is_served_as_it_is(api, music, tmp_path):
    broken = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"  # told as a JPEG, not one
    item = the_track(api, music, broken)
    r = get_thumb(api, item)
    assert r.status_code == 200 and r.content == broken
    assert r.headers["content-type"] == "image/jpeg"
    assert stored(tmp_path) == []


def test_a_truncated_picture_is_served_as_it_is(api, music):
    cut = picture("PNG", (800, 800))[:3000]
    item = the_track(api, music, cut)
    r = get_thumb(api, item)
    assert r.status_code == 200 and r.content == cut and r.headers["content-type"] == "image/png"


def test_a_picture_over_the_limits_is_not_decoded(monkeypatch):
    data = picture("PNG", (200, 200))
    assert thumbs.make_thumb(data) is not None
    with monkeypatch.context() as m:
        m.setattr(thumbs, "MAX_PIXELS", 200 * 200 - 1)
        assert thumbs.make_thumb(data) is None
    with monkeypatch.context() as m:
        m.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # Pillow's own limit still holds
        assert thumbs.make_thumb(data) is None
    with monkeypatch.context() as m:
        m.setattr(tagger, "MAX_COVER", len(data) - 1)  # and so does the size of the cover
        assert thumbs.make_thumb(data) is None
    assert thumbs.make_thumb(b"") is None


def test_only_the_cover_formats_are_decoded():
    # a valid picture in a format Pillow knows but a cover is not: no decoder runs
    for kind in ("BMP", "TIFF", "PPM"):
        assert thumbs.make_thumb(picture(kind, (50, 50))) is None


def test_a_decompression_bomb_is_refused(monkeypatch):
    def bomb(*args, **kwargs):
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(Image, "open", bomb)
    assert thumbs.make_thumb(picture("PNG", (50, 50))) is None


def test_no_cover_is_the_same_404_as_before(api, music):
    item = the_track(api, music, None)
    assert get_thumb(api, item).status_code == 404
    url, _ = thumb_url(item)
    assert api.get(url).status_code == 404
    assert api.get("/api/library/9999/cover", params={"size": "thumb"}).status_code == 404


# ------------------------------------------------------- the full cover, headers
def test_the_full_cover_is_unchanged(api, music):
    big = picture("JPEG", (900, 900))
    item = the_track(api, music, big)
    r = api.get(f"/api/library/{item['id']}/cover", params={"v": item["content_rev"]})
    assert r.status_code == 200 and r.content == big and r.headers["content-type"] == "image/jpeg"
    assert r.headers["etag"] == f'W/"cover-{item["id"]}-{item["content_rev"]}"'
    assert r.headers["cache-control"] == YEAR


def test_the_thumbnail_is_cached_like_the_cover(api, music):
    item = the_track(api, music, picture())

    named = get_thumb(api, item)
    assert named.headers["cache-control"] == YEAR
    assert named.headers["x-content-type-options"] == "nosniff"
    assert named.headers["etag"] == f'W/"cover-thumb-{item["id"]}-{item["content_rev"]}"'

    for stale in (item["content_rev"] + 1, None):  # not the current revision, or none named
        other = get_thumb(api, item, v=stale)
        assert other.status_code == 200 and other.headers["cache-control"] == "private, no-cache"

    full = api.get(f"/api/library/{item['id']}/cover", params={"v": item["content_rev"]})
    assert full.headers["etag"] != named.headers["etag"]  # two different bodies


def test_a_matching_etag_answers_304_without_the_body(api, music):
    item = the_track(api, music, picture())
    tag = get_thumb(api, item).headers["etag"]
    url, params = thumb_url(item)
    r = api.get(url, params=params, headers={"If-None-Match": tag})
    assert r.status_code == 304 and r.content == b""
    assert r.headers["cache-control"] == YEAR
    # the full cover's tag is not the thumbnail's
    full_tag = tag.replace("cover-thumb-", "cover-")
    assert api.get(url, params=params, headers={"If-None-Match": full_tag}).status_code == 200


def test_any_other_size_is_a_400(api, music):
    item = the_track(api, music, picture())
    assert get_thumb(api, item, size="huge").status_code == 400
