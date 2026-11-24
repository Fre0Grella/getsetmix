"""Is it the same song? The rules that tell a staged download apart from a
track the Library already has (issue #71).

Two songs are the same when the exact source URL matches, or when the title
and artist match as *token sets*, independent of punctuation and of the file
name (the naming template can change). Token-set matching is what makes
real-world variants line up, e.g.:
  "Fantasm, The Straikerz"            == "Fantasm & The Straikerz"
  "Hardtechno Tacata" / "Dustin H..." == "Hardtechno Tacata (Extended)" / "Dustin H."
  "Woops (... Remix)" / "A, B, C, D"  == "Woops (... Remix)" / "A, B & C"
while still keeping genuinely different versions apart, e.g.
  "Night Drive (Extended Mix)"        != "Night Drive (Radio Edit)".

A record is a dict {name, artist, url}; any field may be "".
"""
from __future__ import annotations

import re

# Platform cruft stripped before tokenizing. We deliberately keep remix/mix/edit
# words so different versions of a track stay distinct.
_NOISE = re.compile(
    r"\b(official|officiel|video|videoclip|audio|lyrics?|visuali[sz]er|hd|hq|4k|"
    r"mv|m/v|explicit|feat\.?|ft\.?)\b",
    re.I,
)
# What the tagger writes into the comment: "Source: <url> | via GetSetMix".
# A URL has no spaces, so it ends at the first one.
_SOURCE = re.compile(r"\bsource:\s*(\S+)", re.I)


def _norm(value: str) -> str:
    s = (value or "").lower()
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(value: str) -> frozenset[str]:
    """The words of a title or artist, lowercase ASCII, platform cruft removed.
    Every token is a substring of the text as `library.fold` writes it, which
    is what lets the Library prefilter in SQL."""
    return frozenset(_norm(value).split())


def norm_url(value: str) -> str:
    return (value or "").strip().lower().rstrip("/")


def comment_source(comment: str) -> str:
    """The source URL GetSetMix stamped into a comment, or ""."""
    m = _SOURCE.search(comment or "")
    return m.group(1).rstrip(";") if m else ""


def subset(a: frozenset[str], b: frozenset[str], *, allow_single: bool) -> bool:
    """True if the smaller token set is contained in the larger. A single-token
    set only matches a larger one when `allow_single` (used for artists, where
    'Avicii' ⊆ 'Avicii & X' is fine, but a one-word *title* must match exactly)."""
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    if not small <= big:
        return False
    return small == big or len(small) >= 2 or allow_single


def same_url(a: dict, b: dict) -> bool:
    return bool(a["url"]) and a["url"] == b["url"]


def same_song(a: dict, b: dict) -> bool:
    if same_url(a, b):
        return True
    if not subset(tokens(a["name"]), tokens(b["name"]), allow_single=False):
        return False
    aa, ab = tokens(a["artist"]), tokens(b["artist"])
    if not aa and not ab:
        return True  # both artist-less and titles already line up
    return subset(aa, ab, allow_single=True)
