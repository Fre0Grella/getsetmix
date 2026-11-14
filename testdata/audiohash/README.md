# Audio hash fixtures

Small audio files, a few kilobytes each, and the audio id each one must get.
The Python implementation (`app/audiohash.py`, tested by
`tests/test_audiohash.py`) and the Go implementation
(`companion/internal/audio/hash.go`, tested by `hash_test.go` next to it)
both read this folder, so the two cannot drift apart. A change here runs both
test suites in CI. The rules are in
[`docs/design/library.md`, section 4.2](../../docs/design/library.md#42-the-audio-hash).

## `expected.json`

```json
{
  "version": 1,
  "made_with": "ffmpeg version …",
  "files": { "mp3/plain.mp3": "a1_…", "fallback/vorbis.ogg": "f1_…" },
  "same": { "mp3": ["mp3/apev2.mp3", "mp3/plain.mp3"] },
  "different": [["aiff/anno.aif", "fallback/opus.opus", "mp3/other-audio.mp3"]]
}
```

| Key | Meaning |
|---|---|
| `version` | the shape of this file; `1` |
| `made_with` | the ffmpeg that made the base audio, for the record |
| `files` | every fixture, as a `/`-separated path relative to this folder, with the exact id it must get |
| `same` | named groups of files that hold the same audio with different tags, covers, padding, chunks or atom order; all files of a group must get one id |
| `different` | lists of files whose ids must all be different from each other |

A test needs only `files` to check every id; `same` and `different` say why
the ids are what they are, and make a mistake in `files` itself visible.

The format is chosen by the file extension, lowercased: `.mp3`, `.flac`,
`.wav`, `.aif` and `.aiff`, `.m4a` and `.mp4`. Everything else, and every
file that does not parse by its rule, gets the fallback id (`f1_`).

## The files

| Folder | What is in it |
|---|---|
| `mp3/` | one MPEG-2 Layer III stream (with its LAME Info frame) with no tags, ID3v2.3, ID3v2.4, an ID3v2.4 tag with a footer, junk between the tag and the first frame, a cover, grown padding, ID3v1, APEv2, Lyrics3v2, and all of them at once; a different audio stream; an MPEG-1 stream |
| `flac/` | one stream as ffmpeg wrote it, with STREAMINFO only, with Vorbis comments, a cover, grown padding, and an ID3v2 tag in front of `fLaC`; a different stream |
| `wav/` | 16-bit PCM with only `fmt ` and `data`, with a `LIST` chunk, an `id3 ` chunk, and odd-sized extra chunks; different PCM |
| `aiff/` | 16-bit PCM with only `COMM` and `SSND`, with an `ID3 ` chunk, and with an odd-sized `ANNO` chunk (`.aif`); different PCM |
| `m4a/` | one AAC stream with `moov` after `mdat`, with `moov` before `mdat`, both tagged so that `moov` grows, and with a cover; a different stream |
| `fallback/` | files that must get `f1_`: Ogg Vorbis and Opus (not hashed in version 1), raw AAC, truncated WAV, AIFF and MP4, a FLAC with a bad magic, an MP3 with no valid frame, an MP3 whose ID3v2 size points past the end, an RF64 file |

## Making them again

`make_fixtures.py` records how every file was made. It needs ffmpeg on PATH
and mutagen; the tests need neither ffmpeg nor the script.

```sh
python testdata/audiohash/make_fixtures.py
```

The expected ids are not computed with the implementation under test. The
script hashes the bytes it knows to be the audio (the PCM it generated, an
MP3 written without any tag, the frames after ffmpeg's FLAC metadata, the
payload of `mdat`) and only then adds tags around them. A newer ffmpeg can
produce different bytes, and therefore different ids: commit the files and
`expected.json` together.
