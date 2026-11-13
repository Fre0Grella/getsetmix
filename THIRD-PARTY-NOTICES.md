# Third-party notices

GetSetMix is licensed under AGPL-3.0-only (see [LICENSE](LICENSE)). It ships or downloads the third-party components below. Each stays under its own license. This list was read from `requirements.txt`, `Dockerfile`, `companion/go.mod`, `companion/internal/setup/download.go` and `.github/workflows/release.yml`. The license of each component was checked on 2026-11-13; see [docs/research/licenses.md](docs/research/licenses.md) for the sources.

Where a license asks for its text to travel with the software, the full text is in the upstream repository linked in each entry.

## GPL components and where their source is offered

Two kinds of GPL software are involved. GetSetMix offers the corresponding source for both, as follows.

- **mutagen** (GPL-2.0-or-later) is a Python library inside the Docker image and the PyInstaller executables. GetSetMix is AGPL-3.0-only and combines with it under the GPL version 3 terms. The complete source of the GetSetMix side is this repository. The source of mutagen is at https://github.com/quodlibet/mutagen and on PyPI at https://pypi.org/project/mutagen/#files (the sdist).
- **ffmpeg** (GPL) runs as a separate program. It is not linked into GetSetMix. Its source is offered in the entries for each build below.

## In the Docker image

| Component | Used for | License | Copyright | Upstream |
|---|---|---|---|---|
| Python 3.12 (base image `python:3.12-slim`) | Runtime | PSF-2.0 | Python Software Foundation | https://www.python.org/ |
| ffmpeg (Debian package) | Audio conversion and probing, as a separate process | GPL-2.0-or-later per Debian's copyright file (some flavors GPL-3.0-or-later) | The FFmpeg developers and the authors of the bundled libraries, as listed in Debian's copyright file | https://ffmpeg.org/ |
| Deno 2.9.3 | JavaScript runtime for yt-dlp's challenge solver | MIT | Copyright 2018-2026 the Deno authors | https://github.com/denoland/deno |
| FastAPI | Web framework | MIT | Copyright (c) 2018 Sebastian Ramirez | https://github.com/fastapi/fastapi |
| uvicorn (with the `standard` extras) | ASGI server | BSD-3-Clause | Copyright 2017-present, Encode OSS Ltd | https://github.com/Kludex/uvicorn |
| yt-dlp (with the `default` extras) | Downloads media | Unlicense | none (public domain) | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | JavaScript challenge solvers for yt-dlp | Unlicense | none (public domain) | https://github.com/yt-dlp/ejs |
| mutagen | Reads and writes audio tags | GPL-2.0-or-later | See the upstream COPYING and README | https://github.com/quodlibet/mutagen |
| python-multipart | Form and upload parsing | Apache-2.0 | See the upstream LICENSE | https://github.com/Kludex/python-multipart |

**ffmpeg source.** The package comes from Debian. Debian publishes the source package and its copyright file at https://metadata.ftp-master.debian.org/changelogs/main/f/ffmpeg/stable_copyright. Upstream source: https://ffmpeg.org/releases/. The exact Debian release depends on the `python:3.12-slim` tag at build time.

**Python packages installed as dependencies of the ones above.** These are installed by `pip` and carry their own licenses, as given in their PyPI metadata: starlette (BSD-3-Clause), pydantic and pydantic-core (MIT), anyio (MIT), annotated-types (MIT), typing-extensions (PSF-2.0), click (BSD-3-Clause), h11 (MIT), httptools (MIT), uvloop (MIT or Apache-2.0), watchfiles (MIT), websockets (BSD-3-Clause), python-dotenv (BSD-3-Clause), PyYAML (MIT), brotli (MIT), certifi (MPL-2.0), pycryptodomex (BSD-2-Clause and public domain), requests (Apache-2.0), urllib3 (MIT), charset-normalizer (MIT), idna (BSD-3-Clause), sniffio (MIT or Apache-2.0). The exact set and versions depend on what `pip` resolves at build time. Not verified: the set was taken from the PyPI metadata of the direct requirements, not from a built image.

## In the PyInstaller executables (Windows and macOS)

The executables bundle the Python runtime, the app, and the Python packages named in `requirements.txt` and their dependencies, with `yt_dlp` and `yt_dlp_ejs` collected in full. They do not contain ffmpeg or Deno. Those are downloaded by Setup (next section).

| Component | Used for | License | Copyright | Upstream |
|---|---|---|---|---|
| Python 3.12 | Runtime | PSF-2.0 | Python Software Foundation | https://www.python.org/ |
| PyInstaller (bootloader and hooks) | Builds the executable | GPL-2.0-or-later with a special exception that allows bundling in any program | See the upstream COPYING.txt | https://github.com/pyinstaller/pyinstaller |
| mutagen | Reads and writes audio tags | GPL-2.0-or-later | See the Docker table | https://github.com/quodlibet/mutagen |
| FastAPI, uvicorn, yt-dlp, yt-dlp-ejs, python-multipart and their Python dependencies | As in the Docker table | As in the Docker table | As in the Docker table | As in the Docker table |

## Downloaded by Setup (not inside GetSetMix's own files)

Setup downloads these at install time, checks the SHA-256 of each file, and stores them on the user's machine. They are not part of GetSetMix's release files. The URLs and versions are pinned in `companion/internal/setup/download.go`.

| Component | Used for | License | Copyright | Upstream and source |
|---|---|---|---|---|
| ffmpeg and ffprobe 9.0.2, Windows x64, "essentials" build by Gyan Doshi | Audio conversion and probing | GPL-3.0-only as stated by the vendor: "All builds are 64-bit, static and licensed as GPLv3" | The FFmpeg developers and the authors of the bundled libraries | Download: https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2 . Vendor page, with links to the matching FFmpeg source commit: https://www.gyan.dev/ffmpeg/builds/ . Source: https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz |
| ffmpeg and ffprobe 9.0.2, macOS arm64, build 1789931890_9.0.2 by Martin Riedl | Audio conversion and probing | GPL-3.0-or-later. The build's configure line has `--enable-version3 --enable-gpl` and no `--enable-nonfree` | The FFmpeg developers and the authors of the bundled libraries | Download: https://ffmpeg.martin-riedl.de/ . Build info: https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/versions.txt . Build script (Apache-2.0): https://git.martin-riedl.de/ffmpeg/build-script . Source: https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz |
| Deno 2.9.7, Windows x64 and macOS arm64 | JavaScript runtime for yt-dlp's challenge solver | MIT | Copyright 2018-2026 the Deno authors | https://github.com/denoland/deno |

The macOS ffmpeg license is derived from the configure flags in the build's own `versions.txt`, because the vendor's page states none.

## In Setup and the companion (Go, compiled in)

Setup and the companion are one Go module (`companion/go.mod`). Each library below is compiled into the binaries.

| Component | Used for | License | Copyright | Upstream |
|---|---|---|---|---|
| go-sqlcipher (mutecomm) | Encrypted SQLite | MIT, BSD-3-Clause and the SQLite public-domain blessing, in one file | Copyright (c) 2014 Yasuhiro Matsumoto; ZETETIC LLC (SQLCipher code) | https://github.com/mutecomm/go-sqlcipher |
| SQLCipher (inside go-sqlcipher) | Database encryption | BSD-3-Clause | Copyright (c) 2025, ZETETIC LLC | https://github.com/sqlcipher/sqlcipher |
| dhowden/tag | Reads audio tags | BSD-2-Clause | Copyright 2015, David Howden | https://github.com/dhowden/tag |
| fsnotify | File watching | BSD-3-Clause | Copyright (c) 2012 The Go Authors; Copyright (c) fsnotify Authors | https://github.com/fsnotify/fsnotify |
| golang.org/x/sys | OS calls | BSD-3-Clause | Copyright 2009 The Go Authors | https://github.com/golang/sys |
| golang.org/x/text | Text handling | BSD-3-Clause | Copyright 2009 The Go Authors | https://github.com/golang/text |
| rsc.io/qr | QR codes for pairing | BSD-3-Clause | Copyright (c) 2009 The Go Authors | https://github.com/rsc/qr |

The Go standard library (BSD-3-Clause, Copyright The Go Authors, https://go.dev/LICENSE) is compiled in as well.

## Not shipped

Tools checked in `docs/research/licenses.md` but not shipped (research spikes only, or "don't use") are not listed here.
