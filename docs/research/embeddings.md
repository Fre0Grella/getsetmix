# Spike: embeddings, similar tracks and a map

Issue: [#22](https://github.com/Fre0Grella/getsetmix/issues/22). Date: 2026-11-13.
Status: numbers in; the maintainer's verdict, by ear and by eye, is pending.
Server numbers are not measured yet.

## Question

Similar tracks, the scatter map, auto groups and the graph playlist all rest
on one thing: does an audio model's idea of "similar" match a DJ's? And what
does it cost to compute, on the CPU, with a model the product may ship?

## Method

- **Library.** A copy of one real Rekordbox library: 569 tracks (527 MP3,
  42 WAV), 35.6 hours, median length 203 s, 41 genres set by hand, 25 tracks
  without a genre. The track list, BPM, key and genre come from the copy of
  `master.db`; the audio is read from each track's file. Nothing was written
  next to the audio.
- **Models.** Two LAION CLAP audio encoders, both 512-dimensional:

  | Name here | Checkpoint | Weights license | ONNX file used | Size |
  |---|---|---|---|---|
  | general | `laion/clap-htsat-unfused` | Apache-2.0 | `Xenova/clap-htsat-unfused`, `onnx/audio_model.onnx`, revision `c28f288` | 117.5 MB |
  | music | `laion/larger_clap_music` | Apache-2.0 | exported for this spike with `export_onnx.py`, revision `a0b4534` | 276.0 MB |

  The music checkpoint was the first choice, being trained for music. The
  general one was added as the second checkpoint and turned out better on
  every check below, so it was then run over the whole library too.
  The Xenova repository's model card carries no license of its own; it is a
  format conversion of the Apache-2.0 weights. To check that the product
  needs no third-party file, the general checkpoint was also exported with
  `export_onnx.py` (116.4 MB, 4.5 s): on 55 windows of real audio its output
  matches the Xenova file to a cosine of 0.9999999, at the same speed.
- **Runtime.** ONNX Runtime 1.31.1 on the CPU. The environment that computes
  embeddings has no PyTorch and no TensorFlow; its `pip list` is below.
  PyTorch 2.15 (CPU) was used once, in a separate environment, to export
  checkpoints. Each export matches PyTorch to a cosine of 0.99999994 or
  better.
- **Decoding.** ffmpeg 7.1 (already on the computer, and already in the
  GetSetMix Docker image) decodes to 48 kHz mono float32, streamed, keeping
  only the windows needed.
- **Front end.** CLAP's log-mel features, ported to about 30 lines of numpy:
  64 Slaney mel bands from 50 Hz to 14 kHz, 1024-point FFT, hop 480, periodic
  Hann window, power spectrum, 10·log10. On the same audio it matches
  transformers' `ClapFeatureExtractor` to 0.000002 dB. The port was needed:
  in transformers 5.22 `ClapFeatureExtractor` refuses to run without PyTorch,
  although its non-fusion path is plain numpy.
- **One vector per track.** Six 10-second windows, evenly spaced between 10%
  and 90% of the track. Each window's embedding is normalised, the six are
  averaged and the mean is normalised again. Similarity is the cosine. Tracks
  shorter than about 20 s get fewer windows (28 tracks).
- **Pooling check.** For 50 random tracks per model, the whole track was also
  embedded, back to back in 10-second windows ("full coverage"), and compared
  with 1, 3 and 6 sampled windows.
- **Agreement with the hand-set labels.** For each track, its 5 nearest
  neighbours; the share that has the same genre, against the same share with
  the genres shuffled among the tracks (1,000 shuffles). The same for BPM
  (within 6%, half and double time counted) and key (same key, a neighbour on
  the Camelot wheel, or the relative major or minor).
- **Maps.** Three 2-D layouts of the same vectors: PCA, t-SNE (scikit-learn)
  and UMAP (umap-learn). Each is scored by trustworthiness (scikit-learn,
  10 neighbours) and by the share of each track's 10 nearest neighbours that
  stay its 10 nearest on the map.
- **Machine.** AMD Ryzen 7 5700U laptop, 8 cores and 16 threads, 15.3 GB RAM,
  Windows 11, ONNX Runtime's default thread count.
- **Budget.** About 45 minutes of compute in all, so the sampled windows
  were measured on the whole library and full coverage on 50-track subsets.

The scripts are in [`spikes/embeddings/`](../../spikes/embeddings/). They
write their output outside the repository.

## Results

### Cost on the computer

Seconds per track, whole library, six windows:

| Step | general | music |
|---|---|---|
| Decode (ffmpeg) | 0.39 | 0.43 |
| Features (numpy) | 0.10 | 0.08 |
| Inference (ONNX Runtime) | 0.54 | 0.89 |
| **Total** | **1.03** | **1.40** |
| Whole library, 568 tracks | 9.8 min | 16.9 min |

| Measure | general | music |
|---|---|---|
| Model file | 117.5 MB | 276.0 MB |
| Model load | 3.3 s | 2.5 s |
| Memory after load | 268 MB | 419 MB |
| Peak memory, whole run | 500 MB | 759 to 803 MB |
| Inference per 10 s window | 0.09 s | 0.15 s |
| Full coverage instead of 6 windows | 2.3 s/track | 4.3 s/track |

- The first whole-library run decoded each file into memory at once. One
  2.4-hour mix then took 3.8 GB. Streaming the decode and keeping only the
  windows fixed it; the peak figures above are with the fix, the 2.4-hour
  track included.
- Decoding each window with its own ffmpeg seek was slower than one
  streamed decode: 0.95 s against 0.46 s per track (4 tracks).
- Threads, music model, 21 tracks: the default (8) and 4 threads both gave
  1.0 s of inference per track; 2 threads gave 1.5 s.
- At 1 s per track, a library of 5,000 tracks takes about 1.5 hours on this
  laptop, once. New tracks then cost a second each.

### Cost on the server

**Not measured.** `bench.py` is self-contained for that: it needs ffmpeg,
Python and three packages, takes a fixed random pick of 20 tracks, opens the
audio read-only and prints the same split as above. With Docker, on the
server, from a folder holding `bench.py`:

```sh
docker run --rm -v /path/to/music:/music:ro -v "$PWD":/work -w /work python:3.12-slim sh -c '
  apt-get update -qq && apt-get install -y -qq --no-install-recommends ffmpeg >/dev/null &&
  pip install -q onnxruntime numpy psutil &&
  python bench.py /work/bench-general /music --tracks 20 \
    --model /work/clap-htsat-unfused.onnx'
```

Download the general model first with
`curl -L -o clap-htsat-unfused.onnx https://huggingface.co/Xenova/clap-htsat-unfused/resolve/c28f2883575e590e04d3146ff0713c2448d691ba/onnx/audio_model.onnx`.
Without `--model`, `bench.py` downloads `Xenova/larger_clap_music_and_speech`,
which has the music model's architecture and size, so its cost stands for
the music model. Add `--threads 2` to see a busier server. The result is in
`bench-general/bench.json`; it holds no track names.

### How many windows a track needs

Top-10 neighbours of 50 tracks, queried with a sampled vector, against the
same query with the full-coverage vector (about 20 windows per track):

| Windows per track | general: same neighbours | general: cosine to full | music: same neighbours | music: cosine to full |
|---|---|---|---|---|
| 1 | 45% | 0.923 | 25% | 0.940 |
| 3 | 68% | 0.978 | 49% | 0.981 |
| 6 | 80% | 0.991 | 68% | 0.991 |

Six windows keep most of the full-coverage neighbours for less than half of
its cost. A single window does not: the neighbours of a track then depend on
which 10 seconds were taken. Six windows is the choice here.

### Agreement with the hand-set labels

Share of each track's 5 nearest neighbours that agree, whole library:

| Label | general | music | Shuffled labels (95% range) |
|---|---|---|---|
| Same genre (544 tracks with a genre) | **29.5%** | 12.3% | 6.2% (5.2 to 7.3%) |
| Same genre, 10 neighbours | 26.8% | 10.9% | 6.2% (5.5 to 7.1%) |
| BPM within 6% | **43.5%** | 27.7% | 23.1% (21.4 to 25.1%) |
| Compatible key | 19.3% | 30.6% | 21.1% (19.6 to 23.0%) |

Per genre, general model, genres with at least 20 tracks:

| Genre | Tracks | Same genre in top 5 | By chance |
|---|---|---|---|
| House | 94 | 39.8% | 17.1% |
| Reggaeton | 45 | 76.4% | 8.1% |
| Hard Techno | 45 | 30.2% | 8.1% |
| Dance - Techno | 33 | 29.7% | 5.9% |
| Dance | 32 | 21.2% | 5.7% |
| Techno | 26 | 12.3% | 4.6% |
| Pop | 23 | 11.3% | 4.1% |
| Hardstyle | 20 | 44.0% | 3.5% |

- The general model's neighbours share the hand-set genre almost five times
  as often as chance, and a similar tempo almost twice as often. It knows
  nothing of key, which is expected: key is not what CLAP was trained on,
  and Rekordbox already has it.
- The music model is weaker on genre and tempo, and better than chance on
  key. The two models rarely agree: 7.8% of their top-10 neighbours are the
  same.
- The music model's cosines are crowded: two random tracks score 0.945 at the
  median, against 0.797 for the general model. Its neighbours differ by
  hundredths. Centring the vectors on the library's mean helps both models
  a little (genre 30.7% and 13.6%).
- The genres are one DJ's labels, partly overlapping ("Techno", "Hard
  Techno", "Dance - Techno") and partly not about sound at all. A genre
  match is evidence that the neighbours are not random. It is not a measure
  of whether they are useful in a mix; only listening tells that.

### Maps

| Layout | general: fit | general: trustworthiness | general: neighbours kept | music: trustworthiness | music: neighbours kept |
|---|---|---|---|---|---|
| PCA | 0.01 s | 0.763 | 14% | 0.876 | 22% |
| t-SNE (scikit-learn) | 1.0 s | 0.932 | 45% | 0.932 | 41% |
| UMAP (umap-learn) | 0.6 s | 0.915 | 40% | 0.914 | 34% |

- UMAP's first call in a process took about 10 s more, compiling with numba,
  and its first import 43 s; later imports took 2 s.
- t-SNE from scikit-learn is as good as UMAP here, and better than PCA, at
  one second for 568 tracks. It grows roughly as n·log n; a few thousand
  tracks should take seconds (not measured).
- On the general model's map, Reggaeton, the hard styles and House form
  visible regions.

## What a product would need

| Need | Answer from the spike |
|---|---|
| Model download | 117.5 MB (general) or 276 MB (music), once. Quantised or fp16 exports would be smaller; not measured. |
| Runtime | ONNX Runtime (43 MB installed) and numpy (27 MB), plus ffmpeg, which the app already uses. No PyTorch. |
| Front end | The numpy port in `bench.py`, about 30 lines. Its output must stay identical to the model's training front end. |
| Time | About 1 s per track on this laptop; a library is a one-off job, new tracks are cheap. Server: not measured. |
| Memory | 0.5 GB peak with the general model. |
| Storage | 512 float32 per track: 2 KB. 5,000 tracks are 10 MB, in SQLite next to the track, keyed by the audio hash and the model version. |
| Search | Brute-force cosine over a few thousand vectors with numpy is far below a millisecond per query. No vector database or ANN index is needed at this size. |
| Map layout | t-SNE from scikit-learn (with scipy, about 135 MB installed), or PCA from numpy alone if a coarser map is enough. UMAP would bring numba and llvmlite (about 140 MB) for no gain here. |
| Model file | The product should publish its own ONNX export of the Apache-2.0 checkpoint (made with `export_onnx.py`, shown identical above) rather than depend on a third-party mirror without a license of its own. |

## Licenses

| Component | License | Role |
|---|---|---|
| `laion/clap-htsat-unfused`, `laion/larger_clap_music` weights | Apache-2.0 (model cards) | would ship (download) |
| LAION-CLAP original code | CC0-1.0 | reference only |
| `Xenova/clap-htsat-unfused` ONNX file | none stated; conversion of Apache-2.0 weights | spike only |
| ONNX Runtime | MIT | would ship |
| numpy | BSD-3-Clause | would ship |
| scikit-learn, scipy | BSD-3-Clause | would ship, for the map |
| umap-learn, pynndescent | BSD-3-Clause | spike only |
| numba, llvmlite | BSD-2-Clause | spike only |
| ffmpeg | LGPL-2.1 or GPL, by build | already in the app |
| Plotly.js (loaded by the map page) | MIT | spike only |
| PyTorch, transformers, pyrekordbox | BSD-3-Clause, Apache-2.0, MIT | spike only, never at run time |

The data CLAP was trained on was not reviewed; the weights' license is the
one the model cards state. `docs/research/licenses.md`
([#18](https://github.com/Fre0Grella/getsetmix/issues/18)) holds the
project-wide matrix.

The embedding environment, `pip list` (no torch, no tensorflow;
transformers is there only to check the claim above, and is never imported
by the pipeline):

```
annotated-doc 0.0.6, annotated-types 0.8.0, anyio 4.16.0, bidict 0.24.1,
click 8.5.1, cloudpickle 3.1.2, colorama 0.4.6, construct 2.10.70,
filelock 4.2.10, flatbuffers 25.12.19, fsspec 2026.9.0, h11 0.16.0,
hf-xet 1.8.0, httpcore2 2.16.0, httpx2 2.16.0, huggingface_hub 2.4.0,
idna 3.20, joblib 1.6.0, llvmlite 0.50.0, markdown-it-py 4.3.0, mdurl 0.1.2,
narwhals 2.28.0, numba 0.68.1, numpy 2.4.6, onnxruntime 1.31.1,
packaging 26.3, pip 26.3, protobuf 7.36.2, psutil 7.2.2, pydantic 2.14.3,
pydantic_core 2.50.4, Pygments 2.21.0, pynndescent 0.7.0,
pyrekordbox 0.5.0, python-dateutil 4.0.0, PyYAML 6.0.3, regex 2026.11.9,
rich 15.0.0, safetensors 0.8.0, scikit-learn 1.9.1, scipy 1.17.1,
shellingham 1.5.4, SQLAlchemy 2.1.8, sqlcipher3-wheels 0.5.7,
threadpoolctl 3.8.0, tokenizers 0.23.3, tqdm 4.70.1, transformers 5.22.2,
truststore 0.10.5, typer 0.29.1, typing_extensions 4.16.0,
typing-inspection 0.4.5, tzdata 2026.6, umap-learn 0.6.0
```

## Limits

- One library, one DJ's genres, 568 tracks. The genre numbers carry the
  noise of a small sample and of labels that overlap.
- Two checkpoints only. The music model was judged on the same checks as
  the general one; a different pooling or centring could narrow the gap.
- Cost was measured on one laptop with Windows; not on the server, not on
  macOS.
- Six windows are a sample. A track whose character changes sharply may
  land in the wrong place.
- The map page loads Plotly.js from a CDN; offline it shows nothing.
- One track's audio file was missing, so 568 of 569 tracks have embeddings.

## Verdict

| Feature | Verdict | Why |
|---|---|---|
| Computing embeddings in the product | **Feasible** | ONNX Runtime on the CPU, about 1 s per track, 0.5 GB, a 118 MB model under Apache-2.0, no PyTorch |
| Similar tracks | **Pending the maintainer's judgement** | open `neighbours.html` (see below) |
| Map and graph features | **Pending the maintainer's judgement** | open `map.html` (see below) |

Both pages were generated by `analyse.py` into the spike's private output
folder, outside the repository, because they list track names and link to
the audio files:

- **`neighbours.html`**: the 20 most-played tracks, each with its 10 nearest
  neighbours, BPM, key, genre and similarity, and a play button (it starts
  at 30% of the track). A switch shows either model.
- **`map.html`**: every track as a point; hover for details, click to play,
  colour by genre, BPM or key, and a choice of layout and model.

Open them from disk in Chrome or Edge, where playback was tested. The
evidence above points to the general model. The verdict goes here once
given: are the neighbours tracks you would play next to each other, and does
the map put things where you would?
