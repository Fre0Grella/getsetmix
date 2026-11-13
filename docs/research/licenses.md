# Licenses of the tools in play

Checked on 2026-11-13. This closes issue #18. It is an engineering check, not legal advice.

GetSetMix is licensed AGPL-3.0-only, and a paid hosted offering is planned next to free self-hosting. That makes the project commercial for licensing. Only components whose licenses allow commercial use may ship in the product: the Docker image, the PyInstaller executables, and the Setup and companion builds. A non-commercial model may run in a throwaway research spike as a yardstick. It must never ship.

Analysis features have to run in the packaged Windows and macOS builds as well as the Docker image. The plan is a small CPU runtime (ONNX Runtime), not PyTorch or TensorFlow.

Each license below was read from the source in the last column: the LICENSE file in the repository, the package metadata, or the model card. Where a source could not be read, the row says "not verified" and why.

## Verdicts

- **ship**: license allows commercial use and may sit inside an AGPL-3.0-only product.
- **spikes only**: fine to run in research, not to bundle.
- **don't use**: do not use, not even in spikes, without a change.

## Table

| Tool | What it is used for | Code license | Model weights license | Bundle in image / executables / Setup? | Verdict | Source |
|---|---|---|---|---|---|---|
| mutagen | Reads and writes audio tags (Python) | GPL-2.0-or-later (README states "or later"; COPYING is GPL v2 text) | none | Image: yes. Executables: yes. See finding 1. | **ship** | https://github.com/quodlibet/mutagen/blob/main/README.rst , https://github.com/quodlibet/mutagen/blob/main/COPYING |
| yt-dlp | Downloads media | Unlicense (public domain) | none | Image: yes (pip). Executables: yes. | **ship** | https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE |
| yt-dlp-ejs | JavaScript challenge solvers for yt-dlp | Unlicense | none | Image: yes (pip, via `yt-dlp[default]`). Executables: yes. | **ship** | https://github.com/yt-dlp/ejs/blob/main/LICENSE |
| ffmpeg, Debian build in `python:3.12-slim` (`apt-get install ffmpeg`) | Audio conversion and probing, run as a separate process | Debian's copyright file: most files LGPL-2.1+, but the default binary packages use GPL-licensed files, so "the resulting binaries are licensed under GPL v2+". An extra flavor linked to Apache-2.0 libraries is GPL v3+. **Not verified from a running image**: Docker was installed but its engine was not running on 2026-11-13, so `ffmpeg -version` and `ffmpeg -L` were not run. Which Debian release the tag resolves to was not checked. | none | Image: yes, as a separate program. Not in executables. | **ship** | https://metadata.ftp-master.debian.org/changelogs/main/f/ffmpeg/stable_copyright |
| ffmpeg, Windows build fetched by Setup (Gyan "essentials", release 9.0.2) | Same, for the Windows app | "All builds are 64-bit, static and licensed as GPLv3" | none | Setup downloads it at install time from the Gyan release page; it is not inside our binaries. See finding 2. | **ship** | https://www.gyan.dev/ffmpeg/builds/ , URL in `companion/internal/setup/download.go` |
| ffmpeg, macOS build fetched by Setup (martin-riedl.de, 9.0.2) | Same, for the macOS app | GPL-3.0-or-later, read from the pinned build's own `versions.txt` (build 1789931890_9.0.2, arm64): configure flags include `--enable-version3 --enable-gpl --enable-libx264 --enable-libx265`, and do not include `--enable-nonfree`, `--enable-decklink` or `--enable-libfdk-aac`. `codecs.txt` of the same build lists no decklink or fdk codec. The site itself states no license; the license follows from the flags. | none | Setup downloads it at install time; it is not inside our binaries. See finding 2. | **ship** | https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/versions.txt , https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/codecs.txt , https://ffmpeg.martin-riedl.de/ , https://git.martin-riedl.de/ffmpeg/build-script/raw/branch/main/build.sh |
| Deno | JavaScript runtime for yt-dlp's challenge solver | MIT | none | Image: yes (copied from `denoland/deno:bin-2.9.3`). Setup: downloaded from the Deno release page. | **ship** | https://github.com/denoland/deno/blob/main/LICENSE.md |
| FastAPI | Web framework | MIT | none | Image: yes. Executables: yes. | **ship** | https://github.com/fastapi/fastapi/blob/master/LICENSE |
| uvicorn | ASGI server | BSD-3-Clause | none | Image: yes. Executables: yes. | **ship** | https://github.com/Kludex/uvicorn/blob/main/LICENSE.md |
| python-multipart | Form and upload parsing | Apache-2.0 | none | Image: yes. Executables: yes. | **ship** | https://github.com/Kludex/python-multipart/blob/main/LICENSE.txt |
| go-sqlcipher (mutecomm) | Encrypted SQLite for the Go companion | Mixed file: MIT (code from go-sqlite3), BSD-style 3-clause (ZETETIC, the SQLCipher code), and the SQLite public-domain blessing. GitHub reports it as "no assertion" because the file holds several licenses. | none | Setup and companion: yes (compiled in). | **ship** | https://github.com/mutecomm/go-sqlcipher/blob/master/LICENSE |
| SQLCipher (compiled into go-sqlcipher) | Database encryption | BSD-3-Clause (SQLCipher Community Edition) | none | Setup and companion: yes (compiled in). | **ship** | https://github.com/sqlcipher/sqlcipher/blob/master/LICENSE.md |
| dhowden/tag | Reads audio tags in Go | BSD-2-Clause | none | Setup and companion: yes. | **ship** | https://github.com/dhowden/tag/blob/master/LICENSE |
| fsnotify | File watching in Go | BSD-3-Clause | none | Setup and companion: yes. | **ship** | https://github.com/fsnotify/fsnotify/blob/main/LICENSE |
| golang.org/x/sys | Go OS calls | BSD-3-Clause | none | Setup and companion: yes. | **ship** | https://github.com/golang/sys/blob/master/LICENSE |
| golang.org/x/text | Go text handling | BSD-3-Clause | none | Setup and companion: yes. | **ship** | https://github.com/golang/text/blob/master/LICENSE |
| rsc.io/qr | QR codes for pairing | BSD-3-Clause | none | Setup and companion: yes. | **ship** | https://github.com/rsc/qr/blob/master/LICENSE |
| pyrekordbox | Reads and writes Rekordbox data (spikes) | MIT | none | Yes if adopted. | **ship** | https://github.com/dylanljones/pyrekordbox/blob/master/LICENSE |
| LAION CLAP, code | Audio-text embeddings (spikes) | CC0-1.0 (LICENSE file is the CC0 text) | see rows below | Code: yes. | **ship** | https://github.com/LAION-AI/CLAP/blob/main/LICENSE |
| CLAP checkpoints `laion/clap-htsat-unfused`, `laion/clap-htsat-fused`, `laion/larger_clap_music`, `laion/larger_clap_general`, `laion/larger_clap_music_and_speech` (Hugging Face Transformers format) | Embeddings | n/a | Apache-2.0 on each model card | Yes, with the Apache-2.0 notice. | **ship**, after the ONNX export check in finding 5 | https://huggingface.co/laion/clap-htsat-unfused , https://huggingface.co/laion/clap-htsat-fused , https://huggingface.co/laion/larger_clap_music , https://huggingface.co/laion/larger_clap_general , https://huggingface.co/laion/larger_clap_music_and_speech |
| CLAP checkpoints in `lukewys/laion_clap` (`630k-audioset-best.pt`, `630k-audioset-fusion-best.pt`, `630k-best.pt`, `630k-fusion-best.pt`, `music_audioset_epoch_15_esc_90.14.pt`, `music_speech_audioset_epoch_15_esc_89.98.pt`, `music_speech_epoch_15_esc_89.25.pt`) | Embeddings | n/a | CC0-1.0 on the repo card. The CLAP README points to this repo for the checkpoints and states no license of its own. | Yes. | **ship**, after finding 5 | https://huggingface.co/lukewys/laion_clap , https://github.com/LAION-AI/CLAP/blob/main/README.md |
| ONNX Runtime | Small CPU inference runtime | MIT (third-party notices in ThirdPartyNotices.txt) | none | Yes, all three. | **ship** | https://github.com/microsoft/onnxruntime/blob/main/LICENSE , https://pypi.org/project/onnxruntime/ |
| umap-learn | Dimensionality reduction (spikes) | BSD-3-Clause | none | Not needed for shipping, see finding 6. | **spikes only** | https://github.com/lmcinnes/umap/blob/master/LICENSE.txt |
| numba (umap dependency) | JIT compiler | BSD-2-Clause | none | Permissive, but heavy in a packaged build. | **spikes only** | https://api.github.com/repos/numba/numba/license |
| llvmlite (numba dependency) | LLVM bindings | BSD-2-Clause (PyPI: BSD-2-Clause AND Apache-2.0 WITH LLVM-exception) | none | Permissive, but heavy in a packaged build. | **spikes only** | https://pypi.org/project/llvmlite/ |
| Beat This! | Beat and downbeat tracking | MIT | MIT: "The code and the published model weights are released under the MIT license." The README warns that some training files carry limited licenses. | Yes. | **ship**, after the ONNX export check in finding 5 | https://github.com/CPJKU/beat_this/blob/main/README.md , https://github.com/CPJKU/beat_this/blob/main/LICENSE |
| all-in-one (allin1) | Beats, downbeats and song structure | MIT | MIT on `taejunkim/allinone` model card. Trained on the Harmonix Set. The Harmonix repository is MIT and its annotations are free to use, but the terms for its audio data are in a license inside a Dropbox archive that was not read, so they are not verified. | No. It needs PyTorch and Demucs, imports madmom, and its training-data terms are unclear. See finding 4. | **don't use** | https://github.com/mir-aidj/all-in-one/blob/main/LICENSE , https://huggingface.co/taejunkim/allinone , https://github.com/mir-aidj/all-in-one/blob/main/pyproject.toml , https://github.com/urinieto/harmonixset/blob/master/LICENSE , https://github.com/urinieto/harmonixset/blob/master/README.md |
| madmom (all-in-one dependency) | Downbeat HMM post-processing | BSD-style (2-clause source license) | CC BY-NC-SA 4.0 for "all model and data files". Commercial use needs the authors' permission. | No. The PyPI release (0.16.1, the latest) bundles the model files. See finding 4. | **don't use** | https://github.com/CPJKU/madmom/blob/main/README.rst , https://github.com/CPJKU/madmom/blob/main/LICENSE , https://pypi.org/pypi/madmom/json |
| Essentia library and MTG models | Audio descriptors and tag models | Library: AGPL-3.0 (compatible with this project) | CC BY-NC-SA 4.0: "All the models created by the MTG are licensed under CC BY-NC-SA 4.0" | No. The models are non-commercial. | **don't use** | https://github.com/MTG/essentia/blob/master/COPYING.txt , https://github.com/MTG/essentia/blob/master/README.md , https://essentia.upf.edu/models.html |
| MERT-v1-95M and MERT-v1-330M | Music embeddings | Repository (yizhilll/MERT): Apache-2.0 | CC BY-NC 4.0 on both model cards | No. The weights are non-commercial. | **spikes only** | https://huggingface.co/m-a-p/MERT-v1-95M , https://huggingface.co/m-a-p/MERT-v1-330M , https://github.com/yizhilll/MERT |

Notes on sources. The GitHub links above were read through the GitHub license API and the raw LICENSE or README file. The Hugging Face license fields were read from the model metadata. The MERT-v1-330M card was read through the Hugging Face model API; the 95M card was also read as a page.

## Findings

### 1. mutagen is GPL-2.0-or-later and sits in AGPL-3.0-only executables

This is not a conflict, but it has a condition. The README says "GPL-2.0-or-later". GNU's license list says GPLv2 alone is not compatible with GPLv3, but most GPLv2 software that allows later versions can be used under GPLv3 terms to make the combination. So the combined executable is distributed under AGPL-3.0, and the mutagen part stays available under its own license. Keep mutagen's license text and copyright notices in the executables, and offer the source for the whole bundle (we do, because the project is AGPL). If mutagen ever changed to GPL-2.0-only, the combination would be blocked. The only replacement then would be another tag library. In Go, dhowden/tag is BSD-2-Clause.

Sources: https://github.com/quodlibet/mutagen/blob/main/README.rst , https://www.gnu.org/licenses/license-list.en.html

### 2. ffmpeg is GPL, so distribution carries a source offer

The Debian ffmpeg in the image is GPL v2+ by Debian's own copyright file, and the Windows build Setup downloads is GPLv3. This does not conflict with AGPL-3.0-only, because ffmpeg runs as a separate process. It means that wherever we hand out the binary we must offer its source.

- Image: it is Debian's package, and Debian publishes the source. State this in the README's notices and point at the Debian source package.
- Setup: it downloads the build from the vendor's page at install time and does not store it in our release. Link the vendor's source or build script in the notices.
- macOS: the download is from martin-riedl.de. The page states no license. Its build script adds `--enable-nonfree` only when the decklink SDK is switched on (`SKIP_DECKLINK` defaults to "YES"). The pinned build's own `versions.txt` shows the configure line used: it has `--enable-version3 --enable-gpl --enable-libx264 --enable-libx265` and no `--enable-nonfree`, decklink or fdk-aac. So the build is GPL-3.0-or-later and has no non-free part. Source: the FFmpeg 9.0.2 tarball (https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz) plus the vendor's open build script, which fetches the bundled libraries. The vendor does not state this license itself; it is derived from the flags.
- Way around, if we want to drop the GPL: only use an LGPL build of ffmpeg, and only the features we need (decoding and probing).

Sources: https://metadata.ftp-master.debian.org/changelogs/main/f/ffmpeg/stable_copyright , https://www.gyan.dev/ffmpeg/builds/ , https://git.martin-riedl.de/ffmpeg/build-script/raw/branch/main/build.sh

### 3. The Essentia models and MERT weights are non-commercial

The MTG models are CC BY-NC-SA 4.0 and the MERT weights are CC BY-NC 4.0. Neither may ship in a product with a paid hosted offering. The ShareAlike term would also bind anything derived from the models.

- Use them only in a throwaway spike, as a yardstick.
- Replacement: CLAP checkpoints (Apache-2.0 or CC0) for embeddings and Beat This! (MIT) for beats.
- Way around: the Essentia page says the models are "also available under proprietary license upon request". That is an option if we ever need them. It is not part of this plan.

Sources: https://essentia.upf.edu/models.html , https://huggingface.co/m-a-p/MERT-v1-95M

### 4. all-in-one pulls in madmom and PyTorch

The all-in-one code and weights are MIT, which is fine. Two things stop it from shipping as is.

- madmom: its source is BSD-style, but its model and data files are CC BY-NC-SA 4.0. all-in-one only imports `DBNDownBeatTrackingProcessor` (an HMM post-processor) in `postprocessing/metrical.py`. If the model files are left out, madmom's code alone is permissive. The PyPI release does bundle them. The madmom 0.16.1 sdist (the latest release, uploaded 2018-11-14) holds 69 `.pkl` model files under `madmom/models/` (beats, chords, chroma, downbeats, key, notes, onsets, patterns). Its `setup.py` lists them as `package_data` "to be included in the PyPI package", its `license` field says "BSD, CC BY-NC-SA", and `madmom/models/LICENSE` is the CC BY-NC-SA 4.0 text. So a plain `pip install madmom` puts non-commercial files into the product. madmom is therefore "don't use". Avoid it, and write the downbeat post-processing ourselves or use Beat This!, which has no such dependency.
- Harmonix Set: all-in-one is trained on it. The repository `urinieto/harmonixset` is MIT (Copyright (c) 2019 Oriol Nieto), which covers the annotations. Its README says of the audio-derived spectrograms: "Users must agree to the License included before using these data." That license is inside a ~1.2 GB Dropbox archive, which was not downloaded, so its terms are not verified. Because this stays unclear, all-in-one is also "don't use".
- PyTorch and Demucs: all-in-one needs both. That breaks the "small CPU runtime" rule. Treat it as a spike yardstick. For beats, use Beat This! exported to ONNX.

Sources: https://github.com/CPJKU/madmom/blob/main/README.rst , https://github.com/mir-aidj/all-in-one/blob/main/src/allin1/postprocessing/metrical.py , https://github.com/mir-aidj/all-in-one/blob/main/pyproject.toml

### 5. CLAP and Beat This! are licensed for shipping, but not yet as ONNX

Both are permissive. No ONNX export of either was checked. An export is derived from the same weights, so treat it as carrying the same license, and record that license next to every exported file. CLAP also has two license stories: the code repository is CC0, the Transformers-format checkpoints say Apache-2.0, and the original checkpoints in `lukewys/laion_clap` say CC0. Both allow commercial use. Use the license of the checkpoint we actually export from, and ship its notice. The CLAP README does not state a license for the checkpoints. Beat This! warns that some of its training data has limited licenses, and that it is up to the user to judge the impact.

Sources: https://huggingface.co/laion/larger_clap_music , https://huggingface.co/lukewys/laion_clap , https://github.com/CPJKU/beat_this/blob/main/README.md

### 6. umap-learn drags in numba and llvmlite

All of umap-learn, numba and llvmlite are permissive, so there is no license conflict. The cost is in the packaging: umap needs numba, and numba needs llvmlite, which carries an LLVM runtime. That fits badly with the "small CPU runtime" goal for the PyInstaller builds. Keep umap in spikes. For the product, pick another way to do the 2D projection once we know what the feature needs.

Sources: https://github.com/lmcinnes/umap/blob/master/LICENSE.txt , https://pypi.org/project/llvmlite/

## Corrections

Roadmap issue #12 said the MTG/Essentia models were CC BY-NC-ND. That was wrong. They are CC BY-NC-SA 4.0. The Essentia models page says: "All the models created by the MTG are licensed under CC BY-NC-SA 4.0". Source: https://essentia.upf.edu/models.html (read 2026-11-13).

The verdict does not change. NonCommercial still rules the models out of the product.

## Not verified

- ffmpeg in `python:3.12-slim`: still read from Debian's copyright file only. Docker was installed but its engine was not running on 2026-11-13, so `ffmpeg -version` and `ffmpeg -L` were not run. Run `docker run --rm python:3.12-slim sh -c "apt-get update -qq && apt-get install -y -qq --no-install-recommends ffmpeg >/dev/null && ffmpeg -version && ffmpeg -L"` and record the configure flags and license line.
- Harmonix Set audio terms: the license for the spectrogram archive is inside a Dropbox download that was not fetched. all-in-one stays "don't use" until it is read.
