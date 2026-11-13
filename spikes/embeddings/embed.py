"""Spike #22: one CLAP embedding per track of a Rekordbox library, on the CPU.

Read-only. Opens a COPY of master.db for the track list and reads each audio
file at its FolderPath with ffmpeg. Never writes next to the audio.
Needs ffmpeg on PATH and (no torch, no tensorflow):
    pip install onnxruntime numpy psutil pyrekordbox
    python embed.py <copy-dir> <model.onnx> <out-dir> --tag music [--windows 6]
                    [--full-subset 40] [--sample 0] [--seed 0]

--windows N      N evenly spaced 10 s windows per track, decoded with seeks.
--full-subset K  also embed K random tracks with full coverage: the whole
                 file decoded once and cut into back-to-back 10 s windows.
--sample S       embed only S random tracks (for comparing a second model).

Writes to <out-dir>: <tag>.npz (window embeddings and offsets per track),
<tag>_tracks.json (track metadata: PRIVATE, keep out of the repo) and
<tag>_cost.json (timings, memory, machine).
"""
import argparse, json, random, sys, time, warnings, logging
from pathlib import Path

warnings.simplefilter("ignore"); logging.disable(logging.WARNING)
import numpy as np
import psutil
from pyrekordbox import MasterDatabase

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import SR, WIN, Embedder, decode, embed_track, log_mel, machine  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("copy_dir"); ap.add_argument("model"); ap.add_argument("out_dir")
ap.add_argument("--tag", required=True)
ap.add_argument("--windows", type=int, default=6)
ap.add_argument("--full-subset", type=int, default=0)
ap.add_argument("--sample", type=int, default=0)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()

copy, out = Path(a.copy_dir).resolve(), Path(a.out_dir).resolve()
assert "Pioneer" not in copy.parts, "point this at a copy, not the live library"
repo = Path(__file__).resolve().parents[2]
assert repo not in out.parents and out != repo, "write the output outside the repository"
out.mkdir(parents=True, exist_ok=True)

db = MasterDatabase(path=str(copy / "master.db"), db_dir=str(copy))
rows = [c for c in db.get_content() if not c.rb_local_deleted]
rng = random.Random(a.seed)
if a.sample:
    rows = rng.sample(rows, a.sample)
full_ids = {c.ID for c in random.Random(a.seed + 1).sample(rows, a.full_subset)} if a.full_subset else set()

proc = psutil.Process()
t = time.perf_counter(); emb = Embedder(a.model); load_s = time.perf_counter() - t
emb(np.zeros((1, 1001, 64), np.float32))
rss_after_load = proc.memory_info().rss

timer = {"decode": 0.0, "features": 0.0, "inference": 0.0}
ftimer = {"decode": 0.0, "features": 0.0, "inference": 0.0}
tracks, vecs, offs, full_vecs, full_offs, failed = [], [], [0], [], [0], []
n_full_windows, peak = 0, proc.memory_info().rss
t_all = time.perf_counter()
for i, c in enumerate(rows):
    meta = {"id": str(c.ID), "title": c.Title, "artist": c.Artist.Name if c.Artist else "",
            "bpm": round(c.BPM / 100, 2) if c.BPM else None, "key": c.Key.ScaleName if c.Key else None,
            "genre": c.Genre.Name if c.Genre else None, "plays": int(c.DJPlayCount or 0),
            "length": c.Length, "path": c.FolderPath}
    try:
        if not Path(c.FolderPath).is_file():
            raise FileNotFoundError("audio file missing")
        w = embed_track(c.FolderPath, emb, a.windows, timer)
        if c.ID in full_ids:                         # full coverage, same track
            t = time.perf_counter(); x = decode(c.FolderPath); ftimer["decode"] += time.perf_counter() - t
            t = time.perf_counter()
            starts = [s for s in range(0, len(x), WIN) if s == 0 or len(x) - s >= WIN // 2]
            mels = np.stack([log_mel(x[s:s + WIN]) for s in starts])   # drop a tail under 5 s
            ftimer["features"] += time.perf_counter() - t
            t = time.perf_counter()
            fw = np.concatenate([emb(mels[j:j + 8]) for j in range(0, len(mels), 8)])
            ftimer["inference"] += time.perf_counter() - t
            n_full_windows += len(fw)
            full_vecs.append(fw); full_offs.append(full_offs[-1] + len(fw))
            meta["full_index"] = len(full_offs) - 2
    except Exception as e:  # noqa: BLE001
        failed.append({"id": str(c.ID), "reason": f"{type(e).__name__}: {str(e)[:80]}"})
        continue
    meta["index"] = len(tracks)
    tracks.append(meta); vecs.append(w); offs.append(offs[-1] + len(w))
    peak = max(peak, proc.memory_info().rss)
    if i % 25 == 0:
        print(f"{i}/{len(rows)} {time.perf_counter() - t_all:.0f}s", flush=True)
wall = time.perf_counter() - t_all

n = len(tracks)
np.savez(out / f"{a.tag}.npz", windows=np.concatenate(vecs), offsets=np.array(offs),
         full_windows=np.concatenate(full_vecs) if full_vecs else np.zeros((0, 512), np.float32),
         full_offsets=np.array(full_offs))
(out / f"{a.tag}_tracks.json").write_text(json.dumps({"tracks": tracks, "failed": failed}, indent=1))
mi = proc.memory_info()
cost = {"machine": machine(), "model": Path(a.model).name, "model_mb": round(Path(a.model).stat().st_size / 1e6, 1),
        "model_load_s": round(load_s, 2), "rss_after_load_mb": round(rss_after_load / 2**20),
        "peak_rss_mb": round(max(peak, getattr(mi, "peak_wset", 0) or 0) / 2**20),
        "tracks": n, "failed": len(failed), "windows_per_track": a.windows, "wall_s": round(wall, 1),
        "sampled_s_per_track": {k: round(v / max(n, 1), 3) for k, v in timer.items()},
        "full_tracks": len(full_vecs), "full_windows": n_full_windows,
        "full_s_per_track": {k: round(v / max(len(full_vecs), 1), 3) for k, v in ftimer.items()}}
for k in ("sampled_s_per_track", "full_s_per_track"):
    cost[k]["total"] = round(sum(cost[k].values()), 3)
(out / f"{a.tag}_cost.json").write_text(json.dumps(cost, indent=2))
print(json.dumps(cost, indent=2))
