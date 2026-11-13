# Spike: what a Rekordbox library already holds

Issue: [#21](https://github.com/Fre0Grella/getsetmix/issues/21). Date: 2026-11-13.
Status: done. Numbers and verdicts are in.

## Question

How much of the analysis GetSetMix needs (BPM, key, beat grid, phrases) is
already in a Rekordbox library, so that it never has to be computed again?
And are Rekordbox's phrases good enough to place cue points from?

## Method

- A **copy** of one real Rekordbox library: `master.db` (11 MB) and the
  `share/` folder of analysis files (184 MB). Rekordbox was closed when the
  copy was made. Nothing was written, and the live library was never opened.
- Read with [pyrekordbox](https://github.com/dylanljones/pyrekordbox) 0.5.0
  in a throwaway environment. The scripts are in
  [`spikes/rekordbox-read/`](../../spikes/rekordbox-read/); they refuse to
  run on a path inside Rekordbox's own folder.
- Per track: the `djmdContent` row, its cues in `djmdCue`, and the three
  analysis files (`.DAT`, `.EXT`, `.2EX`) that `AnalysisDataPath` points at.

## Results

### Coverage

569 tracks in the collection.

| Data | Where it lives | Tracks | Share |
|---|---|---|---|
| Key | `djmdContent.KeyID` → `djmdKey.ScaleName` | 569 | 100% |
| BPM | `djmdContent.BPM` (value × 100) | 544 | 96% |
| Beat grid | `PQTZ` tag in the `.DAT` file | 544 | 96% |
| Phrases | `PSSI` tag in the `.EXT` file | 407 | 72% |
| Vocal detection | `PVDI` tag in the `.2EX` file | 60 | 11% |

- The 25 tracks without a BPM have no beat grid either: they were never
  analysed.
- 480 of the 544 grids (88%) hold one constant tempo.
- Every analysis file parsed without an error.
- BPM ranges from 78 to 208, median 137.5.

### Phrases

407 tracks have phrases, 6,234 phrases in all. Rekordbox sorted the tracks
into three moods, which decide the phrase names: high (315 tracks: Intro, Up,
Down, Chorus, Outro), mid (84) and low (8: Intro, Verse, Bridge, Chorus,
Outro).

| Measure | Phrases | Share |
|---|---|---|
| Starts on a downbeat | 6,010 | 96% |
| Length is a multiple of 4 bars | 4,374 | 70% |
| Length is a multiple of 8 bars | 3,095 | 50% |

Half of the phrases have a length that is not a multiple of 8 bars. In dance
music, where sections usually run 8, 16 or 32 bars, that points to
boundaries that are often a few bars off.

### Cues

| Measure | Value |
|---|---|
| Cues in `master.db` (`djmdCue`) | 3,484 |
| Tracks with at least one hot cue | 423 |
| Tracks with at least one memory cue | 335 |
| Tracks whose local analysis files hold a cue (`PCOB`, `PCO2`) | 0 |

The cue tags exist in every local analysis file and are all empty. On the
computer, cues live only in `master.db`. That settles one question for the
cue spike ([#23](https://github.com/Fre0Grella/getsetmix/issues/23)):
writing a cue means writing `djmdCue` rows, and the analysis files are
Rekordbox's business at export time.

### The library's cues against the phrases

Of the 3,241 cues on tracks with phrases:

| Where the cue sits | Cues | Share |
|---|---|---|
| Exactly on a phrase start | 2,008 | 62% |
| Within one bar of a phrase start | 2,829 | 87% |
| On a plain 8-bar grid from the first downbeat | 1,341 | 41% |
| On a plain 16-bar grid | 956 | 29% |

The 8-bar grid produces about as many boundaries as the phrases do (6,965
against 6,641), so the comparison is fair: the phrases match the cues
clearly better than counting bars would.

This does not show that the phrases are right, because the cues are not all
hand-made. 1,016 cues, nearly all memory cues, carry a phrase name as their
comment ("Chorus", "Up", "Outro", "Intro", "Down", "Verse", "Bridge"), and
982 cues were created on a single day. The maintainer confirmed where they
came from: a third-party cue generator that works from Rekordbox's phrase
analysis. Of the cues named after a phrase, only 64% sit on a
phrase start today, so the phrases have changed since, or the generator
offsets its cues. Hand-made and generated cues cannot be told apart
reliably from the data.

### Cost

One run over the 569 tracks took 53 s on a laptop, with a Python parser that
reads every tag, waveforms included. A reader that takes only the beat grid
and the phrases has far less to do; that was not measured.

## How the companion would read this

- **BPM and key** are two columns and one join in `master.db`, which the
  companion already opens.
- **Beat grid and phrases** are in the analysis files at
  `<rekordbox folder>/share` + `AnalysisDataPath`. The format is a sequence
  of tagged blocks with fixed-size entries, documented by pyrekordbox and
  the Deep Symmetry project. The companion needs a small reader of its own
  for two tags (`PQTZ`, `PSSI`); no library is required.
- **Reaching the app.** The Python app cannot open `master.db`, so the
  companion would send what it reads to the app over HTTP, keyed by the
  track's audio hash. The same call serves a home server and the app in
  local mode. It is a new flow from the computer to the app, of metadata
  only; files still travel one way.

## Licenses

pyrekordbox is used in the spike only. Its license and the others are in
`docs/research/licenses.md`
([#18](https://github.com/Fre0Grella/getsetmix/issues/18)). The product
would read these files with its own code.

## Verdict

| Feature | Verdict | Why |
|---|---|---|
| BPM and key from Rekordbox; match and sort by them | **Continue** | 96 to 100% of tracks covered, exact, nothing to compute |
| Beat grid from Rekordbox | **Continue** | same coverage as BPM; needed for anything placed on a beat |
| Cue points from Rekordbox's phrases | **Stop** | see below |

Against cue points from these phrases:

- It exists already. The library holds about a thousand memory cues placed
  by a third-party generator from this same phrase analysis.
- The maintainer's experience with those cues: not awful, but they often do
  more harm than good. The maintainer puts the weakness in Rekordbox's
  phrase analysis, so a second generator on the same phrases would inherit
  it.
- Phrases cover 72% of the tracks.
- Half of the phrase lengths are not multiples of 8 bars.

For them: where phrases exist they agree with the existing cues far better
than a fixed bar grid, but that agreement is partly circular, since many of
those cues were generated from the phrases.

So cue points are only worth building on a better source of phrase
boundaries than Rekordbox's. Whether to look for one (a structure model run
on the audio) is a question for the synthesis
([#24](https://github.com/Fre0Grella/getsetmix/issues/24)); the cue-write
spike ([#23](https://github.com/Fre0Grella/getsetmix/issues/23)) does not
start on Rekordbox's phrases.

### Ten tracks with cues the maintainer vouches for

The 10 most-played tracks carry cues the maintainer set and checked by
hand, so they serve as a reference. `top10.py` compares them with
Rekordbox's phrase starts on the same tracks.

| Measure | Count | Share |
|---|---|---|
| Good cue positions | 81 | |
| ...that sit on a phrase start | 52 | 64% |
| ...that miss by up to one bar | 15 | 19% |
| ...that miss by 2 to 4 bars | 7 | 9% |
| ...that miss by more than 4 bars | 7 | 9% |
| Phrase starts | 121 | |
| ...where the DJ put no cue | 69 | 57% |

- A generator that put a cue on every phrase start would place more than
  half of its cues where the DJ wants none, and would miss a third of the
  places the DJ does want one.
- Results vary a lot per track: on two tracks every cue sits on a phrase
  start; on one track none does, with most cues exactly one beat away from
  a phrase start, which means the phrases are shifted against the music
  there.

This confirms the stop: Rekordbox's phrases are a useful hint, not a
reliable source of cue positions.
