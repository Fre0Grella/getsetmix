"""Spike #21: what analysis does a Rekordbox library already hold?

Read-only. Opens a COPY of master.db and of the analysis (ANLZ) files:
    pip install pyrekordbox numpy
    python read_rekordbox.py <copy-dir> <out-dir>   # copy-dir holds master.db and share/
Prints coverage counts and writes results.json and phrases.md to <out-dir>.
phrases.md lists 10 tracks by name for a DJ to judge: keep it out of the repo.
"""
import collections, json, logging, statistics, sys, warnings
from pathlib import Path

warnings.simplefilter("ignore"); logging.disable(logging.WARNING)
import numpy as np
from pyrekordbox import MasterDatabase
from pyrekordbox.anlz import AnlzFile

PHRASES = {
    1: {1: "Intro", 2: "Up", 3: "Down", 5: "Chorus", 6: "Outro"},
    2: {1: "Intro", 2: "Verse 1", 3: "Verse 2", 4: "Verse 3", 5: "Verse 4", 6: "Verse 5",
        7: "Verse 6", 8: "Bridge", 9: "Chorus", 10: "Outro"},
    3: {1: "Intro", 2: "Verse 1", 3: "Verse 1", 4: "Verse 1", 5: "Verse 2", 6: "Verse 2",
        7: "Verse 2", 8: "Bridge", 9: "Chorus", 10: "Outro"},
}
MOODS = {1: "high", 2: "mid", 3: "low"}

copy, out_dir = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
assert "Pioneer" not in copy.parts, "point this at a copy, not the live library"
out_dir.mkdir(parents=True, exist_ok=True)
db = MasterDatabase(path=str(copy / "master.db"), db_dir=str(copy))
tracks = [c for c in db.get_content() if not c.rb_local_deleted]

cues_by_track = collections.defaultdict(list)
for cue in db.get_cue():
    if not cue.rb_local_deleted:
        cues_by_track[cue.ContentID].append(cue)

def mmss(sec):
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"

n = collections.Counter()
moods = collections.Counter()
rows = []          # per-track detail for tracks with phrases
cue_stats = collections.Counter()
for c in tracks:
    n["tracks"] += 1
    n["bpm"] += bool(c.BPM and c.BPM > 0)
    n["key"] += bool(c.KeyID)
    db_cues = cues_by_track.get(c.ID, [])
    n["db_hot_cue_tracks"] += any(q.Kind != 0 for q in db_cues)
    n["db_memory_cue_tracks"] += any(q.Kind == 0 for q in db_cues)
    if not c.AnalysisDataPath:
        continue
    dat_path = copy / "share" / c.AnalysisDataPath.lstrip("/")
    if not dat_path.exists():
        continue
    n["anlz_dat"] += 1
    dat = AnlzFile.parse_file(dat_path)
    beats = bpms = times = None
    if "PQTZ" in dat.tag_types:
        beats, bpms, times = dat.get("beat_grid")
        if len(beats):
            n["grid"] += 1
            n["grid_constant_tempo"] += bool(np.ptp(bpms) < 0.01)
    # cues stored in the local analysis files (as opposed to master.db)
    anlz_cues = sum(t.content.count for t in dat.getall_tags("PCOB"))
    ext_path, ex2_path = dat_path.with_suffix(".EXT"), dat_path.with_suffix(".2EX")
    pssi = None
    if ext_path.exists():
        ext = AnlzFile.parse_file(ext_path)
        anlz_cues += sum(t.content.count for t in ext.getall_tags("PCO2"))
        if "PSSI" in ext.tag_types:
            pssi = ext.get_tag("PSSI").content
    n["anlz_local_cues_tracks"] += anlz_cues > 0
    if ex2_path.exists() and "PVDI" in AnlzFile.parse_file(ex2_path).tag_types:
        n["vocal"] += 1
    if pssi is None or not pssi.len_entries or times is None or not len(times):
        continue
    n["phrases"] += 1
    moods[MOODS.get(pssi.mood, str(pssi.mood))] += 1

    # phrase boundaries as beat indexes (1-based into the grid)
    entries = list(pssi.entries)
    bounds = [e.beat for e in entries] + [pssi.end_beat]
    downbeats = np.flatnonzero(np.asarray(beats) == 1)            # 0-based beat idx
    first_down = int(downbeats[0]) if len(downbeats) else 0
    def bar_of(beat_1based):
        return (beat_1based - 1 - first_down) / 4.0
    phrases = []
    for e, nxt in zip(entries, bounds[1:]):
        i = min(max(e.beat - 1, 0), len(times) - 1)
        phrases.append({"start": float(times[i]), "bars": (nxt - e.beat) / 4.0,
                        "label": PHRASES.get(pssi.mood, {}).get(e.kind, f"kind {e.kind}"),
                        "on_bar": abs(bar_of(e.beat) - round(bar_of(e.beat))) < 1e-9})
    n["phrase_count"] += len(phrases)
    n["phrase_on_downbeat"] += sum(p["on_bar"] for p in phrases)
    n["phrase_len_multiple_of_8_bars"] += sum(p["bars"] % 8 == 0 for p in phrases)
    n["phrase_len_multiple_of_4_bars"] += sum(p["bars"] % 4 == 0 for p in phrases)

    # the DJ's own cues vs phrase boundaries, and vs a naive 16-bar / 8-bar grid
    cues = []
    tarr = np.asarray(times)
    for q in db_cues:
        if q.InMsec is None or q.InMsec < 0:
            continue
        t = q.InMsec / 1000.0
        i = int(np.argmin(np.abs(tarr - t)))                       # nearest beat, 0-based
        beat_len = 60.0 / float(bpms[i])
        if abs(tarr[i] - t) > beat_len / 2:                        # outside the grid
            continue
        d_phrase = min(abs((i + 1) - b) for b in bounds)
        bar = (i - first_down) / 4.0
        cue_stats["cues"] += 1
        cue_stats["on_phrase_boundary"] += d_phrase == 0
        cue_stats["within_1_bar_of_boundary"] += d_phrase <= 4
        cue_stats["on_16_bar_grid"] += bar % 16 == 0
        cue_stats["on_8_bar_grid"] += bar % 8 == 0
        cue_stats["on_any_downbeat"] += bar % 1 == 0
        cues.append({"t": t, "kind": "memory" if q.Kind == 0 else f"hot {chr(64 + q.Kind)}",
                     "on_boundary": d_phrase == 0})
    # how many phrase boundaries does the 8-bar grid produce vs Rekordbox (for a fair baseline)
    total_bars = (len(beats) - first_down) / 4.0
    cue_stats["rb_boundaries"] += len(bounds)
    cue_stats["grid8_boundaries"] += int(total_bars // 8) + 1
    cue_stats["grid16_boundaries"] += int(total_bars // 16) + 1
    rows.append({"title": c.Title, "artist": c.Artist.Name if c.Artist else "", "bpm": c.BPM / 100,
                 "key": c.Key.ScaleName if c.Key else "", "length": c.Length,
                 "mood": MOODS.get(pssi.mood, "?"), "plays": c.DJPlayCount or 0,
                 "phrases": phrases, "cues": sorted(cues, key=lambda x: x["t"])})

bpm_values = [c.BPM / 100 for c in tracks if c.BPM]
out = {"counts": dict(n), "moods": dict(moods), "cue_vs_phrase": dict(cue_stats),
       "bpm": {"min": min(bpm_values), "median": statistics.median(bpm_values), "max": max(bpm_values)}}
print(json.dumps(out, indent=2))
(out_dir / "results.json").write_text(json.dumps(out, indent=2))

# 10 tracks the DJ knows best: most played, with phrases and at least one cue
def plays(r):
    try: return int(r["plays"])
    except (TypeError, ValueError): return 0
best = sorted([r for r in rows if r["cues"]], key=plays, reverse=True)[:10]
lines = ["# Rekordbox phrases on 10 most-played tracks (local file, not for the repo)", ""]
for r in best:
    lines += [f"## {r['artist']} - {r['title']}",
              f"{r['bpm']:.1f} BPM, {r['key']}, {mmss(r['length'])}, mood: {r['mood']}, plays: {r['plays']}", "",
              "| At | Phrase | Bars | Your cue here |", "|---|---|---|---|"]
    for p in r["phrases"]:
        here = ", ".join(q["kind"] for q in r["cues"] if abs(q["t"] - p["start"]) < 0.05)
        lines.append(f"| {mmss(p['start'])} | {p['label']} | {p['bars']:g} | {here} |")
    off = [f"{q['kind']} at {mmss(q['t'])}" for q in r["cues"] if not q["on_boundary"]]
    lines += ["", "Your cues that are not on a phrase start: " + (", ".join(off) or "none"), ""]
(out_dir / "phrases.md").write_text("\n".join(lines), encoding="utf-8")
print("wrote phrases.md for", len(best), "tracks")
