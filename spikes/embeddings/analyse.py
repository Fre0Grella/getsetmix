"""Spike #22: neighbours, sanity numbers, 2-D layouts and the two local pages.

Reads what embed.py wrote (no audio, no model) and needs:
    pip install numpy scikit-learn umap-learn
    python analyse.py <emb-dir> <out-dir> [--tags general,music]

Each tag is one embed.py run over the whole library (one model). For the
pooling comparison a model's full-coverage windows come from its own run
(--full-subset) or from a run tagged <tag>full. Writes to <out-dir>:
- analysis.json: numbers only (pooling stability, agreement with the hand-set
  genres, BPM and key, agreement between models, layout cost and quality);
- neighbours.html and map.html: PRIVATE pages with titles, artists and
  file:/// links to the audio, for listening, with a switch between models.
  Keep them out of the repo.
"""
import argparse, html, json, time
from pathlib import Path

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("emb_dir"); ap.add_argument("out_dir")
ap.add_argument("--tags", default="general,music", help="the first is the pages' default model")
a = ap.parse_args()
src, out = Path(a.emb_dir).resolve(), Path(a.out_dir).resolve()
repo = Path(__file__).resolve().parents[2]
assert repo not in out.parents and out != repo, "write the output outside the repository"
out.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)
TAGS = a.tags.split(",")


def load(tag):
    z = np.load(src / f"{tag}.npz")
    meta = json.loads((src / f"{tag}_tracks.json").read_text(encoding="utf-8"))
    w, o = z["windows"], z["offsets"]
    fw, fo = z["full_windows"], z["full_offsets"]
    return (meta["tracks"], [w[o[i]:o[i + 1]] for i in range(len(o) - 1)],
            [fw[fo[i]:fo[i + 1]] for i in range(len(fo) - 1)], meta["failed"],
            json.loads((src / f"{tag}_cost.json").read_text()))


def unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def pool(w, pick=None):
    """Mean of the L2-normalised windows, normalised again."""
    if pick is not None and len(w) == 6:
        w = w[pick]
    return unit(unit(w).mean(0))


def knn(V, k):
    S = V @ V.T
    np.fill_diagonal(S, -np.inf)
    return np.argsort(-S, axis=1)[:, :k], S


def overlap(A, B):
    return float(np.mean([len(set(x) & set(y)) / len(x) for x, y in zip(A, B)]))


def camelot(k):
    names = {"Dm": "7A", "Am": "8A", "E": "12B", "D": "10B", "Em": "9A", "Gm": "6A"}
    k = names.get(k, k)
    if not k or k[-1] not in "AB":
        return None
    return int(k[:-1]), k[-1]


def key_ok(x, y):    # same key, a neighbour on the Camelot wheel, or the relative major/minor
    d = (x[0] - y[0]) % 12
    return (x[1] == y[1] and d in (0, 1, 11)) or x[0] == y[0]


def bpm_ok(x, y):    # within 6%, half and double time included
    return any(abs(x * m / y - 1) <= 0.06 for m in (0.5, 1, 2))


def agreement(V, labels, same, k=5, shuffles=1000):
    """Share of top-k neighbours whose label agrees, against shuffled labels."""
    idx = [i for i, l in enumerate(labels) if l is not None]
    lab = [labels[i] for i in idx]
    N, _ = knn(V[idx], k)

    def score(L):
        return float(np.mean([same(L[i], L[j]) for i in range(len(L)) for j in N[i]]))

    base = [score([lab[p] for p in rng.permutation(len(lab))]) for _ in range(shuffles)]
    return {"tracks": len(idx), "k": k, "agree": score(lab), "shuffled_mean": float(np.mean(base)),
            "shuffled_p2_5": float(np.percentile(base, 2.5)), "shuffled_p97_5": float(np.percentile(base, 97.5))}


# ---- load; keep the tracks every model has --------------------------------
runs = {t: load(t) for t in TAGS}
ids = set.intersection(*({x["id"] for x in runs[t][0]} for t in TAGS))
tracks = [x for x in runs[TAGS[0]][0] if x["id"] in ids]
order = [x["id"] for x in tracks]
n = len(tracks)
R = {"tracks": n, "failed": {t: [f["reason"] for f in runs[t][3]] for t in TAGS}, "models": {}}
V, WINS = {}, {}
for t in TAGS:
    pos = {x["id"]: i for i, x in enumerate(runs[t][0])}
    WINS[t] = [runs[t][1][pos[i]] for i in order]
    V[t] = np.stack([pool(w) for w in WINS[t]])
genres = [x["genre"] for x in tracks]
R["windows_per_track"] = {"6": int(sum(len(w) == 6 for w in WINS[TAGS[0]])),
                          "fewer (short tracks)": int(sum(len(w) < 6 for w in WINS[TAGS[0]]))}

# ---- pooling: how many windows a track needs --------------------------------
# Full coverage comes from the model's own run (--full-subset) or from a
# separate run tagged <tag>full (--sample K --full-subset K).
R["pooling"] = {}
pos_all = {x["id"]: i for i, x in enumerate(tracks)}
for tag in TAGS:
    V6 = V[tag]
    V3 = np.stack([pool(w, [1, 3, 5]) for w in WINS[tag]])
    V1 = np.stack([pool(w, [3]) for w in WINS[tag]])
    N6, _ = knn(V6, 10)
    res = {"library_top10_overlap_1_vs_6": overlap(knn(V1, 10)[0], N6),
           "library_top10_overlap_3_vs_6": overlap(knn(V3, 10)[0], N6)}
    ftracks, full = runs[tag][0], runs[tag][2]
    if not full and (src / f"{tag}full.npz").exists():
        ftracks, _, full, _, _ = load(f"{tag}full")
    pairs = [(pos_all[x["id"]], x["full_index"]) for x in ftracks if "full_index" in x and x["id"] in pos_all]
    if pairs:
        rows = [i for i, _ in pairs]
        VF = np.stack([pool(full[j]) for _, j in pairs])
        res |= {"full_tracks": len(rows), "full_windows_per_track": float(np.mean([len(full[j]) for _, j in pairs]))}

        def query_nn(Q):  # neighbours of the subset tracks among all tracks (library vectors: 6 windows)
            S = Q @ V6.T
            S[np.arange(len(rows)), rows] = -np.inf
            return np.argsort(-S, axis=1)[:, :10]

        ref = query_nn(VF)
        for name, W in (("1", V1), ("3", V3), ("6", V6)):
            res[f"cosine_to_full_{name}"] = float(np.mean((W[rows] * VF).sum(1)))
            res[f"top10_overlap_with_full_{name}"] = overlap(query_nn(W[rows]), ref)
    R["pooling"][tag] = res

# ---- per model: agreement, cost, layouts ----------------------------------
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.manifold import TSNE, trustworthiness  # noqa: E402

t = time.perf_counter(); import umap  # noqa: E402
R["umap_import_s"] = round(time.perf_counter() - t, 2)
LAY = {}
for tag in TAGS:
    X = V[tag]
    Xc = unit(X - X.mean(0))       # centred: removes the direction every track shares
    m = {"cost": runs[tag][4]}
    m["genre_agreement"] = agreement(X, genres, lambda x, y: x == y)
    m["genre_agreement_centred"] = agreement(Xc, genres, lambda x, y: x == y, shuffles=300)
    m["genre_agreement_top10"] = agreement(X, genres, lambda x, y: x == y, k=10, shuffles=300)
    m["bpm_agreement"] = agreement(X, [x["bpm"] for x in tracks], bpm_ok, shuffles=300)
    m["key_agreement"] = agreement(X, [camelot(x["key"]) for x in tracks], key_ok, shuffles=300)
    idx = [i for i, g in enumerate(genres) if g]
    N5, _ = knn(X[idx], 5)
    G = [genres[i] for i in idx]
    m["per_genre"] = {}
    for g in sorted(set(G), key=lambda g: -G.count(g)):
        mm = [i for i, x in enumerate(G) if x == g]
        if len(mm) >= 20:
            m["per_genre"][g] = {"tracks": len(mm), "agree": float(np.mean([G[j] == g for i in mm for j in N5[i]])),
                                 "chance": (len(mm) - 1) / (len(G) - 1)}
    S = X @ X.T
    iu = np.triu_indices(n, 1)
    m["cosine_all_pairs"] = {"p5": float(np.percentile(S[iu], 5)), "median": float(np.median(S[iu])),
                             "p95": float(np.percentile(S[iu], 95))}
    NN, _ = knn(X, 10)
    lay, m["layouts"] = {}, {}
    for name, fit in (("PCA", lambda: PCA(2, random_state=0).fit_transform(X)),
                      ("t-SNE", lambda: TSNE(2, perplexity=30, metric="cosine", init="pca",
                                             random_state=0).fit_transform(X)),
                      ("UMAP", lambda: umap.UMAP(n_neighbors=15, min_dist=0.1, metric="cosine",
                                                 random_state=0).fit_transform(X))):
        t = time.perf_counter(); Y = fit(); s = time.perf_counter() - t
        N2 = np.argsort(((Y[:, None] - Y[None]) ** 2).sum(-1) + np.eye(n) * 1e9, axis=1)[:, :10]
        m["layouts"][name] = {"fit_s": round(s, 2), "top10_kept": overlap(N2, NN),
                              "trustworthiness_10": float(trustworthiness(X, Y, n_neighbors=10, metric="cosine"))}
        lay[name] = Y
    m["layouts"]["PCA"]["variance_explained"] = float(PCA(2).fit(X).explained_variance_ratio_.sum())
    LAY[tag] = lay
    R["models"][tag] = m
if len(TAGS) > 1:
    R["top10_overlap_between_models"] = overlap(knn(V[TAGS[0]], 10)[0], knn(V[TAGS[1]], 10)[0])
(out / "analysis.json").write_text(json.dumps(R, indent=2))
print(json.dumps(R, indent=2))

# ---- pages -------------------------------------------------------------------
MODEL_NAME = {"music": "laion/larger_clap_music", "general": "laion/clap-htsat-unfused"}
e = html.escape


def label(tag):
    return MODEL_NAME.get(tag, tag)


def cells(x):
    return (f"<td>{e(x['artist'] or '')}</td><td>{e(x['title'] or '')}</td>"
            f"<td class=n>{x['bpm'] if x['bpm'] else '-'}</td><td>{e(str(x['key'] or '-'))}</td>"
            f"<td>{e(x['genre'] or '-')}</td>")


def play(i):
    x = tracks[i]
    return (f"<button class=play title=Play data-src=\"{e(Path(x['path']).as_uri())}\" "
            f"data-name=\"{e((x['artist'] or '') + ' - ' + (x['title'] or ''))}\">&#9654;</button>")


STYLE = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--muted:#5f5e58;--line:#e1e0d9;--accent:#2a78d6}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 20px;z-index:5}
h1{font-size:18px;margin:0 0 4px}p.note{color:var(--muted);margin:2px 0;max-width:80em}
.ctl{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:6px}#now{color:var(--muted)}
select{font:inherit;padding:2px 6px}audio{height:32px;width:420px}main{padding:8px 20px 40px}
button.play{border:1px solid var(--line);background:#fff;border-radius:4px;width:30px;height:26px;cursor:pointer;color:var(--accent)}
button.play:hover{border-color:var(--accent)}button.play.on{background:var(--accent);color:#fff}
"""
PLAYER_JS = """
const player=document.getElementById('player'),now=document.getElementById('now'),mid=document.getElementById('mid');
let cur=null;
function playTrack(src,name,btn){
  if(cur)cur.classList.remove('on');cur=btn;if(btn)btn.classList.add('on');
  player.src=src;now.textContent=name;
  player.onloadedmetadata=()=>{if(mid.checked&&player.duration>40)player.currentTime=player.duration*0.3;player.play();};
  player.onerror=()=>{now.textContent='cannot play: '+name;};
}
document.addEventListener('click',ev=>{const b=ev.target.closest('button.play');if(b)playTrack(b.dataset.src,b.dataset.name,b);});
"""
PLAYER = ("<audio id=player controls preload=none></audio><label><input type=checkbox id=mid checked>"
          " start at 30%</label><span id=now>nothing playing</span>")
MODEL_SELECT = ("<label>Model <select id=model>" +
                "".join(f"<option value={t}>{e(label(t))}</option>" for t in TAGS) + "</select></label>")

seeds = sorted(range(n), key=lambda i: (-tracks[i]["plays"], tracks[i]["id"]))[:20]
blocks = []
for tag in TAGS:
    NN, S = knn(V[tag], 10)
    sec = []
    for r, i in enumerate(seeds, 1):
        x = tracks[i]
        body = "".join(f"<tr><td class=n>{k}</td><td>{play(j)}</td>{cells(tracks[j])}<td class=n>{S[i, j]:.3f}</td></tr>"
                       for k, j in enumerate(NN[i], 1))
        sec.append(f"<section><h2><span class=rank>{r}</span> {play(i)} {e(x['artist'] or '')} - {e(x['title'] or '')}"
                   f" <small>{x['bpm'] or '-'} BPM · {e(str(x['key'] or '-'))} · {e(x['genre'] or '-')} · "
                   f"played {x['plays']}x</small></h2><table><thead><tr><th>#</th><th></th><th>Artist</th><th>Title</th>"
                   f"<th>BPM</th><th>Key</th><th>Genre</th><th>Similarity</th></tr></thead><tbody>{body}</tbody></table></section>")
    cs = R["models"][tag]["cosine_all_pairs"]
    blocks.append(f"<div class=model data-tag={tag}><p class=note>{e(label(tag))}: for scale, two random tracks score "
                  f"{cs['median']:.3f} at the median and the top 5% of pairs score above {cs['p95']:.3f}.</p>{''.join(sec)}</div>")
neigh = f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>Similar tracks (spike #22)</title>
<style>{STYLE}
section{{margin:20px 0 28px}}h2{{font-size:15px;margin:0 0 6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
h2 small{{color:var(--muted);font-weight:normal}}.rank{{color:var(--muted);min-width:1.6em}}
table{{border-collapse:collapse;width:100%;max-width:1100px;table-layout:fixed}}
th:nth-child(1){{width:36px}}th:nth-child(2){{width:44px}}th:nth-child(3){{width:22%}}th:nth-child(5){{width:70px}}
th:nth-child(6){{width:50px}}th:nth-child(7){{width:14%}}th:nth-child(8){{width:80px}}td{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}td,th{{padding:3px 8px;border-bottom:1px solid var(--line);text-align:left}}
th{{font-weight:600;color:var(--muted);font-size:12px}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}
div.model{{display:none}}div.model.on{{display:block}}
</style></head><body><header><h1>Similar tracks: the 20 most-played tracks and their 10 nearest neighbours</h1>
<p class=note>CLAP audio embeddings (ONNX Runtime, CPU), mean of 6 ten-second windows per track, cosine similarity over
{n} tracks. Switch the model to compare. Click &#9654; to listen; open this file from disk so the links play.</p>
<div class=ctl>{MODEL_SELECT}{PLAYER}</div></header><main>{''.join(blocks)}</main>
<script>{PLAYER_JS}
const sel=document.getElementById('model');
function show(){{document.querySelectorAll('div.model').forEach(d=>d.classList.toggle('on',d.dataset.tag===sel.value));}}
sel.onchange=show;show();</script></body></html>"""
(out / "neighbours.html").write_text(neigh, encoding="utf-8")

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
top = [g for g, _ in sorted(((g, genres.count(g)) for g in set(genres) if g), key=lambda x: -x[1])[:8]]
pts = []
for i, x in enumerate(tracks):
    c = camelot(x["key"])
    pts.append({"a": x["artist"] or "", "t": x["title"] or "", "b": x["bpm"], "k": x["key"] or "-",
                "c": c[0] if c else None, "m": c[1] if c else None, "g": x["genre"] or "",
                "u": Path(x["path"]).as_uri(),
                "xy": {tag: {name: [round(float(v), 4) for v in Y[i]] for name, Y in LAY[tag].items()} for tag in TAGS}})
mp = f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>Library map (spike #22)</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>{STYLE}#plot{{width:100%;height:calc(100vh - 160px);min-height:480px}}</style></head><body>
<header><h1>Library map: {n} tracks laid out by CLAP audio embeddings</h1>
<p class=note>Each point is a track; tracks the model finds similar sit close together. Hover for details, click a point to
play it, drag to zoom, double-click to reset. Key colours follow the Camelot wheel (circles minor, diamonds major).
Genres beyond the 8 largest are grey.</p>
<div class=ctl>{MODEL_SELECT}<label>Layout <select id=lay><option>UMAP</option><option>t-SNE</option><option>PCA</option></select></label>
<label>Colour by <select id=col><option value=g>genre</option><option value=b>BPM</option><option value=k>key</option></select></label></div>
<div class=ctl>{PLAYER}</div></header><div id=plot></div>
<script>{PLAYER_JS}
const P={json.dumps(pts, ensure_ascii=False)};
const TOP={json.dumps(top, ensure_ascii=False)}, CAT={json.dumps(CAT)};
const BLUE=[[0,'#cde2fb'],[0.25,'#86b6ef'],[0.5,'#3987e5'],[0.75,'#1c5cab'],[1,'#0d366b']];
const CYC=[[0,'#e34948'],[0.17,'#eda100'],[0.33,'#008300'],[0.5,'#1baf7a'],[0.67,'#2a78d6'],[0.83,'#6250d6'],[1,'#e87ba4']];
const esc=s=>String(s).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[c]);
const hover=p=>`<b>${{esc(p.a)}}</b><br>${{esc(p.t)}}<br>${{p.b??'-'}} BPM · ${{esc(p.k)}} · ${{esc(p.g||'no genre')}}`;
function traces(model,lay,col){{
  const T=[], xy=p=>p.xy[model][lay];
  const mk=(pts,name,marker)=>T.push({{mode:'markers',type:'scattergl',name,hoverinfo:'text',
      hoverlabel:{{bgcolor:'#fff',font:{{color:'#0b0b0b'}}}},x:pts.map(p=>xy(p)[0]),y:pts.map(p=>xy(p)[1]),
      text:pts.map(hover),customdata:pts.map(p=>[p.u,p.a+' - '+p.t]),marker:{{size:9,line:{{width:1,color:'#fcfcfb'}},...marker}}}});
  if(col==='g'){{
    TOP.forEach((g,i)=>mk(P.filter(p=>p.g===g),g,{{color:CAT[i]}}));
    mk(P.filter(p=>p.g&&!TOP.includes(p.g)),'other genres',{{color:'#8d8c85'}});
    mk(P.filter(p=>!p.g),'no genre',{{color:'#d3d2cb'}});
  }}else if(col==='b'){{
    const has=P.filter(p=>p.b);
    mk(has,'BPM',{{color:has.map(p=>p.b),colorscale:BLUE,cmin:90,cmax:180,showscale:true,colorbar:{{title:{{text:'BPM'}},thickness:12}}}});
    mk(P.filter(p=>!p.b),'no BPM',{{color:'#d3d2cb'}});
  }}else{{
    for(const m of ['A','B']){{const s=P.filter(p=>p.m===m);
      mk(s,m==='A'?'minor (A)':'major (B)',{{color:s.map(p=>p.c),colorscale:CYC,cmin:1,cmax:12,symbol:m==='A'?'circle':'diamond',
        showscale:m==='A',colorbar:{{title:{{text:'Camelot'}},thickness:12,tickvals:[1,3,5,7,9,11]}}}});}}
  }}
  return T;
}}
const L={{margin:{{l:20,r:10,t:10,b:20}},paper_bgcolor:'#fcfcfb',plot_bgcolor:'#fcfcfb',hovermode:'closest',
  xaxis:{{showgrid:false,zeroline:false,showticklabels:false}},yaxis:{{showgrid:false,zeroline:false,showticklabels:false}},
  legend:{{orientation:'h',y:-0.02}},dragmode:'zoom'}};
const el=document.getElementById('plot'),ms=document.getElementById('model'),ls=document.getElementById('lay'),cs=document.getElementById('col');
function draw(){{Plotly.react(el,traces(ms.value,ls.value,cs.value),L,{{responsive:true,displaylogo:false}});}}
ms.onchange=ls.onchange=cs.onchange=draw;draw();
el.on('plotly_click',d=>{{const c=d.points[0].customdata;playTrack(c[0],c[1],null);}});
</script></body></html>"""
(out / "map.html").write_text(mp, encoding="utf-8")
print("pages:", out / "neighbours.html", out / "map.html")
