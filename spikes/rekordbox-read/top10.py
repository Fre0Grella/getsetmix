"""Spike #21: on the 10 most-played tracks, whose cues the DJ vouches for,
how do Rekordbox's phrase starts compare with the cue positions?
Read-only, on a copy:  python top10.py <copy-dir>   (prints counts only, no titles)"""
import collections, logging, sys, warnings
from pathlib import Path
warnings.simplefilter("ignore"); logging.disable(logging.WARNING)
import numpy as np
from pyrekordbox import MasterDatabase
from pyrekordbox.anlz import AnlzFile

copy = Path(sys.argv[1]).resolve()
assert "Pioneer" not in copy.parts, "point this at a copy, not the live library"
db = MasterDatabase(path=str(copy / "master.db"), db_dir=str(copy))
by_track = collections.defaultdict(list)
for q in db.get_cue():
    if not q.rb_local_deleted and q.InMsec is not None and q.InMsec >= 0:
        by_track[q.ContentID].append(q)
rows = []
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
    try: plays = int(c.DJPlayCount or 0)
    except (TypeError, ValueError): plays = 0
    rows.append((plays, c, np.asarray(times), bpms, [e.beat for e in pssi.entries]))
rows.sort(key=lambda r: r[0], reverse=True)
tot = collections.Counter(); offs = collections.Counter()
for n, (plays, c, tarr, bpms, starts) in enumerate(rows[:10], 1):
    cue_beats = set()
    for q in by_track[c.ID]:
        t = q.InMsec / 1000.0
        i = int(np.argmin(np.abs(tarr - t)))
        if abs(tarr[i] - t) <= 30.0 / float(bpms[i]): cue_beats.add(i + 1)
    cue_beats = sorted(cue_beats)
    hit = [b for b in cue_beats if b in starts]
    miss = [min((b - s for s in starts), key=abs) for b in cue_beats if b not in starts]
    unused = [s for s in starts if s not in cue_beats]
    for d in miss: offs["within 1 bar" if abs(d) <= 4 else "2 to 4 bars" if abs(d) <= 16 else "more than 4 bars"] += 1
    tot["cue positions"] += len(cue_beats); tot["on a phrase start"] += len(hit)
    tot["phrase starts"] += len(starts); tot["phrase starts with no cue"] += len(unused)
    print(f"track {n}: {len(cue_beats)} cue positions, {len(hit)} on a phrase start, "
          f"misses (bars off): {[round(d / 4, 2) for d in miss]}; {len(starts)} phrase starts, {len(unused)} without a cue")
print(dict(tot)); print("misses by distance:", dict(offs))
