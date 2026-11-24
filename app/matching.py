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
import unicodedata

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


# Two ways to compare text, for two jobs:
# - `fold` is for *search*: it keeps every character but folds case and
#   accents, so "beyonce" finds "Beyoncé". The Library's `search` column holds
#   it, and a query is folded the same way.
# - `tokens` is for *identity*: the bare ASCII words of a title or artist,
#   punctuation and platform cruft ("Official Video") gone, so two spellings of
#   one song give the same set.
# Every token is a substring of `fold` of the same text, which is what lets
# the Library prefilter its candidates in SQL.


def fold(text: str) -> str:
    """Lowercase, accents removed: what `search` holds and what a query is matched as."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _token_text(value: str) -> str:
    s = (value or "").lower()
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(value: str) -> frozenset[str]:
    """The words of a title or artist, lowercase ASCII, platform cruft removed."""
    return frozenset(_token_text(value).split())


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
