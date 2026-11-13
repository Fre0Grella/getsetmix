"""The cleanup rules: the table of cases, the properties every rule keeps, the
built-in set, and a check that the design document and the table agree.

Design: docs/design/batch-editing.md, sections 4.1 and 4.2.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from app import genres, rules

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((Path(__file__).parent / "rules_cases.json").read_text(encoding="utf-8"))
DESIGN = ROOT / "docs" / "design" / "batch-editing.md"
CATALOGUE_IDS = [
    "trim", "promo.remove", "url.remove", "split.artist_title", "feat.normalise",
    "feat.move", "mix.remove_default", "mix.brackets", "artist.separators",
    "case.title", "genre.map", "year.extract",
]
IDS = [c["id"] for c in CASES]


def run_case(case, fields=None):
    return rules.run_rule(
        case["rule"], copy.deepcopy(fields if fields is not None else case["in"]),
        scope=case.get("scope"), params=case.get("params"),
    )


def expected(case):
    return {**case["in"], **case["out"]}


# ------------------------------------------------------------ the table

def test_every_catalogue_rule_has_cases():
    assert {c["rule"] for c in CASES} == set(CATALOGUE_IDS)
    assert [r["id"] for r in rules.catalogue()["rules"]] == CATALOGUE_IDS


def test_case_ids_are_unique():
    assert len(IDS) == len(set(IDS))


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case(case):
    result = run_case(case)
    assert result.fields == expected(case)
    assert sorted(w["warning"] for w in result.warnings) == sorted(case.get("warnings", []))


# ------------------------------------------------------------ properties

@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_idempotent(case):
    once = run_case(case)
    twice = run_case(case, once.fields)
    assert twice.fields == once.fields


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_never_empties_title_or_artist(case):
    out = run_case(case).fields
    for field in ("title", "artist"):
        if case["in"].get(field, "").strip():
            assert out[field].strip(), field


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_leaves_other_fields_alone(case):
    decoys = {
        "title": "  Decoy (Original Mix) [HQ] x feat. y  ", "artist": " decoy x feat. y ",
        "album": " decoy (2019) ", "genre": " dEcOy ", "comment": " see www.example.com ",
        "year": None,
    }
    # 1. a field the rule was not given is never added or changed
    given = dict(case["in"])
    out = run_case(case, given).fields
    assert set(out) == set(given)
    # 2. a field outside the step's scope is never changed, whatever the rule does
    scope = case.get("scope") or [f for f in given if f in rules.allowed_fields(case["rule"])]
    for field, decoy in decoys.items():
        if field in given:
            continue
        out = rules.run_rule(case["rule"], {**given, field: decoy}, scope=scope,
                             params=case.get("params")).fields
        assert out[field] == decoy, field


def test_scope_limits_a_step():
    fields = {"title": "night  drive", "artist": "nova  x kito", "album": "a  b"}
    out = rules.run_rule("trim", fields, scope=["album"]).fields
    assert out == {"title": "night  drive", "artist": "nova  x kito", "album": "a b"}


NASTY = [
    "(Original Mix)", "[HQ]", "(Official Video)", "www.example.com", "@nova", " - ", "()", "[]", ",",
    "feat. Kito", "(feat. Kito)", "(2019)", "[Kito Remix]", "- Kito Remix", "x", "  ", "Remix",
    "nova x kito", "Original Mix", "( )", "-", "Nova -", "; ;",
]


@pytest.mark.parametrize("rule", CATALOGUE_IDS)
def test_no_rule_empties_title_or_artist_on_nasty_input(rule):
    for text in NASTY:
        if not text.strip():
            continue
        for fields in ({"title": text, "artist": "Nova", "year": None, "album": "", "genre": ""},
                       {"title": "Night Drive", "artist": text, "year": None, "album": "", "genre": ""},
                       {"title": text, "artist": "", "year": None, "album": "", "genre": ""}):
            out = rules.run_rule(rule, dict(fields), scope=list(rules.allowed_fields(rule))).fields
            for field in ("title", "artist"):
                if fields[field].strip():
                    assert out[field].strip(), (rule, field, fields)
            # and the rule is idempotent on all of it
            again = rules.run_rule(rule, dict(out), scope=list(rules.allowed_fields(rule))).fields
            assert again == out, (rule, fields)


UNICODE = [
    "Café del Mar – Ñandú", "夜のドライブ", "الليل الطويل",
    "לילה טוב", "Night Drive \U0001f525\U0001f3a7", "\U0001f468‍\U0001f469‍\U0001f467 Family",
    "Élan Vital", "Διονυσος", "Nova ‏(Kito)‎",
]


@pytest.mark.parametrize("rule", CATALOGUE_IDS)
def test_unicode_passes_through_whole(rule):
    for text in UNICODE:
        fields = {"title": text, "artist": text, "album": text, "genre": "", "year": None}
        out = rules.run_rule(rule, dict(fields), scope=list(rules.allowed_fields(rule))).fields
        assert out["title"] == text and out["artist"] == text and out["album"] == text, (rule, text)


def test_lower_case_accents_and_scripts_are_cased_not_mangled():
    out = rules.run_rule("case.title", {"title": "été à paris \U0001f525 夜"}).fields
    assert out["title"] == "Été À Paris \U0001f525 夜"


# ------------------------------------------------------------ the runner

def test_unknown_rule_param_and_field_are_refused():
    with pytest.raises(rules.RuleError):
        rules.run_steps({"title": "x"}, [{"rule": "nope"}])
    with pytest.raises(rules.RuleError):
        rules.run_steps({"title": "x"}, [{"rule": "trim", "params": {"bogus": 1}}])
    with pytest.raises(rules.RuleError):
        rules.run_steps({"title": "x"}, [{"rule": "trim", "fields": ["cover"]}])
    with pytest.raises(rules.RuleError):
        rules.run_steps({"title": "x"}, [{"rule": "case.title", "params": {"scope": "sometimes"}}])
    with pytest.raises(rules.RuleError):
        rules.run_steps({"title": "x"}, [{"op": "set", "field": "genre", "value": "x"}])


def test_run_steps_does_not_touch_its_input():
    fields = {"title": " a  b "}
    rules.run_steps(fields, [{"rule": "trim"}])
    assert fields == {"title": " a  b "}


def test_run_steps_reports_which_steps_changed_a_field():
    res = rules.run_steps(
        {"title": "night drive (original mix) [free download]", "artist": "Nova", "genre": "Techno"},
        [{"rule": "promo.remove"}, {"rule": "mix.remove_default"}, {"rule": "case.title"}],
    )
    assert res.fields["title"] == "Night Drive"
    assert res.by == {"title": [{"step": 0, "rule": "promo.remove"},
                                {"step": 1, "rule": "mix.remove_default"},
                                {"step": 2, "rule": "case.title"}]}
    assert res.warnings == []


def test_each_step_sees_the_result_of_the_one_before():
    res = rules.run_steps({"title": "a_b"}, [{"rule": "trim", "params": {"underscores": True}},
                                             {"rule": "case.title"}])
    assert res.fields["title"] == "A B"


def test_tidy_runs_after_every_step():
    # nothing in url.remove squeezes spaces; the tidy pass does
    res = rules.run_steps({"title": "Night   Drive () [ ] -"}, [{"rule": "url.remove"}])
    assert res.fields["title"] == "Night Drive"


def test_warnings_come_back_with_field_step_and_value():
    res = rules.run_steps({"genre": "Dark Disco"}, [{"rule": "trim"}, {"rule": "genre.map"}])
    assert res.warnings == [{"warning": "not_in_genre_list", "field": "genre", "step": 1,
                             "rule": "genre.map", "value": "Dark Disco"}]


# ------------------------------------------------------------ the built-in set

def test_standard_cleanup_order_is_the_designs():
    assert [s["rule"] for s in rules.STANDARD_CLEANUP] == [
        "promo.remove", "url.remove", "trim", "split.artist_title", "feat.normalise",
        "feat.move", "mix.remove_default", "mix.brackets", "artist.separators",
        "case.title", "genre.map",
    ]
    assert rules.STANDARD_CLEANUP[5] == {"rule": "feat.move", "params": {"to": "title"}}
    assert rules.BUILTIN_RULESETS[0]["name"] == "Standard cleanup"
    assert rules.BUILTIN_RULESETS[0]["builtin"] is True


MESSY = [
    # (input, expected fields, expected warnings)
    ({"title": "  nova - night drive (original mix) [free download] ", "artist": "", "album": "",
      "genre": "tech-house", "year": None},
     {"title": "Night Drive", "artist": "nova", "album": "", "genre": "Tech House", "year": None}, []),
    ({"title": "Night Drive - Kito Remix", "artist": "Nova ft Sol", "album": "", "genre": "", "year": None},
     {"title": "Night Drive (feat. Sol) (Kito Remix)", "artist": "Nova", "album": "", "genre": "",
      "year": None}, []),
    ({"title": "lost in the city (Official Video) www.example.com", "artist": "Sun x Moon",
      "album": "the hits", "genre": "hiphop", "year": None},
     {"title": "Lost in the City", "artist": "Sun, Moon", "album": "The Hits", "genre": "Hip-Hop",
      "year": None}, []),
    ({"title": "夜のドライブ [HQ]", "artist": "ナオ & Kito", "album": "",
      "genre": "Dark Disco", "year": None},
     {"title": "夜のドライブ", "artist": "ナオ & Kito", "album": "",
      "genre": "Dark Disco", "year": None}, ["not_in_genre_list"]),
    ({"title": "(Original Mix)", "artist": "@nova", "album": "", "genre": "", "year": None},
     {"title": "(Original Mix)", "artist": "@nova", "album": "", "genre": "", "year": None}, []),
    # capitals stay; the separator rule still applies to the artist
    ({"title": "NIGHT DRIVE", "artist": "NOVA x KITO", "album": "", "genre": "House", "year": 2019},
     {"title": "NIGHT DRIVE", "artist": "NOVA, KITO", "album": "", "genre": "House", "year": 2019}, []),
    ({"title": "night drive", "artist": "Nova feat. kito", "album": "", "genre": "", "year": None},
     {"title": "Night Drive (feat. Kito)", "artist": "Nova", "album": "", "genre": "", "year": None}, []),
    ({"title": "Night Drive", "artist": "Nova", "album": "Hits", "genre": "House", "year": 2019},
     {"title": "Night Drive", "artist": "Nova", "album": "Hits", "genre": "House", "year": 2019}, []),
]


@pytest.mark.parametrize("fields, want, warnings", MESSY, ids=[str(i) for i in range(len(MESSY))])
def test_standard_cleanup_on_messy_input(fields, want, warnings):
    res = rules.run_steps(fields, rules.STANDARD_CLEANUP)
    assert res.fields == want
    assert [w["warning"] for w in res.warnings] == warnings
    # a second run finds nothing left to do
    again = rules.run_steps(res.fields, rules.STANDARD_CLEANUP)
    assert again.fields == res.fields and again.by == {}


def test_order_matters_case_before_split_capitalises_the_artist_too():
    fields = {"title": "nova - night drive", "artist": ""}
    standard = rules.run_steps(fields, [{"rule": "split.artist_title"}, {"rule": "case.title"}])
    swapped = rules.run_steps(fields, [{"rule": "case.title"}, {"rule": "split.artist_title"}])
    assert standard.fields == {"title": "Night Drive", "artist": "nova"}
    assert swapped.fields == {"title": "Night Drive", "artist": "Nova"}


def test_order_matters_case_must_run_after_feat_move():
    fields = {"title": "night drive", "artist": "Nova feat. kito"}
    move_first = rules.run_steps(fields, [{"rule": "feat.move"}, {"rule": "case.title"}])
    case_first = rules.run_steps(fields, [{"rule": "case.title"}, {"rule": "feat.move"}])
    assert move_first.fields["title"] == "Night Drive (feat. Kito)"
    assert case_first.fields["title"] == "Night Drive (feat. kito)"


# ------------------------------------------------------------ the catalogue

def test_catalogue_shape():
    cat = rules.catalogue()
    assert cat["version"] == rules.CATALOGUE_VERSION == 1
    assert cat["rulesets"] == rules.BUILTIN_RULESETS
    by_id = {r["id"]: r for r in cat["rules"]}
    assert list(by_id) == CATALOGUE_IDS
    for rule in cat["rules"]:
        for key in ("name", "description"):
            assert rule[key]["en"] and rule[key]["it"], (rule["id"], key)
        assert rule["fields"] == list(rules.default_fields(rule["id"]))
        assert isinstance(rule["cross_field"], bool)
        assert rule["examples"], rule["id"]
        for p in rule["params"]:
            assert {"name", "type", "default"} <= set(p)
    assert by_id["feat.move"]["cross_field"] and by_id["split.artist_title"]["cross_field"]
    assert by_id["year.extract"]["cross_field"] and not by_id["trim"]["cross_field"]
    defaults = {r["id"]: {p["name"]: p["default"] for p in r["params"]} for r in cat["rules"]}
    assert defaults["feat.move"] == {"to": "title"}
    assert defaults["case.title"]["scope"] == "lower"
    assert defaults["artist.separators"]["to"] == ", "
    assert " & " not in defaults["artist.separators"]["from"]
    assert " and " not in defaults["artist.separators"]["from"]
    assert defaults["artist.separators"]["keep"] == []
    assert defaults["trim"] == {"underscores": False}
    assert defaults["split.artist_title"] == {"when": "artist_empty_or_same"}
    assert defaults["feat.normalise"] == {"spelling": "feat."}
    assert "Free Download" in defaults["promo.remove"]["phrases"]
    assert "Original Mix" in defaults["mix.remove_default"]["labels"]
    assert "Remix" in defaults["mix.brackets"]["mix_words"]
    assert defaults["year.extract"] == {"remove": False}
    assert defaults["genre.map"]["aliases"]["DnB"] == "Drum & Bass"


def test_default_fields_match_the_design_table():
    assert {r: list(rules.default_fields(r)) for r in CATALOGUE_IDS} == {
        "trim": ["title", "artist", "album", "genre"],
        "promo.remove": ["title"],
        "url.remove": ["title", "artist", "album"],
        "split.artist_title": ["title", "artist"],
        "feat.normalise": ["title", "artist"],
        "feat.move": ["title", "artist"],
        "mix.remove_default": ["title"],
        "mix.brackets": ["title"],
        "artist.separators": ["artist"],
        "case.title": ["title", "album"],
        "genre.map": ["genre"],
        "year.extract": ["year", "title", "album"],
    }


def test_every_catalogue_example_runs_as_stated():
    for rule in rules.catalogue()["rules"]:
        for ex in rule["examples"]:
            res = rules.run_rule(rule["id"], dict(ex["before"]), params=ex.get("params"))
            assert res.fields == {**ex["before"], **ex["after"]}, (rule["id"], ex)


def test_genre_list_is_the_uis_list():
    assert len(genres.GENRES) == 42 and len(set(genres.GENRES)) == 42
    assert genres.GENRES[0] == "Afro House" and genres.GENRES[-1] == "UK Garage"
    assert set(genres.GENRE_PICKS) <= set(genres.GENRES)
    keys = {rules.genre_key(g) for g in genres.GENRES}
    assert len(keys) == len(genres.GENRES)  # no two names collapse onto one match key


# ------------------------------------------------------------ design and cases agree

# Rows of the design that cannot be turned into a case, with the reason. Empty on
# purpose: every row of 4.2 is a case. Add a row here only with a reason.
UNTESTABLE_ROWS: dict[str, str] = {}


def design_example_rows() -> list[str]:
    """Every row of every Before/After table in section 4.2, as one string."""
    text = DESIGN.read_text(encoding="utf-8")
    section = text[text.index("### 4.2 "):text.index("### 4.3 ")]
    rows: list[str] = []
    in_examples = False
    for line in section.split("\n"):
        if not line.startswith("|"):
            in_examples = False
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if "Before" in cells and "After" in cells:
            in_examples = True
            continue
        if in_examples and not set(cells[0]) <= set("-|"):
            rows.append(" | ".join(cells))
    return rows


def test_the_parser_finds_the_design_tables():
    rows = design_example_rows()
    assert len(rows) >= 50
    assert any("Night Drive (Original Mix)" in r for r in rows)
    assert any("Dark Disco" in r for r in rows)


def test_every_design_row_is_a_case():
    covered = {d for c in CASES for d in c.get("doc", [])}
    missing = [r for r in design_example_rows() if r not in covered and r not in UNTESTABLE_ROWS]
    assert not missing, "design rows with no case in tests/rules_cases.json:\n" + "\n".join(missing)


def test_every_case_that_cites_the_design_cites_a_real_row():
    rows = set(design_example_rows())
    stale = [(c["id"], d) for c in CASES for d in c.get("doc", []) if d not in rows]
    assert not stale, f"cases citing rows the design no longer has: {stale}"


def test_untestable_rows_are_real_and_not_covered_twice():
    rows = set(design_example_rows())
    covered = {d for c in CASES for d in c.get("doc", [])}
    for row in UNTESTABLE_ROWS:
        assert row in rows and row not in covered


def test_cases_file_is_well_formed():
    for c in CASES:
        assert set(c) <= {"id", "rule", "doc", "params", "scope", "in", "out", "warnings"}, c["id"]
        assert c["id"].startswith(c["rule"] + ":")
        assert set(c["out"]) <= set(c["in"]), c["id"]
        assert re.fullmatch(r"[a-z._]+", c["rule"])
