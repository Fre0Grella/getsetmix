"""Cleanup rules for track tags: pure functions over a dict of fields.

Design: docs/design/batch-editing.md, sections 4.1 and 4.2. The cases that
document and test every rule are in tests/rules_cases.json.

A rule reads the fields it is given and returns new ones. It reads no file and
no database, never invents text (it removes, moves or respells), never returns
an empty title or artist, and is idempotent. After every step a *tidy* pass
runs on the fields the step was aimed at.

No regular expression is ever taken from a user; `re` is only used inside the
rules, with patterns written here.
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .genres import GENRES

CATALOGUE_VERSION = 1

TEXT_FIELDS = ("title", "artist", "album", "genre", "comment")
Fields = dict[str, Any]
Warning_ = dict[str, Any]


class RuleError(ValueError):
    """A step names an unknown rule, field or parameter, or gives a bad value."""


@dataclass
class RuleResult:
    fields: Fields
    changed: tuple[str, ...] = ()
    warnings: list[Warning_] = field(default_factory=list)


@dataclass
class StepsResult:
    fields: Fields
    by: dict[str, list[dict]] = field(default_factory=dict)
    warnings: list[Warning_] = field(default_factory=list)


# ---------------------------------------------------------------- tidy pass

_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")
_DANGLING_END = re.compile(r"(?:\s*[,;]|\s+[-–—|－])+\s*$")
_DANGLING_START = re.compile(r"^\s*(?:[,;]\s*|[-–—|－]\s+)+")


def tidy(text: str) -> str:
    """Runs of spaces become one, ends are trimmed, empty brackets go, and a
    separator left dangling at an end goes."""
    prev = None
    while text != prev:
        prev = text
        text = " ".join(text.split())
        text = _EMPTY_BRACKETS.sub("", text)
        text = _DANGLING_END.sub("", text)
        text = _DANGLING_START.sub("", text)
        text = text.strip()
    return text


# ---------------------------------------------------------------- helpers

_GROUP = re.compile(r"\(([^()\[\]]*)\)|\[([^()\[\]]*)\]")
_FEAT = r"(?:featuring|feat|ft)"
_FEAT_SPELLINGS = ("feat.", "feat", "ft.", "ft", "featuring")
_SEPARATORS = (" - ", " – ", " — ", " | ", " － ")  # as app/metadata.py
_DASHES = r"[-–—]"


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _group_content(m: re.Match) -> str:
    return m.group(1) if m.group(1) is not None else m.group(2)


def _drop_groups(text: str, wanted: set[str]) -> str:
    return _GROUP.sub(lambda m: "" if _norm(_group_content(m)) in wanted else m.group(0), text)


def _last_word(text: str) -> str:
    m = re.search(r"(\w+)$", text.strip())
    return m.group(1).casefold() if m else ""


def _per_field(fields: Fields, scope: tuple[str, ...], fn: Callable[[str], str]) -> Fields:
    return {k: fn(fields[k]) for k in scope if isinstance(fields.get(k), str)}


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == 0


# ---------------------------------------------------------------- the rules

def _trim(fields, scope, p):
    def fix(v: str) -> str:
        out = []
        for ch in v:
            if ch in "​﻿":  # zero-width space, byte-order mark
                continue
            if ch.isspace():
                out.append(" ")
            elif unicodedata.category(ch) == "Cc":
                continue
            elif ch == "_" and p["underscores"]:
                out.append(" ")
            else:
                out.append(ch)
        return "".join(out)

    return _per_field(fields, scope, fix), []


def _promo_remove(fields, scope, p):
    wanted = {_norm(x) for x in p["phrases"]}
    return _per_field(fields, scope, lambda v: _drop_groups(v, wanted)), []


_TLDS = "com|net|org|io|fm|dj|co|it|de|uk"
_URL = re.compile(r"(?:https?://|www\.)[^\s()\[\]]+", re.I)
_DOMAIN = re.compile(rf"(?<![\w@.-])(?:[\w-]+\.)+(?:{_TLDS})(?![\w-])", re.I)
_HANDLE = re.compile(r"(?:(?<=\s)|^)@[\w.]+(?:\s+@[\w.]+)*\s*$")


def _url_remove(fields, scope, p):
    def fix(v: str) -> str:
        v = _URL.sub(" ", v)
        v = _DOMAIN.sub(" ", v)
        return _HANDLE.sub("", v)

    return _per_field(fields, scope, fix), []


def _split_artist_title(fields, scope, p):
    if not {"title", "artist"} <= set(scope):
        return {}, []
    title, artist = fields["title"], fields["artist"]
    if not isinstance(title, str) or not isinstance(artist, str):
        return {}, []
    when = p["when"]
    title, artist = title.strip(), artist.strip()
    if not artist and when in ("artist_empty_or_same", "artist_empty", "always") \
            or when == "always":
        for sep in _SEPARATORS:  # first separator in ingest's order, as metadata.py
            if sep in title:
                left, right = (s.strip() for s in title.split(sep, 1))
                if left and right:
                    return {"title": right, "artist": left}, []
                return {}, []
        return {}, []
    if when == "artist_empty_or_same" and artist:
        for sep in _SEPARATORS:
            prefix = artist + sep
            if title.casefold().startswith(prefix.casefold()):
                rest = title[len(prefix):].strip()
                if rest:
                    return {"title": rest}, []
    return {}, []


_FEAT_BRACKETED = re.compile(rf"\[\s*({_FEAT}(?![\w])\.?)\s*([^\[\]()]*?)\s*\]", re.I)
_FEAT_WORD = re.compile(rf"(?<=[\s(\[]){_FEAT}(?![\w])\.?", re.I)


def _feat_normalise(fields, scope, p):
    spelling = p["spelling"]

    def fix(v: str) -> str:
        v = _FEAT_BRACKETED.sub(lambda m: f"({m.group(1)} {m.group(2)})".replace(" )", ")"), v)
        return _FEAT_WORD.sub(lambda m: spelling, v)

    return _per_field(fields, scope, fix), []


_ARTIST_FEAT_BRACKETED = re.compile(
    rf"^(?P<base>.+?)\s+\(\s*(?P<word>{_FEAT}(?![\w])\.?)\s+(?P<names>[^()]+?)\s*\)$", re.I)
_ARTIST_FEAT_PLAIN = re.compile(
    rf"^(?P<base>.+?)\s+(?P<word>{_FEAT}(?![\w])\.?)\s+(?P<names>.+)$", re.I)
_TITLE_FEAT = re.compile(
    rf"[\(\[]\s*(?P<word>{_FEAT}(?![\w])\.?)\s+(?P<names>[^()\[\]]+?)\s*[\)\]]", re.I)


def _mix_position(title: str, mix_words: set[str]) -> int | None:
    """Where a mix name starts in a title: a bracket group, or a tail after a dash."""
    found = []
    for m in _GROUP.finditer(title):
        if _last_word(_group_content(m)) in mix_words:
            found.append(m.start())
    m = re.match(rf"^(.*\S)(\s+{_DASHES}\s+)([^()\[\]]+)$", title)
    if m and _last_word(m.group(3)) in mix_words:
        found.append(m.end(1))
    return min(found) if found else None


def _feat_move(fields, scope, p):
    if not {"title", "artist"} <= set(scope):
        return {}, []
    title, artist = fields["title"], fields["artist"]
    if not isinstance(title, str) or not isinstance(artist, str):
        return {}, []
    if p["to"] == "title":
        m = _ARTIST_FEAT_BRACKETED.match(artist) or _ARTIST_FEAT_PLAIN.match(artist)
        if not m or not m.group("base").strip():
            return {}, []
        names = m.group("names").strip()
        already = any(_norm(t.group("names")) == _norm(names) for t in _TITLE_FEAT.finditer(title))
        new_artist = m.group("base").strip()
        if already:
            return {"artist": new_artist}, []
        group = f"({m.group('word')} {names})"
        pos = _mix_position(title, _mix_words_default())
        if pos is None:
            new_title = f"{title} {group}"
        elif title[pos:].lstrip().startswith(("(", "[")):
            new_title = f"{title[:pos].rstrip()} {group} {title[pos:]}"
        else:
            new_title = f"{title[:pos]} {group}{title[pos:]}"
        return {"artist": new_artist, "title": new_title}, []
    # to == "artist"
    t = _TITLE_FEAT.search(title)
    if not t or not artist.strip():
        return {}, []
    new_title = tidy(title[:t.start()] + " " + title[t.end():])
    if not new_title:
        return {}, []
    names = t.group("names").strip()
    existing = _ARTIST_FEAT_BRACKETED.match(artist) or _ARTIST_FEAT_PLAIN.match(artist)
    if existing:
        if _norm(existing.group("names")) != _norm(names):
            return {}, []
        return {"title": new_title}, []
    return {"title": new_title, "artist": f"{artist} {t.group('word')} {names}"}, []


def _mix_remove_default(fields, scope, p):
    wanted = {_norm(x) for x in p["labels"]}
    return _per_field(fields, scope, lambda v: _drop_groups(v, wanted)), []


_SQUARE = re.compile(r"\[([^()\[\]]*)\]")
_TAIL = re.compile(rf"^(?P<left>.*\S)\s+{_DASHES}\s+(?P<tail>[^()\[\]]+)$")


def _mix_brackets(fields, scope, p):
    words = {w.casefold() for w in p["mix_words"]}

    def fix(v: str) -> str:
        v = _SQUARE.sub(
            lambda m: f"({m.group(1).strip()})" if _last_word(m.group(1)) in words else m.group(0), v)
        m = _TAIL.match(v)
        if m and _last_word(m.group("tail")) in words:
            v = f"{m.group('left')} ({m.group('tail').strip()})"
        return v

    return _per_field(fields, scope, fix), []


def _artist_separators(fields, scope, p):
    seps = sorted({s for s in p["from"] if s.strip()}, key=len, reverse=True)
    if not seps:
        return {}, []

    def part(s: str) -> str:
        lead = r"\s+" if s[:1].isspace() else r"\s*"
        trail = r"\s+" if s[-1:].isspace() else r"\s*"
        return lead + re.escape(s.strip()) + trail

    sep_re = re.compile("|".join(part(s) for s in seps))
    to = p["to"]
    keep = sorted({k for k in p["keep"] if k}, key=len, reverse=True)
    keep_re = re.compile("(" + "|".join(re.escape(k) for k in keep) + ")", re.I) if keep else None

    def fix(v: str) -> str:
        if keep_re is None:
            return sep_re.sub(lambda m: to, v)
        pieces = keep_re.split(v)
        return "".join(x if i % 2 else sep_re.sub(lambda m: to, x) for i, x in enumerate(pieces))

    return _per_field(fields, scope, fix), []


def _is_lower(v: str) -> bool:
    return v == v.lower() and v != v.upper()


def _is_upper(v: str) -> bool:
    return v == v.upper() and v != v.lower()


def _capital(ch: str) -> str:
    up = ch.upper()
    return up if len(up) == 1 else ch


def _cap_word(core: str) -> str:
    parts = core.split("-")
    return "-".join(_capital(x[:1]) + x[1:].lower() for x in parts)


_TOKEN = re.compile(r"\S+")
_SPLIT_TOKEN = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


def _title_case(value: str, small: set[str], keep: dict[str, str]) -> str:
    tokens = list(_TOKEN.finditer(value))
    out, last_end = [], 0
    for i, m in enumerate(tokens):
        out.append(value[last_end:m.start()])
        last_end = m.end()
        lead, core, trail = _SPLIT_TOKEN.match(m.group(0)).groups()
        key = core.casefold()
        if not core:
            word = core
        elif key in keep:
            word = keep[key]
        elif key in ("feat", "ft", "featuring"):
            word = key  # the spelling feat.normalise chose stays as it is
        elif key in small and not (i == 0 or i == len(tokens) - 1 or "(" in lead or "[" in lead):
            word = key
        else:
            word = _cap_word(core)
        out.append(lead + word + trail)
    return "".join(out)


def _case_title(fields, scope, p):
    small = {w.casefold().rstrip(".") for w in p["small_words"]}
    keep = {k.casefold(): k for k in p["keep"]}
    scope_kind = p["scope"]

    def eligible(v: str) -> bool:
        if scope_kind == "lower":
            return _is_lower(v)
        if scope_kind == "uniform":
            return _is_lower(v) or _is_upper(v)
        return True

    return {k: _title_case(fields[k], small, keep)
            for k in scope if isinstance(fields.get(k), str) and eligible(fields[k])}, []


def genre_key(name: str) -> str:
    """The form in which two genre spellings are compared: lower case, with
    spaces, hyphens, `&`, the word "and" and punctuation dropped."""
    name = re.sub(r"\band\b", "", name.casefold())
    return re.sub(r"[\W_]+", "", name)


_GENRE_BY_KEY = {genre_key(g): g for g in GENRES}


def _genre_map(fields, scope, p):
    aliases = {genre_key(k): v for k, v in p["aliases"].items()}
    out: Fields = {}
    warnings: list[Warning_] = []
    for k in scope:
        v = fields.get(k)
        if not isinstance(v, str) or not v.strip():
            continue
        key = genre_key(v)
        if key in aliases:
            out[k] = aliases[key]
        elif key in _GENRE_BY_KEY:
            out[k] = _GENRE_BY_KEY[key]
        else:
            warnings.append({"warning": "not_in_genre_list", "field": k, "value": v})
    return out, warnings


_YEAR_AT_END = re.compile(r"[\(\[]\s*([0-9]{4})\s*[\)\]]\s*$")


def _year_extract(fields, scope, p):
    if "year" not in scope or not _is_empty(fields.get("year")):
        return {}, []
    top = datetime.date.today().year + 1
    for k in ("title", "album"):
        v = fields.get(k)
        if k not in scope or not isinstance(v, str):
            continue
        m = _YEAR_AT_END.search(v)
        if m and 1900 <= int(m.group(1)) <= top:
            out: Fields = {"year": int(m.group(1))}
            if p["remove"]:
                out[k] = v[:m.start()]
            return out, []
    return {}, []


# ---------------------------------------------------------------- the catalogue

PROMO_PHRASES = [
    "Free Download", "Free DL", "Out Now", "Official Video", "Official Audio",
    "Official Music Video", "Official Visualizer", "Visualizer", "Lyric Video", "Lyrics",
    "Audio", "Video", "HD", "HQ", "4K", "Premiere", "Preview", "Clip", "Full Track",
    "Video Ufficiale", "Testo",
]
MIX_DEFAULT_LABELS = ["Original Mix", "Original", "Original Version"]
MIX_WORDS = [
    "Mix", "Remix", "Edit", "Rework", "Bootleg", "Dub", "Version", "VIP", "Flip",
    "Mashup", "Refix", "Remaster",
]
ARTIST_SEPARATORS = [" x ", " X ", " vs ", " vs. ", " Vs. ", ";", " / ", " + "]
SMALL_WORDS = [
    "a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the",
    "to", "vs", "with", "feat.",
]
KEEP_WORDS = [
    "DJ", "MC", "UK", "USA", "NYC", "EP", "LP", "VIP", "II", "III", "EDM", "BPM", "R&B",
]
GENRE_ALIASES = {
    "Drum n Bass": "Drum & Bass", "Drum'n'Bass": "Drum & Bass", "DnB": "Drum & Bass",
    "D&B": "Drum & Bass", "RnB": "R&B", "R'n'B": "R&B", "UKG": "UK Garage",
    "Prog House": "Progressive House", "Melodic Techno": "Melodic House & Techno",
}


def _mix_words_default() -> set[str]:
    return {w.casefold() for w in MIX_WORDS}


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # bool | string | string_list | string_map | choice
    default: Any
    choices: tuple[str, ...] = ()

    def describe(self) -> dict:
        d: dict[str, Any] = {"name": self.name, "type": self.type, "default": _copy(self.default)}
        if self.choices:
            d["choices"] = list(self.choices)
        return d

    def check(self, rule: str, value: Any) -> Any:
        ok = {
            "bool": lambda v: isinstance(v, bool),
            "string": lambda v: isinstance(v, str),
            "string_list": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
            "string_map": lambda v: isinstance(v, dict) and all(
                isinstance(k, str) and isinstance(x, str) for k, x in v.items()),
            "choice": lambda v: v in self.choices,
        }[self.type](value)
        if not ok:
            raise RuleError(f"{rule}: bad value for parameter {self.name!r}")
        return _copy(value)


def _copy(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


@dataclass(frozen=True)
class Rule:
    id: str
    name: dict[str, str]
    description: dict[str, str]
    fields: tuple[str, ...]            # the default fields
    allowed: tuple[str, ...]           # the fields a step may aim it at
    cross_field: bool
    params: tuple[Param, ...]
    fn: Callable[[Fields, tuple[str, ...], dict], tuple[Fields, list[Warning_]]]
    examples: tuple[dict, ...]

    def resolve(self, given: dict | None) -> dict:
        known = {p.name: p for p in self.params}
        given = given or {}
        unknown = set(given) - set(known)
        if unknown:
            raise RuleError(f"{self.id}: unknown parameter {sorted(unknown)[0]!r}")
        return {p.name: p.check(self.id, given[p.name]) if p.name in given else _copy(p.default)
                for p in self.params}


_TEXT4 = ("title", "artist", "album", "genre")


def _ex(before: dict, after: dict, **params) -> dict:
    ex: dict[str, Any] = {"before": before, "after": after}
    if params:
        ex["params"] = params
    return ex


RULES: tuple[Rule, ...] = (
    Rule(
        "trim",
        {"en": "Tidy spaces", "it": "Pulisci gli spazi"},
        {"en": "Spaces, odd whitespace and control characters.",
         "it": "Spazi, spazi strani e caratteri di controllo."},
        ("title", "artist", "album", "genre"), (*_TEXT4, "comment"), False,
        (Param("underscores", "bool", False),), _trim,
        (_ex({"title": "  Night   Drive "}, {"title": "Night Drive"}),
         _ex({"title": "Night_Drive"}, {"title": "Night Drive"}, underscores=True),
         _ex({"title": "Night_Drive"}, {})),
    ),
    Rule(
        "promo.remove",
        {"en": "Remove promo text", "it": "Togli il testo promozionale"},
        {"en": "Promotional and video text in brackets, such as (Official Video).",
         "it": "Testo promozionale e di video tra parentesi, come (Official Video)."},
        ("title",), _TEXT4, False,
        (Param("phrases", "string_list", PROMO_PHRASES),), _promo_remove,
        (_ex({"title": "Night Drive (Extended Mix) [FREE DOWNLOAD]"}, {"title": "Night Drive (Extended Mix)"}),
         _ex({"title": "Night Drive [HQ] (Kito Remix)"}, {"title": "Night Drive (Kito Remix)"}),
         _ex({"title": "Night Drive (Free)"}, {})),
    ),
    Rule(
        "url.remove",
        {"en": "Remove web addresses", "it": "Togli gli indirizzi web"},
        {"en": "Web addresses and @handles. Never runs on the comment unless you aim it there.",
         "it": "Indirizzi web e @nomi. Non tocca il commento se non lo scegli tu."},
        ("title", "artist", "album"), (*_TEXT4, "comment"), False, (), _url_remove,
        (_ex({"title": "Night Drive - www.example.com"}, {"title": "Night Drive"}),
         _ex({"title": "Nova @novamusic"}, {"title": "Nova"}),
         _ex({"title": "Mr. Fingers"}, {})),
    ),
    Rule(
        "split.artist_title",
        {"en": "Split artist and title", "it": "Separa artista e titolo"},
        {"en": "Moves \"Artist - Title\" left in the title into the two fields.",
         "it": "Separa \"Artista - Titolo\" rimasto nel titolo nei due campi."},
        ("title", "artist"), ("title", "artist"), True,
        (Param("when", "choice", "artist_empty_or_same",
               ("artist_empty_or_same", "artist_empty", "always")),), _split_artist_title,
        (_ex({"title": "Nova - Night Drive", "artist": ""}, {"title": "Night Drive", "artist": "Nova"}),
         _ex({"title": "Nova - Night Drive", "artist": "Nova"}, {"title": "Night Drive"}),
         _ex({"title": "Nova - Night Drive", "artist": "Kito"}, {})),
    ),
    Rule(
        "feat.normalise",
        {"en": "One spelling of \"featuring\"", "it": "Una sola grafia di \"featuring\""},
        {"en": "Respells ft, ft., feat, featuring to one form; square brackets become round.",
         "it": "Riscrive ft, ft., feat, featuring in una sola forma; le quadre diventano tonde."},
        ("title", "artist"), ("title", "artist", "album"), False,
        (Param("spelling", "choice", "feat.", _FEAT_SPELLINGS),), _feat_normalise,
        (_ex({"title": "Night Drive (Ft. Kito)"}, {"title": "Night Drive (feat. Kito)"}),
         _ex({"title": "Night Drive [Featuring Kito]"}, {"title": "Night Drive (feat. Kito)"}),
         _ex({"title": "Left Behind"}, {})),
    ),
    Rule(
        "feat.move",
        {"en": "Move the featured artist", "it": "Sposta l'artista ospite"},
        {"en": "Moves the featured artist into the title (default) or into the artist. Run it after the spelling rule.",
         "it": "Sposta l'artista ospite nel titolo (predefinito) o nell'artista. Da eseguire dopo la regola della grafia."},
        ("title", "artist"), ("title", "artist"), True,
        (Param("to", "choice", "title", ("title", "artist")),), _feat_move,
        (_ex({"artist": "Nova feat. Kito", "title": "Night Drive"},
             {"artist": "Nova", "title": "Night Drive (feat. Kito)"}),
         _ex({"artist": "Nova feat. Kito", "title": "Night Drive (Extended Mix)"},
             {"artist": "Nova", "title": "Night Drive (feat. Kito) (Extended Mix)"}),
         _ex({"artist": "Nova", "title": "Night Drive (feat. Kito)"},
             {"artist": "Nova feat. Kito", "title": "Night Drive"}, to="artist")),
    ),
    Rule(
        "mix.remove_default",
        {"en": "Remove \"(Original Mix)\"", "it": "Togli \"(Original Mix)\""},
        {"en": "Removes the default mix name; names that tell two files apart stay.",
         "it": "Toglie il nome di mix predefinito; i nomi che distinguono due file restano."},
        ("title",), ("title", "album"), False,
        (Param("labels", "string_list", MIX_DEFAULT_LABELS),), _mix_remove_default,
        (_ex({"title": "Night Drive (Original Mix)"}, {"title": "Night Drive"}),
         _ex({"title": "Night Drive [Original]"}, {"title": "Night Drive"}),
         _ex({"title": "Night Drive (Extended Mix)"}, {})),
    ),
    Rule(
        "mix.brackets",
        {"en": "Round brackets for mix names", "it": "Parentesi tonde per i mix"},
        {"en": "Gives a mix or remix name round brackets when it is in square brackets or hangs after a dash.",
         "it": "Mette tra tonde il nome di un mix o remix quando e' tra quadre o dopo un trattino."},
        ("title",), ("title", "album"), False,
        (Param("mix_words", "string_list", MIX_WORDS),), _mix_brackets,
        (_ex({"title": "Night Drive [Kito Remix]"}, {"title": "Night Drive (Kito Remix)"}),
         _ex({"title": "Night Drive - Extended Mix"}, {"title": "Night Drive (Extended Mix)"}),
         _ex({"title": "Night Drive - Part Two"}, {})),
    ),
    Rule(
        "artist.separators",
        {"en": "One separator between artists", "it": "Un solo separatore tra gli artisti"},
        {"en": "Replaces x, vs, ; and similar between artists with one separator. & and \"and\" are not touched by default.",
         "it": "Sostituisce x, vs, ; e simili tra gli artisti con un solo separatore. & e \"and\" non si toccano per impostazione predefinita."},
        ("artist",), ("artist",), False,
        (Param("from", "string_list", ARTIST_SEPARATORS), Param("to", "string", ", "),
         Param("keep", "string_list", [])), _artist_separators,
        (_ex({"artist": "Nova x Kito"}, {"artist": "Nova, Kito"}),
         _ex({"artist": "Nova;Kito"}, {"artist": "Nova, Kito"}),
         _ex({"artist": "Sun & Moon"}, {})),
    ),
    Rule(
        "case.title",
        {"en": "Fix letter case", "it": "Correggi le maiuscole"},
        {"en": "Capitalises values written all in lower case. Capitals are left alone unless you widen the scope.",
         "it": "Mette le maiuscole ai valori scritti tutti in minuscolo. Le maiuscole esistenti restano, salvo che tu allarghi l'ambito."},
        ("title", "album"), ("title", "artist", "album"), False,
        (Param("scope", "choice", "lower", ("lower", "uniform", "all")),
         Param("small_words", "string_list", SMALL_WORDS), Param("keep", "string_list", KEEP_WORDS)),
        _case_title,
        (_ex({"title": "night drive (extended mix)"}, {"title": "Night Drive (Extended Mix)"}),
         _ex({"title": "lost in the city"}, {"title": "Lost in the City"}),
         _ex({"title": "NIGHT DRIVE"}, {"title": "Night Drive"}, scope="uniform"),
         _ex({"title": "NIGHT DRIVE"}, {})),
    ),
    Rule(
        "genre.map",
        {"en": "Map genres to the list", "it": "Porta i generi sulla lista"},
        {"en": "Maps genre spellings onto the app's genre list; unknown genres are left alone with a warning.",
         "it": "Porta le grafie dei generi sulla lista dell'app; i generi sconosciuti restano com'e' con un avviso."},
        ("genre",), ("genre",), False,
        (Param("aliases", "string_map", GENRE_ALIASES),), _genre_map,
        (_ex({"genre": "tech-house"}, {"genre": "Tech House"}),
         _ex({"genre": "DnB"}, {"genre": "Drum & Bass"}),
         _ex({"genre": "Dark Disco"}, {})),
    ),
    Rule(
        "year.extract",
        {"en": "Year from the title or album", "it": "Anno dal titolo o dall'album"},
        {"en": "Takes a year that stands alone in brackets at the end of the title or album, when the year is empty.",
         "it": "Prende un anno da solo tra parentesi a fine titolo o album, quando l'anno e' vuoto."},
        ("year", "title", "album"), ("year", "title", "album"), True,
        (Param("remove", "bool", False),), _year_extract,
        (_ex({"year": None, "title": "Night Drive [2019]"}, {"year": 2019}),
         _ex({"year": None, "title": "Night Drive [2019]"}, {"year": 2019, "title": "Night Drive"}, remove=True),
         _ex({"year": 2021, "title": "Night Drive [2019]"}, {})),
    ),
)
_BY_ID = {r.id: r for r in RULES}

STANDARD_CLEANUP: list[dict] = [
    {"rule": "promo.remove"},
    {"rule": "url.remove"},
    {"rule": "trim"},
    {"rule": "split.artist_title"},
    {"rule": "feat.normalise"},
    {"rule": "feat.move", "params": {"to": "title"}},
    {"rule": "mix.remove_default"},
    {"rule": "mix.brackets"},
    {"rule": "artist.separators"},
    {"rule": "case.title"},
    {"rule": "genre.map"},
]

BUILTIN_RULESETS: list[dict] = [
    {"name": "Standard cleanup", "builtin": True, "steps": STANDARD_CLEANUP},
]


def default_fields(rule_id: str) -> tuple[str, ...]:
    return _rule(rule_id).fields


def allowed_fields(rule_id: str) -> tuple[str, ...]:
    return _rule(rule_id).allowed


def _rule(rule_id: str) -> Rule:
    try:
        return _BY_ID[rule_id]
    except (KeyError, TypeError):
        raise RuleError(f"unknown rule {rule_id!r}") from None


def catalogue() -> dict:
    """The catalogue as the API serves it (without the genre list)."""
    return {
        "version": CATALOGUE_VERSION,
        "rules": [
            {
                "id": r.id, "name": dict(r.name), "description": dict(r.description),
                "fields": list(r.fields), "allowed_fields": list(r.allowed),
                "cross_field": r.cross_field,
                "params": [p.describe() for p in r.params],
                "examples": [dict(e) for e in r.examples],
            }
            for r in RULES
        ],
        "rulesets": BUILTIN_RULESETS,
    }


# ---------------------------------------------------------------- running

def run_rule(rule_id: str, fields: Fields, scope: list[str] | tuple[str, ...] | None = None,
             params: dict | None = None) -> RuleResult:
    """Run one rule over `fields` and tidy what it was aimed at.

    `scope` is the fields the step names; the rule's defaults when None. Only
    fields that are in `fields` and in the scope can change. `fields` is not
    modified.
    """
    rule = _rule(rule_id)
    if scope is not None:
        bad = [f for f in scope if f not in rule.allowed]
        if bad:
            raise RuleError(f"{rule_id}: cannot be aimed at {bad[0]!r}")
    p = rule.resolve(params)
    wanted = rule.fields if scope is None else tuple(scope)
    use = tuple(f for f in wanted if f in fields)
    before = dict(fields)
    updates, warnings = rule.fn(before, use, p)
    out = dict(before)
    for k, v in updates.items():
        if k in use:
            out[k] = v
    for k in use:
        if isinstance(out[k], str):
            out[k] = tidy(out[k])
    for k in ("title", "artist"):  # a rule never leaves these empty
        if k in use and isinstance(before[k], str) and before[k].strip() and not out[k]:
            out[k] = tidy(before[k]) or before[k]
    changed = tuple(k for k in out if out[k] != before[k])
    return RuleResult(out, changed, [{**w, "rule": rule_id} for w in warnings])


def run_steps(fields: Fields, steps: list[dict]) -> StepsResult:
    """Run an ordered list of rule steps. Each sees the result of the one before.

    `by` says, per field, which steps changed it; `warnings` carries what the
    rules flagged (each with the step and rule that raised it).
    """
    current = dict(fields)
    by: dict[str, list[dict]] = {}
    warnings: list[Warning_] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or "rule" not in step:
            raise RuleError(f"step {i} is not a rule step")
        res = run_rule(step["rule"], current, scope=step.get("fields"), params=step.get("params"))
        for k in res.changed:
            by.setdefault(k, []).append({"step": i, "rule": step["rule"]})
        warnings.extend({**w, "step": i} for w in res.warnings)
        current = res.fields
    return StepsResult(current, by, warnings)
