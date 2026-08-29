# Rekordbox Link — design & implementation plan

## The problem

`rekordbox.py:_location()` writes an **absolute server path** into the XML:

```python
p = Path(file_path).resolve().as_posix()   # /music/Artist - Title.mp3
return "file://localhost" + quote(p, ...)
```

The server's truth is `/music/…`; Rekordbox's truth is `C:\Users\marco\Nextcloud\Music\…`.
Nothing reconciles them, so every ingested track shows up in Rekordbox as a missing
file. Every other complaint about this feature is downstream of that:

| Symptom | Real cause |
|---|---|
| "Tracks import but files are missing" | server path ≠ DJ-machine path |
| "Browse… shows folders I don't recognise" | the picker lists the *container* filesystem |
| "Collection XML goes stale" | it must be re-exported by hand and copied somewhere the server reads |
| "Nextcloud integration is bad" | there is no integration — just a doc note saying "sync it yourself" |
| "It silently breaks" | nothing verifies the setup; you find out inside Rekordbox |

## The fix, in one sentence

Stop treating an absolute path as a track's identity. A track is a
**library-relative path**; every machine joins it against its own root.

```
server:      /music            + Hardstyle/Artist - Title.mp3
studio PC:   C:\…\Nextcloud\Music + Hardstyle\Artist - Title.mp3
macbook:     /Users/m/Music    + Hardstyle/Artist - Title.mp3
```

## Architecture

### Machine profiles

`config.json` grows a `profiles` list. One profile = one machine that runs Rekordbox.

```jsonc
{
  "id": "studio-pc",
  "name": "Studio PC",
  "os": "windows",                 // windows | macos | linux
  "library_root": "C:\\Users\\marco\\Nextcloud\\Music",   // DJ-side root
  "xml_path": "",                  // DJ-side XML path (default: <library_root>/getsetmix-<id>.xml)
  "server_xml_path": "",           // where the server writes it (default: <server library>/getsetmix-<id>.xml)
  "collection_xml_path": "",       // server-readable copy of that machine's collection export
  "agent_token": "…", "last_seen": "…", "last_report": { … }
}
```

The server writes **one XML per profile**, with Locations already correct for that
machine. Stateless, no runtime translation, multi-machine for free. Defaulting the
XML into the library root means the sync tool carries it along with the music.

**Back-compat:** with `profiles == []` the writer falls back to today's single
`xml_path` with identity mapping, so existing installs are untouched.

### Verification, not hope

`app/health.py` runs the same checks continuously and on demand:

- library root exists and is writable (probe write + unlink)
- each profile's XML directory is writable, and the XML parses
- collection XML age — warn past 30 days (stale export)
- **location resolution**: sample N tracks from a profile's XML, map back to
  server paths, `stat()` them — reports `18/20 resolve`
- companion last-seen age, and its last DJ-side verification report

Surfaced as a link-status chip in the toolbar (green/amber/red) and as the
wizard's verify step. Each failing check carries a `fix` string.

### The companion — `gsm-link`

Headless, stdlib-only, single file, runs on the DJ machine. It knows things the
server cannot:

1. **Nextcloud folder map** — parses `nextcloud.cfg` (`Folders\N\localPath` /
   `targetPath`) to derive the local root for a synced remote path. This is the
   auto-config: the user never types a path.
2. **Rekordbox preferences** — locates the app-data dir and reports whether the XML
   path can be set programmatically. Best-effort by design: when it cannot confirm
   the format it reports `manual` and the wizard shows the path to paste. We never
   claim to have configured something we didn't.
3. **DJ-side verification** — resolves sample Locations from the XML and reports
   how many exist.

Protocol (polling, no websockets):

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/link/pair` | short-lived 6-digit code | claim/create a profile, receive an agent token |
| `POST /api/link/sync` | `X-GSM-Agent-Token` | push machine facts + verification report, receive desired config |

### Nextcloud, properly

`app/delivery.py` adds WebDAV as an output target: app-password auth,
`PUT /remote.php/dav/files/<user>/<path>`, `MKCOL` for parents, XML uploaded
alongside the audio. The server no longer needs the sync client mounted — which is
what made this awkward under Docker/k8s in the first place.

### The wizard

Served by the **server**, opened from the **DJ machine's browser** (`/setup`).
The companion has no UI; its findings render inside the wizard.

1. Library — where files land server-side, with a live write test
2. Delivery — same machine / Nextcloud sync / Nextcloud WebDAV / Syncthing / mount / manual
3. DJ machine — pairing code + per-OS install snippet, or manual profile entry with
   a live preview of the resulting `Location` string
4. Verify — run every check, show pass/fail with the exact fix for each failure
5. Done

## Staging

1. `feat(rekordbox)` — library-relative paths + profiles + per-profile XML
2. `feat(api)` — health checks + link status
3. `feat(link)` — pairing/sync API
4. `feat(agent)` — the companion
5. `feat(delivery)` — WebDAV
6. `feat(ui)` — the wizard
7. `feat(ui)` — dark theme, settings sections, status chip
8. `docs` — rewrite setup docs around the wizard

## Known unknowns

- **Rekordbox preference format** is undocumented and version-dependent. The agent
  reports what it finds and degrades to manual instructions rather than guessing.
- **Nothing can force Rekordbox to reload the XML tree** — no API, no CLI. The agent
  can only notify; the refresh stays a human click.
- **Reading `master.db` directly** (via `pyrekordbox`) would kill the manual
  collection export entirely, but it is SQLCipher-encrypted and version-fragile.
  Deliberately out of scope here; the profile model leaves room for it as a future
  source alongside the XML export.
