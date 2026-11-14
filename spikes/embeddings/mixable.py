"""Spike #22, second look: key first, genre second.

The maintainer cares less about genre and more about harmonic mixing, and
hopes the embeddings find good mixes *across* genres. This script measures
that and writes a listening page.

- How often a model's nearest neighbours are key-compatible (Camelot: same
  key, one step on the wheel, or the relative major/minor), and also
  mixable (key-compatible and BPM within 6%, half and double time included),
  against shuffled labels.
- "Mix-ready" neighbours: keep only the tracks that are mixable with the seed
  (key and BPM come from Rekordbox, exactly), then rank them by the model's
  similarity. How many seeds have enough candidates, and how many of the top
  picks are in another genre.

Usage: python mixable.py <emb_dir> <out_dir> [--tags general,music]
Writes <out_dir>/mixable.json and <out_dir>/mixable.html (track names and
file links: keep it outside the repository).
"""
import argparse
import html
import json
from pathlib import Path

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("emb_dir")
ap.add_argument("out_dir")
ap.add_argument("--tags", default="general,music")
ap.add_argument("--min-length", type=float, default=60, help="skip samples and one-shots shorter than this (s)")
a = ap.parse_args()
src, out = Path(a.emb_dir).resolve(), Path(a.out_dir).resolve()
repo = Path(__file__).resolve().parents[2]
assert repo not in out.parents and out != repo, "write the output outside the repository"
TAGS = a.tags.split(",")
NAMES = {"general": "general model (clap-htsat-unfused)", "music": "music model (larger_clap_music)"}
rng = np.random.default_rng(0)
e = html.escape


def unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def load(tag):
    z = np.load(src / f"{tag}.npz")
    meta = json.loads((src / f"{tag}_tracks.json").read_text(encoding="utf-8"))
    w, o = z["windows"], z["offsets"]
    return meta["tracks"], {x["id"]: unit(unit(w[o[i]:o[i + 1]]).mean(0)) for i, x in enumerate(meta["tracks"])}


def camelot(k):
    names = {"Dm": "7A", "Am": "8A", "E": "12B", "D": "10B", "Em": "9A", "Gm": "6A"}
    k = names.get(k, k)
    if not k or k[-1] not in "AB" or not k[:-1].isdigit():
        return None
    return int(k[:-1]), k[-1]


def key_ok(x, y):
    d = (x[0] - y[0]) % 12
    return (x[1] == y[1] and d in (0, 1, 11)) or x[0] == y[0]


def bpm_ok(x, y):
    return any(abs(x * m / y - 1) <= 0.06 for m in (0.5, 1, 2))


runs = {t: load(t) for t in TAGS}
ids = set.intersection(*(set(runs[t][1]) for t in TAGS))
tracks = [x for x in runs[TAGS[0]][0] if x["id"] in ids
          and camelot(x["key"]) and x["bpm"] and (x["length"] or 0) >= a.min_length]
n = len(tracks)
K = [camelot(x["key"]) for x in tracks]
B = [float(x["bpm"]) for x in tracks]
G = [x["genre"] for x in tracks]
KEY = np.array([[key_ok(K[i], K[j]) for j in range(n)] for i in range(n)])
BPM = np.array([[bpm_ok(B[i], B[j]) for j in range(n)] for i in range(n)])
MIX = KEY & BPM
np.fill_diagonal(KEY, False)
np.fill_diagonal(MIX, False)
R = {"tracks": n, "note": f"tracks with a key, a BPM and at least {a.min_length:.0f} s",
     "share_of_all_pairs": {"key_compatible": float(KEY.mean()), "mixable": float(MIX.mean())}, "models": {}}


def rate(NN, M):
    return float(np.mean([M[i, j] for i in range(n) for j in NN[i]]))


def shuffled(NN, labels_ok, shuffles=300):
    """Rate under shuffled keys and BPMs (the neighbours stay, the labels move)."""
    vals = []
    for _ in range(shuffles):
        p = rng.permutation(n)
        vals.append(float(np.mean([labels_ok(p[i], p[j]) for i in range(n) for j in NN[i]])))
    return float(np.mean(vals)), float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


seeds = sorted(range(n), key=lambda i: (-tracks[i]["plays"], tracks[i]["id"]))[:20]
pages = {}
for tag in TAGS:
    V = np.stack([runs[tag][1][x["id"]] for x in tracks])
    S = V @ V.T
    np.fill_diagonal(S, -np.inf)
    NN = np.argsort(-S, axis=1)[:, :10]
    m = {}
    for name, M in (("key_compatible", KEY), ("mixable", MIX)):
        base = shuffled(NN, lambda i, j, M=M: M[i, j])
        m[name + "_top10"] = {"rate": rate(NN, M), "shuffled_mean": base[0], "shuffled_95": [base[1], base[2]]}
    # Mix-ready: candidates mixable with the seed, ranked by similarity.
    picks, cross, cands, sims_top, sims_rand = [], [], [], [], []
    for i in range(n):
        c = np.flatnonzero(MIX[i])
        cands.append(len(c))
        if len(c) == 0:
            picks.append([])
            continue
        top = c[np.argsort(-S[i, c])][:5]
        picks.append(list(top))
        sims_top.append(float(S[i, top].mean()))
        sims_rand.append(float(S[i, c].mean()))
        for j in top:
            if G[i] and G[j]:
                cross.append(G[i] != G[j])
    m["mix_ready"] = {
        "candidates_per_seed": {"median": float(np.median(cands)), "p10": float(np.percentile(cands, 10)),
                                "seeds_with_at_least_5": int(sum(c >= 5 for c in cands))},
        "top5_other_genre_share": float(np.mean(cross)) if cross else None,
        "top5_mean_similarity": float(np.mean(sims_top)),
        "all_candidates_mean_similarity": float(np.mean(sims_rand)),
    }
    R["models"][tag] = m

    def row(i, j, k):
        x = tracks[j]
        other = G[i] and G[j] and G[i] != G[j]
        return (f"<tr{' class=x' if other else ''}><td class=n>{k}</td><td><button class=play data-src=\""
                f"{e(Path(x['path']).as_uri())}\" data-name=\"{e((x['artist'] or '') + ' - ' + (x['title'] or ''))}\">"
                f"&#9654;</button></td><td>{e(x['artist'] or '')}</td><td>{e(x['title'] or '')}</td>"
                f"<td class=n>{x['bpm']}</td><td>{e(x['key'])}</td><td>{e(x['genre'] or '-')}</td>"
                f"<td class=n>{S[i, j]:.3f}</td></tr>")

    secs = []
    for r, i in enumerate(seeds, 1):
        x = tracks[i]
        body = "".join(row(i, j, k) for k, j in enumerate(picks[i][:10], 1)) or "<tr><td colspan=8>no mixable track</td></tr>"
        secs.append(f"<section><h2>{r}. <button class=play data-src=\"{e(Path(x['path']).as_uri())}\" "
                    f"data-name=\"{e((x['artist'] or '') + ' - ' + (x['title'] or ''))}\">&#9654;</button> "
                    f"{e(x['artist'] or '')} - {e(x['title'] or '')} <small>{x['bpm']} BPM · {e(x['key'])} · "
                    f"{e(x['genre'] or '-')} · {cands[i]} mixable tracks</small></h2><table><tbody>{body}</tbody></table></section>")
    pages[tag] = "".join(secs)

(out / "mixable.json").write_text(json.dumps(R, indent=1), encoding="utf-8")
opts = "".join(f"<option value={t}>{e(NAMES.get(t, t))}</option>" for t in TAGS)
divs = "".join(f"<div class=model data-tag={t}>{pages[t]}</div>" for t in TAGS)
(out / "mixable.html").write_text(f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<title>Mix-ready neighbours (spike #22)</title><style>
body{{margin:0;font:14px/1.45 system-ui,Segoe UI,sans-serif;background:#fcfcfb;color:#0b0b0b}}
header{{position:sticky;top:0;background:#fcfcfb;border-bottom:1px solid #e1e0d9;padding:10px 20px;z-index:5}}
h1{{font-size:18px;margin:0 0 4px}}p{{color:#5f5e58;margin:2px 0;max-width:80em}}main{{padding:8px 20px 40px}}
h2{{font-size:15px;margin:20px 0 6px}}h2 small{{color:#5f5e58;font-weight:normal}}
table{{border-collapse:collapse;width:100%;max-width:1100px}}td{{padding:3px 8px;border-bottom:1px solid #e1e0d9}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}tr.x td{{background:#eef4fc}}
button.play{{border:1px solid #e1e0d9;background:#fff;border-radius:4px;width:30px;height:26px;cursor:pointer;color:#2a78d6}}
button.play.on{{background:#2a78d6;color:#fff}}div.model{{display:none}}div.model.on{{display:block}}audio{{height:32px;width:420px}}
</style></head><body><header><h1>Mix-ready neighbours: the 20 most-played tracks</h1>
<p>Only tracks you could mix into the seed are listed: Camelot-compatible key (same, one step, or relative
major/minor) and BPM within 6% (half and double time count), both from Rekordbox. Among those, the model
orders them by how similar they sound. <b>Blue rows are another genre</b>: the cross-genre mixes.</p>
<p><label>Model <select id=model>{opts}</select></label> <audio id=player controls preload=none></audio>
<label><input type=checkbox id=mid checked> start at 30%</label> <span id=now></span></p></header>
<main>{divs}</main><script>
const player=document.getElementById('player'),now=document.getElementById('now'),mid=document.getElementById('mid');let cur=null;
document.addEventListener('click',ev=>{{const b=ev.target.closest('button.play');if(!b)return;if(cur)cur.classList.remove('on');
cur=b;b.classList.add('on');player.src=b.dataset.src;now.textContent=b.dataset.name;
player.onloadedmetadata=()=>{{if(mid.checked&&player.duration>40)player.currentTime=player.duration*0.3;player.play();}};}});
const sel=document.getElementById('model');function show(){{document.querySelectorAll('div.model').forEach(d=>d.classList.toggle('on',d.dataset.tag===sel.value));}}
sel.onchange=show;show();</script></body></html>""", encoding="utf-8")
print(json.dumps(R, indent=1))
