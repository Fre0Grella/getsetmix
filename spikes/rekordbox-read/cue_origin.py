"""Spike #21, second pass: split the existing cues by how they look to have been made.

Read-only, on a copy:  python cue_origin.py <copy-dir>
"""
import collections, logging, sys, warnings
from pathlib import Path
warnings.simplefilter("ignore"); logging.disable(logging.WARNING)
import numpy as np
from pyrekordbox import MasterDatabase
from pyrekordbox.anlz import AnlzFile

PHRASE_WORDS = {"Intro", "Up", "Down", "Chorus", "Outro", "Verse", "Bridge"}
copy = Path(sys.argv[1]).resolve()
assert "Pioneer" not in copy.parts, "point this at a copy, not the live library"
db = MasterDatabase(path=str(copy / "master.db"), db_dir=str(copy))
cues = [q for q in db.get_cue() if not q.rb_local_deleted]
per_day = collections.Counter(str(q.created_at)[:10] for q in cues)
by_track = collections.defaultdict(list)
for q in cues: by_track[q.ContentID].append(q)

def group(q):
    if q.Comment in PHRASE_WORDS: return "named after a phrase"
    if q.Comment: return "other comment"
    return "no comment, bulk day (>=80 cues)" if per_day[str(q.created_at)[:10]] >= 80 else "no comment, quiet day"

stats = collections.defaultdict(collections.Counter)
for c in db.get_content():
    if c.rb_local_deleted or not c.AnalysisDataPath or c.ID not in by_track: continue
    dat_path = copy / "share" / c.AnalysisDataPath.lstrip("/")
    ext_path = dat_path.with_suffix(".EXT")
    if not (dat_path.exists() and ext_path.exists()): continue
    dat, ext = AnlzFile.parse_file(dat_path), AnlzFile.parse_file(ext_path)
    if "PQTZ" not in dat.tag_types or "PSSI" not in ext.tag_types: continue
    beats, bpms, times = dat.get("beat_grid")
    pssi = ext.get_tag("PSSI").content
    if not len(times) or not pssi.len_entries: continue
    bounds = [e.beat for e in pssi.entries] + [pssi.end_beat]
    down = np.flatnonzero(np.asarray(beats) == 1)
    first_down = int(down[0]) if len(down) else 0
    tarr = np.asarray(times)
    for q in by_track[c.ID]:
        if q.InMsec is None or q.InMsec < 0: continue
        t = q.InMsec / 1000.0
        i = int(np.argmin(np.abs(tarr - t)))
        if abs(tarr[i] - t) > 30.0 / float(bpms[i]): continue
        g = stats[group(q)]
        d = min(abs((i + 1) - b) for b in bounds)
        bar = (i - first_down) / 4.0
        g["cues"] += 1; g["memory"] += q.Kind == 0
        g["on phrase start"] += d == 0
        g["on 8-bar grid"] += bar % 8 == 0
        g["on 16-bar grid"] += bar % 16 == 0
        g["first beat of track"] += i <= 4
for name, g in sorted(stats.items()):
    n = g["cues"]
    print(f"{name}: {n} cues ({g['memory']} memory)")
    for k in ("on phrase start", "on 8-bar grid", "on 16-bar grid", "first beat of track"):
        print(f"    {k}: {g[k]} ({100 * g[k] / n:.0f}%)")
print("days with >=80 cues:", sorted((d, n) for d, n in per_day.items() if n >= 80))
