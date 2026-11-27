# CHANGELOG


## v1.23.0 (2026-11-27)

### Features

- **library**: Batch edit tags on a phone
  ([`f0e3575`](https://github.com/Fre0Grella/getsetmix/commit/f0e35753565fe8d1f40645558e8504b6ae4dc352))

Batch editing, slice 7: on a phone the edit panel is a sheet in three steps.

- What: every rule set as one tap, its rules named under it in the UI's language from the catalogue;
  or the field rows. - Check: one card per track, warnings first; a switch keeps or leaves out a
  track, a tap leaves out or puts back one change. - Apply: progress, counts, then only the
  failures, with Try again and Undo. - The resend note is cleared once an edit is written.

Closes #52

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.22.0 (2026-11-27)

### Features

- **library**: Covers, year and comment in edits
  ([`f88b889`](https://github.com/Fre0Grella/getsetmix/commit/f88b889bfbf4d48c12eea4da70573bb6aaa7963b))

* feat(library): covers, year and comment in edits

Batch editing, slice 6.

- set_cover and clear_cover steps for a selection: an image is uploaded first (POST
  /api/library/edits/covers), tags and cover go in one write, the cover an edit replaces is kept so
  undo puts it back, and undo leaves a cover changed since alone. - Library.write_tags takes the
  cover and a digest precondition; write_cover is a wrapper over it. - Tests for year.extract in an
  edit, a full date kept when the year is not edited, and every rule leaving the comment alone
  unless the step names it. - The purge removes kept covers with their journal, and old uploads. -
  UI: a Cover row in the Fields tab.

Closes #51

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

* test(ui): allow the cover 404 an undo can race

---------

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.21.0 (2026-11-27)

### Features

- **library**: Rule sets and a cleanup tab
  ([`5760e65`](https://github.com/Fre0Grella/getsetmix/commit/5760e6506ec754d489744a309db4849f87e419b5))

Batch editing, slice 4.

- Rules run as steps of an edit beside field operations; a rule's warnings join its change. - Rule
  sets: the built-in Standard cleanup, seeded from the catalogue and never changed or removed;
  saving, renaming, reordering and deleting your own (/api/library/rulesets). A preview can name a
  set with ruleset_id. - PATCH /api/library/edits/{id} leaves tracks or single changes out of a
  preview and puts them back; counts and resend follow. - UI: a Cleanup tab (cleanup.js) to pick a
  set, switch rules off, set their parameters and reorder them; the preview grouped by track with
  the changed part marked, checkboxes per track and change, and filters for warnings and fields.

Closes #49

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.20.0 (2026-11-27)

### Features

- **library**: Field operations and edit by filter
  ([`0c4f8ea`](https://github.com/Fre0Grella/getsetmix/commit/0c4f8ea9bcdefe2639a58e875611c13f79744115))

Batch editing, slice 5.

- Field operations clear, append, prepend and replace (plain text, whole word or not, case or not;
  never a pattern) beside set, each aimed only at the fields it allows: title and artist are never
  cleared. - A selection can be a filter of the Library list (q, genre, folder), resolved to ids
  when the preview is made and frozen there. - Every edit says what paired computers download again
  (resend). - The edit panel has one row per field, and offers the whole view when it holds more
  tracks than the selection.

Closes #50

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.19.0 (2026-11-27)

### Features

- **library**: Undo batch edits, and their history
  ([`1921697`](https://github.com/Fre0Grella/getsetmix/commit/1921697db97a6453a18ce22c5f72781617dc17dd))

Batch editing, slice 3.

- Undo is a new edit that writes the old values back through the same job and precondition: a field
  changed since is a conflict, a trashed track fails as gone, an undo can itself be undone, and part
  of an edit can be undone. - GET /api/library/edits lists applied edits, newest first. - Retention:
  edit_history_days (default 30, 0 for good, in Settings); a purged edit keeps its line and counts;
  unused previews go after a day. The purge runs at most once a day, when edits are used. - The bulk
  set_genre is now an edit (library design L9), so it shows in the history and can be undone; the
  request and answer are as before. - UI: Undo in the edit panel, and a History panel in the
  Library. - Ruff ceiling 31 -> 30 (an old try/except/pass in config.py).

Closes #48

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.18.0 (2026-11-27)

### Features

- **library**: Batch edit one field with preview
  ([`14fc439`](https://github.com/Fre0Grella/getsetmix/commit/14fc439d413b87784399d99a50464f08de01dc24))

Batch editing, slice 2: set one field on the selected tracks, see the changes, then write exactly
  those.

- app/edits.py stores a preview per track and field (old, new, the steps that made it, warnings) and
  applies it one file at a time through the Library's write, with the previewed values as the
  precondition: a file changed meanwhile is a conflict and is left alone, a failure fails that file
  only, applying again retries only the failures, one edit applies at a time, an unused preview
  expires. - rules.run_steps runs field operations beside rules (set for now). - /api/library/edits:
  preview, read, changes, apply. - The bulk bar gains Edit tags, a panel with preview and progress.
  - Companion test: tracks changed together update in one sync. - Ruff ceiling 38 -> 31 (old
  findings in files touched here).

Closes #47

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.17.0 (2026-11-27)

### Chores

- Check commits before they reach CI ([#93](https://github.com/Fre0Grella/getsetmix/pull/93),
  [`5b38ffb`](https://github.com/Fre0Grella/getsetmix/commit/5b38ffb29fc8c1d646c9aa2d58895f98ed1d6a09))

The headline rule is looser and lives in one place: 50 characters, not counting the " (#NN)" a
  squash merge adds, as a commitlint rule in commitlint.config.mjs. CI's PR-title job drops its own
  length count and runs commitlint alone, and the push to main accepts squash headlines up to 50
  characters plus the number.

The git hooks are switched on and check what CI would reject first: commitlint on each commit
  message (replacing conventional-pre-commit, whose rules differ from commitlint's), ruff and gofmt
  on each commit, go vet and the staticcheck ratchet before a push that touches the companion.
  CLAUDE.md and architecture 8.8 say so; a PR title, which no hook sees, is checked with `echo
  "<title>" | commitlint`.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Continuous Integration

- Run less, and in parallel ([#94](https://github.com/Fre0Grella/getsetmix/pull/94),
  [`a45fef8`](https://github.com/Fre0Grella/getsetmix/commit/a45fef8b4ab5eced64f18c854f9010069479bca6))

Three changes to make a pull request's checks finish sooner.

- Setup is built beside the companion tests, not after them. A release still waits for the tests
  (build needs test). - The importer and library tests run in parallel. Each opens an encrypted
  master.db, which is slow by design, and they ran one by one: locally the importer tests went from
  about 200 s to 58 s, the library tests from 95 s to 25 s, with no race under -race. The two tests
  that replace a package variable (quickCheck, syncWait) stay sequential; Go runs those before the
  parallel ones. - A changes job skips the app's tests, browser tests and image build when a pull
  request only touches the companion, the docs, the site or other workflows' files. lint always
  runs: it also counts the companion's duplication. Main has no required checks, so a skipped job
  cannot block a merge.

Windows keeps -parallel 1: there, parallel runs were slower (importer 72 s to 156 s). Measured on
  this PR: the companion workflow took 182 s, down from 318 s on #92.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Documentation

- Code signing policy for SignPath ([#95](https://github.com/Fre0Grella/getsetmix/pull/95),
  [`f4c7c87`](https://github.com/Fre0Grella/getsetmix/commit/f4c7c874ea7aa8c289bb97a22e1ed6cc38946127))

README's Install section has what SignPath Foundation's conditions ask of the download page: the
  code signing policy, a privacy statement, what Setup changes on the computer and how to remove it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- Signing waits for the public launch ([#96](https://github.com/Fre0Grella/getsetmix/pull/96),
  [`ca51dce`](https://github.com/Fre0Grella/getsetmix/commit/ca51dcee20830eb89e82c19fca890f7f7fd03fd7))

README says releases are unsigned until the public launch; no SignPath application before then.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Features

- **library**: Select tracks and act in bulk
  ([`6e3bb61`](https://github.com/Fre0Grella/getsetmix/commit/6e3bb610716403211aafb2c6e44640df406722c8))

Pick several tracks in the Library view (long press on a phone; Ctrl-, Shift- or cover-click on a
  desktop) and act on all of them from a bar in the deck: Set genre, Delete (asks with the count,
  offers Undo), and Restore in the trash.

POST /api/library/bulk runs delete, restore or set_genre per id through the single-track internals
  and reports the outcome per id, so one failure never hides the rest.

Closes #39

Claude-Session: https://claude.ai/code/session_01P6dL1ubJcR7rkeStcK3oqS

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>

### Refactoring

- **companion**: A pure track package ([#87](https://github.com/Fre0Grella/getsetmix/pull/87),
  [`088592f`](https://github.com/Fre0Grella/getsetmix/commit/088592f3d4b6480f36456cdce719bd4783cef404))

Slice 1 of the sync ledger (docs/design/library.md, 4.6.1).

track holds what every package means by a track: Track, Tags, Changed, PathKey, Local, the Rekordbox
  file type codes and the link listing types (the removed entry is track.Tombstone). library and
  fetch keep aliases while callers move; audio, scan, fetch and config use track directly, so none
  of them reaches library or SQLCipher any more. The MP3 builder for tests moves from librarytest to
  a pure track/tracktest, so fetch's tests skip the cgo driver as well.

internal/layers is the import-rule test: go list -deps -test of the pure packages must name neither
  library nor go-sqlcipher, and track imports nothing of the companion. It stats the module's Go
  files, so the test cache reruns it after an import changes. Architecture 8.8 lists the rule. Go
  duplication fell to 0.26%: ceiling lowered.

No behaviour change.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **companion**: Drop the track aliases ([#92](https://github.com/Fre0Grella/getsetmix/pull/92),
  [`03701ec`](https://github.com/Fre0Grella/getsetmix/commit/03701ecdcd9438f92b770a8fb212c4137b5ec0ef))

Slice 5 of the sync ledger (docs/design/library.md, 4.6.1), the last: clean-up.

The aliases kept while callers moved are gone: library's Track, Tags, file type codes, field names,
  AllFields, Changed and PathKey, and fetch's File, Removed, Listing, Local and Server. Every use
  names track or config. The tests of Changed, PathKey and Local move to track. The ledger's begin,
  newer and remember are private: only the ledger calls them now.

The fetch package comment and section 4.6 of the design say who owns fetched.json now; 4.6.1 is
  marked implemented.

No behaviour change.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **companion**: Ledger plans fetches ([#91](https://github.com/Fre0Grella/getsetmix/pull/91),
  [`f48b097`](https://github.com/Fre0Grella/getsetmix/commit/f48b0972271dd46ebac67da9100ba0fe822718b0))

Second half of slice 4 of the sync ledger (docs/design/library.md, 4.6.1): the fetch side.

ledger.Fetched.Plan says what a fetch does with one listing: Get, Refresh and Keep steps in listing
  order, the tombstones to record, the ones the server lists again (and which of them to fetch
  again), and the local files for the recycle bin. It keeps today's rules: one step per audio id, so
  a track listed at two server paths is fetched once; a newer copy of a track deleted here is only
  noted; only tracks this computer holds get a tombstone, and only a deleted one goes to the recycle
  bin.

fetch does the network and file work and records each outcome: Got, Refreshed, Kept, Tombstoned,
  Restored, Recycled. Its own decision code (the old tombstones walk and the checks in Run, fetchNew
  and refresh) is gone.

No behaviour change: every fetch test keeps its assertions; one test that called the tombstone walk
  directly now asks the plan for it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **companion**: One owner for the state ([#89](https://github.com/Fre0Grella/getsetmix/pull/89),
  [`e264593`](https://github.com/Fre0Grella/getsetmix/commit/e264593df9b2dcd130ffe96313c3c5d688ef2242))

Slice 3 of the sync ledger (docs/design/library.md, 4.6.1).

internal/ledger is the only package that reads or writes fetched.json (Fetched, moved from
  fetch.State) and state.json (Synced, moved from config.State), in the formats and with the
  migrations they always had. Either file can be saved only through its held lock, FetchLock or
  SyncLock; ReadFetched and ReadSynced are snapshots for questions.

One sync at a time (decision 1): a sync takes sync.lock, waits up to 30 s for another one, and
  otherwise returns ErrSyncRunning having done nothing. The launcher still starts Rekordbox, a fetch
  logs it, the watcher tries again; a dry run takes no lock. The holder refreshes sync.lock every
  minute, so a dead sync blocks for at most five minutes. fetch.lock behaves as before. Baseline
  writes under sync.lock; one sync reads fetched.json once, not twice.

config is companion.json alone, with config.Server (fetch.Server is an alias for one release).
  Setup's seed is fetch.Seed, beside RunLocked. atomicfile.WriteJSON replaces three copies of the
  same write. ledgertest writes state for tests under the lock. The layers test adds the ledger,
  config as settings only, and that no code outside the ledger names its files.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **companion**: One row lookup per file ([#88](https://github.com/Fre0Grella/getsetmix/pull/88),
  [`d03e534`](https://github.com/Fre0Grella/getsetmix/commit/d03e534022943a15bc296500b216df1a7680da73))

Slice 2 of the sync ledger (docs/design/library.md, 4.6.1).

rowsByPath (library/rows.go) is the one place that picks the djmdContent row for a file. Update,
  MarkRemoved and Import use it, and so does KnownPaths, through knownPaths; contentIDs and the two
  inline queries are gone. localDevice is the device detection Import already had, now shared with
  Update.

The winner, when Rekordbox holds several live rows for one file, is this computer's oldest row; when
  this computer has none, the oldest row of any device, as before. "Already in Rekordbox?" still
  counts every device's rows, so a library whose rows carry an old device ID is not imported twice.
  Decision 2 in the design records this refinement.

Tests: a duplicate row is updated, listed and restored as one row; this computer's row wins over an
  older row of another device; another device's row is used when it is the only one. Each fails
  against a mutant of the rule it protects.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **companion**: The ledger plans a sync ([#90](https://github.com/Fre0Grella/getsetmix/pull/90),
  [`afdf413`](https://github.com/Fre0Grella/getsetmix/commit/afdf413a64c3c0ba35c2eabdde4eb968cae2087c))

First half of slice 4 of the sync ledger (docs/design/library.md, 4.6.1): the importer's side.

ledger.WorkFor answers what a sync does about the server's tracks: Changed (a newer copy is in place
  and the row is behind), Removed (a tombstone not listed yet) and Restored (listed, but no
  tombstone any more), as Items with the audio id, the local path, its key and, for a changed track,
  the tags last seen. Unhandled, Handled, Listed, Unlisted and Applied are the record calls;
  NewSynced is Baseline's fresh state.

importer.removals, Fetched.Stale, the key handling around the fetch lock and the re-keying at the
  end of Sync are gone: the importer hands the items back, and maps the library's results back by
  the paths it gave. status asks WorkFor too.

Golden files in internal/ledger/testdata record each form of fetched.json and state.json; each is
  asked, saved, asked again, and read with a frozen copy of the decoder, the old-companion check.
  They pin one old answer: a tombstone in its first form names no path, so it lists nothing. Go
  duplication fell to 0.25%: ceiling lowered.

No behaviour change: the importer and fetch tests keep their assertions.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.7 (2026-11-26)

### Bug Fixes

- **ui**: Translate errors, labels, plurals ([#86](https://github.com/Fre0Grella/getsetmix/pull/86),
  [`12a1c79`](https://github.com/Fre0Grella/getsetmix/commit/12a1c79e26944739bb7d1cfd8a2ab674d2ab77b8))

The words items of #83: - server errors are English; i18n.js now says them in Italian
  (SERVER_ERRORS_IT, patterns for the ones built from parts), and tests/test_ui_words.py fails when
  a message app/*.py can raise has no pattern, or a pattern matches no message any more; -
  screen-reader labels (close, search, link, sort, folder, ...) are translated through
  data-i18n-aria, like placeholders; - plural(n, one, other) and num(n) replace ten inline switches
  and the hand-written toLocaleString calls; - one key per phrase: changeCover, album and genre were
  each defined twice; `cancel` (which said "Stop") is `stop`, and libCancel is `cancel`.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.6 (2026-11-26)

### Bug Fixes

- **setup**: Take the app's colours ([#85](https://github.com/Fre0Grella/getsetmix/pull/85),
  [`6d364f1`](https://github.com/Fre0Grella/getsetmix/commit/6d364f19641a36e3ed0ed0dd793b47844db64409))

The Setup window took 21 of the app's colour tokens as its own copy, and five had drifted.
  tokens.css is now generated from the app's palette and a Go test fails when the copy and the app
  disagree; setup.css keeps only its own rail, wash, code colours and fonts. The 15 inline styles in
  setup.js are classes.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Documentation

- **design**: The companion's sync ledger ([#78](https://github.com/Fre0Grella/getsetmix/pull/78),
  [`40dc7d0`](https://github.com/Fre0Grella/getsetmix/commit/40dc7d0b8efc8f7c61641532dd69431062a44d81))

docs/design/library.md 4.6.1, approved: a pure track package, one ledger that owns fetched.json and
  state.json, sync.lock (30 s wait), the oldest row of this computer's DeviceID, the removed records
  kept as they are. Decision 10 in docs/architecture.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.5 (2026-11-24)

### Bug Fixes

- **ui**: One notice, badge and pill style ([#84](https://github.com/Fre0Grella/getsetmix/pull/84),
  [`b82d448`](https://github.com/Fre0Grella/getsetmix/commit/b82d44892c17a6080b170add29bbb4c4a7df28ac))

Part of #83: one .notice, .badge, .count and .btn-pill; the view switch shares .seg's track; tokens
  for the top bar height and the raw shadows and colours; one download icon; .lib-note defined once.
  CLAUDE.md lists the commit and PR-title rules.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Refactoring

- **ui**: One palette, shared icons ([#82](https://github.com/Fre0Grella/getsetmix/pull/82),
  [`79af863`](https://github.com/Fre0Grella/getsetmix/commit/79af863cc71cc4792abd479f04cc99ddbb7249ad))

data-theme always holds the theme shown, so styles.css has one dark palette instead of two identical
  blocks; the close and trash icons are symbols in the sprite, used everywhere. Screenshots match.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **ui**: Split the UI into ES modules ([#81](https://github.com/Fre0Grella/getsetmix/pull/81),
  [`5cf4aaf`](https://github.com/Fre0Grella/getsetmix/commit/5cf4aaf1c10e7513af189ead31a1643d28505b03))

app.js and library.js now import what they use from core.js (requests, escaping, toasts, the dialog,
  shared state), i18n.js (the words) and cover.js (the cover picker) instead of sharing ~20 globals;
  library.js never imports app.js. .js is served as text/javascript so modules run on any Windows
  registry.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.4 (2026-11-24)

### Bug Fixes

- **ui**: Take the rules from the server ([#80](https://github.com/Fre0Grella/getsetmix/pull/80),
  [`cfa0842`](https://github.com/Fre0Grella/getsetmix/commit/cfa08424eb071ce8da0cad7c04c873e1a9332d6a))

The UI reads damaged, source, the year range, the source pattern, the list's order and each track's
  editable/active from the server instead of keeping its own copies. The "replace the link?"
  question now fires only for a stamped "Source: <url>".

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.3 (2026-11-24)

### Bug Fixes

- **ui**: Health dot, duplicate dialog, token
  ([#79](https://github.com/Fre0Grella/getsetmix/pull/79),
  [`10ce8b1`](https://github.com/Fre0Grella/getsetmix/commit/10ce8b162d7cdca94e6b6b26b5dd90828d8d6f2f))

The health dot keeps engine problems red; the duplicate question uses the app dialog; every request
  goes through request(), which asks for the token once on a 401 and not again after a dismissal.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.2 (2026-11-24)

### Bug Fixes

- **companion**: Keep the sync list on rerun
  ([#77](https://github.com/Fre0Grella/getsetmix/pull/77),
  [`db64144`](https://github.com/Fre0Grella/getsetmix/commit/db6414401986368198e9636c8a5394dea2bde502))

Setup run again no longer replaces fetched.json (it seeds only an empty state, under the lock).
  fetch.RunLocked is the one way to fetch; one path -> row lookup with the oldest row winning;
  importer.Split shared by sync and status, which now counts tracks changed on the server.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.1 (2026-11-24)

### Bug Fixes

- One definition per thing, typed ([#76](https://github.com/Fre0Grella/getsetmix/pull/76),
  [`5cfe94f`](https://github.com/Fre0Grella/getsetmix/commit/5cfe94fb903370c51bb565a4ea4dcc667e71026d))

The fixes from the 2026-11-24 health check, with the ceilings lowered: ruff 45 -> 39, pyright 30 ->
  0, Python duplication 0.13 -> 0, staticcheck 5 -> 0, coverage floor 86 -> 93. Background tasks
  kept until done; staged covers checked like Library covers; one helper each for atomic writes
  (Python and Go), timestamps, outbound requests and bearer parsing; settings values only in config.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Continuous Integration

- Ratchet lint, types and coverage ([#74](https://github.com/Fre0Grella/getsetmix/pull/74),
  [`9c9eef1`](https://github.com/Fre0Grella/getsetmix/commit/9c9eef1f0eb9539f9bb0acb6f40f585af96e2cfe))

Ceilings in ratchets.json at today's values, checked by scripts/ratchet.py: ruff 45, pyright 30,
  import contracts 0 broken, duplication py 0.13 / js 0 / go 0.27, coverage floor 86, staticcheck 5
  (Linux). Browser smoke tests in tests/ui run in a new ui job.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Documentation

- Write down the code rules and checks ([#75](https://github.com/Fre0Grella/getsetmix/pull/75),
  [`ea160f0`](https://github.com/Fre0Grella/getsetmix/commit/ea160f04c899e0e386e00d917793e8e337dff7bb))

docs/architecture.md 8.8: the layering, pure modules, settings only in config.py, one definition per
  thing, and the rule -> check table; decision 9 (CI ratchets). Module tables, track identity and
  risks brought up to date. CLAUDE.md points future sessions at 8.8.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.16.0 (2026-11-24)

### Features

- Check downloads against the library ([#73](https://github.com/Fre0Grella/getsetmix/pull/73),
  [`411b157`](https://github.com/Fre0Grella/getsetmix/commit/411b157b28c2124afe4a70e1c057aa4fd2dea285))

Drops the Rekordbox XML features (inbox XML, collection purge, XML duplicate check and their
  settings). Finished downloads show where they are in the Library now (present, trash, gone);
  Already owned? matches the Library index by source URL or title and artist.

Closes #71

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.15.2 (2026-11-24)

### Bug Fixes

- **ui**: Keep dialogs inside a phone screen
  ([#72](https://github.com/Fre0Grella/getsetmix/pull/72),
  [`d580a65`](https://github.com/Fre0Grella/getsetmix/commit/d580a65b6a99cf592c12cf4e79d0b72d4bd5461e))

min-width: 0 on the dialog card: a long file name no longer pushes the Library sheet past the right
  edge of a phone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.15.1 (2026-11-24)

### Bug Fixes

- **library**: Confirm deletes, no drag-close
  ([#70](https://github.com/Fre0Grella/getsetmix/pull/70),
  [`e7b6d91`](https://github.com/Fre0Grella/getsetmix/commit/e7b6d919e364ed09922b70ec5899a8c485c55cfb))

A modal closes on the backdrop only when the press started there too. Delete, restore and Empty
  trash ask first in the app's own dialog.

Closes #66

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.15.0 (2026-11-24)

### Features

- **library**: Small cover thumbnails ([#67](https://github.com/Fre0Grella/getsetmix/pull/67),
  [`e9d1bee`](https://github.com/Fre0Grella/getsetmix/commit/e9d1bee6856b9a63d47368bf618ecb3fe55b184c))

The list loads a 144 px JPEG of each cover (?size=thumb), made once per content_rev and kept under
  DATA_DIR/thumbs. On real covers it is about 5 KB against 107 KB, so a full scroll costs about 3 MB
  instead of 60. Only the JPEG, PNG, WebP and GIF decoders run, with size and pixel caps. Adds
  Pillow (MIT-CMU).

Closes #65

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.14.0 (2026-11-24)

### Features

- **library**: The full view ([#64](https://github.com/Fre0Grella/getsetmix/pull/64),
  [`003c025`](https://github.com/Fre0Grella/getsetmix/commit/003c02580133b3dd3d41d54f832ebd50a240fd65))

A virtualised list in pages of 200, genre and folder filters with counts, sorts, row covers loaded
  lazily, a preview player with range requests, cover replacement, and markers for shared audio and
  read-only files. On a phone the search sits under the thumb.

Covers are served only as image types the app can trust, so a picture in a file's tags cannot run
  script in the app.

Closes #40

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.13.0 (2026-11-24)

### Features

- **library**: Edit one track, all the way ([#63](https://github.com/Fre0Grella/getsetmix/pull/63),
  [`7ce6797`](https://github.com/Fre0Grella/getsetmix/commit/7ce679756898c835a023ea0f9593cb2e4d681cb3))

Add the tagger's atomic edit path, library.write_tags with a check of old values, GET and PATCH
  /api/library/{id}, and the detail sheet. An edit keeps the file's owner, so a shared volume stays
  accessible.

On the computer, a track with a newer rev is downloaded again and checked against its audio id. The
  importer then updates only the changed fields of its Rekordbox row, under the existing safety.

Closes #37

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.12.0 (2026-11-24)

### Features

- **library**: Delete and restore ([#60](https://github.com/Fre0Grella/getsetmix/pull/60),
  [`b7bc619`](https://github.com/Fre0Grella/getsetmix/commit/b7bc619b5cdcf444a82bb1c57f34551913075246))

* feat(library): delete and restore

Trash with restore and purge (trash_days, default 30), tombstones in removed[], the Trash view and
  an Undo toast. The companion adds removed tracks to a 'GetSetMix: removed on server' playlist
  under the importer's safety and can move the local file to the recycle bin (opt-in, off).

Closes #38

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

* fix(library): keep replaced and vanished files

A path the server lists again under another id was replaced, so it is no longer a removal and leaves
  the "removed on server" playlist. The option to delete the local file acts only on tracks deleted
  in GetSetMix: a file that vanished from the server may have its last copy on this computer.

---------

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.11.0 (2026-11-14)

### Documentation

- Check ffmpeg in the Docker image ([#58](https://github.com/Fre0Grella/getsetmix/pull/58),
  [`4af8d76`](https://github.com/Fre0Grella/getsetmix/commit/4af8d765c227a1942d364f46229bd5c37b8f732d))

Ran the published image (release 1.10.0, Debian 13): ffmpeg 7.1.5 is built with --enable-gpl and
  without --enable-nonfree, so it is GPL-2.0-or-later, and Debian's copyright file ships next to
  ours.

The Harmonix audio terms are no longer needed: all-in-one is "don't use" for reasons that do not
  depend on them. Nothing is left under "Not verified".

Closes #28

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>

### Features

- **link**: Protocol 2 with audio ids ([#59](https://github.com/Fre0Grella/getsetmix/pull/59),
  [`0cdc31e`](https://github.com/Fre0Grella/getsetmix/commit/0cdc31e39f9128af279a84de1f7d4f5158177a62))

The server serves /api/link/files from the library index, with protocol, rev, files[].id,
  files[].rev and removed[]; it answers as protocol 1, from a disk walk, until the first index is
  complete. Of two files with the same audio it lists one. A move keeps a file's rev (new
  content_rev column), so it is not downloaded again.

The companion gets the audio hash in Go, tested against the shared fixtures; reads protocol 2 and
  still works against protocol 1; migrates fetched.json to version 2 keyed by audio id, keeping the
  old file as fetched.v1.json; widens state.json values to {at, size, mtime}. Files Rekordbox cannot
  import (Ogg, Opus) are no longer downloaded, and `gsm-companion status` says how many and why.

Closes #36 Closes #31

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.10.0 (2026-11-13)

### Features

- Ship license notices with every build ([#57](https://github.com/Fre0Grella/getsetmix/pull/57),
  [`51afcd0`](https://github.com/Fre0Grella/getsetmix/commit/51afcd08a8b816779f4637d872d76f435c0b4b35))

GetSetMix bundles or downloads GPL components (mutagen, ffmpeg), so the notices have to travel with
  everything it ships (#28).

- Docker image: LICENSE and THIRD-PARTY-NOTICES.md are copied to /usr/share/doc/getsetmix/. -
  Executables: both files are bundled with --add-data and attached to each GitHub Release as assets.
  - App: GET /licenses and GET /licenses/agpl serve them, and the footer links to them. - Setup and
  the companion: both files are embedded, shown from a Licenses link in Setup's window and by
  gsm-companion licenses.

Refs #28

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.9.0 (2026-11-13)

### Features

- **library**: Index and a read-only list ([#56](https://github.com/Fre0Grella/getsetmix/pull/56),
  [`7013794`](https://github.com/Fre0Grella/getsetmix/commit/7013794cef26608c181570c6a12d3a0846afd792))

First slice of the Library module (#35): the app now knows every audio file under the library root,
  not only the ones it downloaded.

- app/audiohash.py: the audio id, a hash of the audio payload that skips the tags, for MP3, FLAC,
  WAV, AIFF and MP4; a fallback id otherwise. 45 shared fixtures in testdata/audiohash/. -
  app/library.py: the index tables, the first index in resumable batches, the reconcile pass, the
  guard against mass deletes, one rev counter. The worker inserts a row when it places a file. - GET
  /api/library, GET /api/library/status and POST /api/library/rescan. - UI: a switch between
  Downloads and Library and a read-only list with search, in English and Italian. - The first index
  dates each file by its own modification time. - docs/design/library.md records what the
  implementation settled and the measured costs.

Closes #35

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.8.0 (2026-11-13)

### Documentation

- Record cue and ogg/opus decisions ([#54](https://github.com/Fre0Grella/getsetmix/pull/54),
  [`17fbf43`](https://github.com/Fre0Grella/getsetmix/commit/17fbf430d75498e81ee469438333750b5fb42c91))

Two decisions the maintainer took on 2026-11-14:

- Auto cue points leave the roadmap (decision 7 in the architecture log). - Library proposal 16 is
  accepted: the companion skips files Rekordbox cannot import and says so (#31).

Refs #23 Refs #31

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **design**: Add the batch editing design ([#34](https://github.com/Fre0Grella/getsetmix/pull/34),
  [`74313ee`](https://github.com/Fre0Grella/getsetmix/commit/74313ee5dd3234c8d8ed2297b59a547da98223f4))

The design doc for batch tag editing, approved by the maintainer on 2026-11-14.

- Edits on a selection: field operations on title, artist, album, genre, year, comment and cover.
  Only tags change. - Cleanup rules: a fixed menu of twelve parameterised rules saved as ordered
  rule sets; no rule language, no regular expressions. - Every edit is previewed and stored, apply
  writes exactly the stored changes, and applied edits can be undone for 90 days. - Decided in
  review: a featured artist goes into the title, several artists are separated by a comma, and the
  case rule only fixes values written entirely in lower case.

Closes #20

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **design**: Add the library design ([#29](https://github.com/Fre0Grella/getsetmix/pull/29),
  [`436ca2b`](https://github.com/Fre0Grella/getsetmix/commit/436ca2bce1a699a7489974bbf141202b08656711))

docs/design/library.md: the design of the Library module (#11), approved by the maintainer on
  2026-11-14.

- Identity: a hash of the audio payload per container, in Python and Go, kept equal by shared
  fixtures. - Index: one row per file, reconciled with the disk; a guard against mass deletes and a
  24-hour grace time for files that vanish outside GetSetMix. - Editing: one atomic write of title,
  artist, album, genre, year and comment, with an optional check of the old values. - Delete: a
  trash in the library root, restore, purge, tombstones. - Computers: link protocol 2; a changed
  track updates its row in Rekordbox, a deleted one lands in a "removed on server" playlist. - The
  view: a virtualised, paged list for phone and desktop.

Three proposals stay open (16, 17, 18) and are decided before the slice that needs them.

Closes #19 Refs #11

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

- **design**: Undo edits for 30 days ([#44](https://github.com/Fre0Grella/getsetmix/pull/44),
  [`dc38644`](https://github.com/Fre0Grella/getsetmix/commit/dc3864400037f51130e9b74cbd7c32c24f0e910f))

The maintainer shortened the time an applied batch edit can be undone: edit_history_days defaults to
  30 days, not 90.

Refs #20

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk

### Features

- **rules**: Add the cleanup rule catalogue ([#55](https://github.com/Fre0Grella/getsetmix/pull/55),
  [`95740e4`](https://github.com/Fre0Grella/getsetmix/commit/95740e462bfc80c31721bc2f2024eb1eefdb4be3))

First slice of batch tag editing (#46): the cleanup rules as pure functions, with the table of cases
  that is both their documentation and their test. No file is written and no table is added yet.

- app/rules.py: the twelve rules, the tidy pass, a runner for an ordered list of steps, the built-in
  Standard cleanup set. - app/genres.py: the genre list and the one-tap picks move from the UI to
  the server. - GET /api/library/rules: the catalogue, the built-in set, the genre list and the
  picks. - tests/rules_cases.json: 118 cases; a test fails when the design doc's examples and the
  cases drift apart. - Design corrections in docs/design/batch-editing.md: feat. stays lower case in
  the case rule; US, LA, ID and IV leave the default keep list; a list parameter replaces the
  default list.

Closes #46

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01P6dL1rTis43LTgmturVnCk


## v1.7.3 (2026-11-13)

### Bug Fixes

- **worker**: Tag a file before placing it ([#33](https://github.com/Fre0Grella/getsetmix/pull/33),
  [`82ddbc1`](https://github.com/Fre0Grella/getsetmix/commit/82ddbc16531f86f1b0b5ea8b12cdc3c5e0af80b2))

_process moved the download into the library under its final name and only then tagged it. In that
  window /api/link already listed and served the file, and paired computers fetch each path once, so
  they could keep an untagged or half-rewritten copy.

Tag the file in the temporary folder first, then place it. Placing still lands under a hidden name
  and is renamed, so the file only appears complete. A tagging failure now leaves nothing in the
  library.

Closes #30

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>

### Documentation

- Add AGPL-3.0 license and architecture ([#25](https://github.com/Fre0Grella/getsetmix/pull/25),
  [`1a44af5`](https://github.com/Fre0Grella/getsetmix/commit/1a44af5e9f457ca58ce7a5e4aec59ac02091a218))

The repository had no license and no architecture document.

- LICENSE: the AGPL-3.0 text; README and pyproject.toml name it (AGPL-3.0-only). -
  docs/architecture.md: an arc42 overview (goals, constraints, context, strategy, building blocks,
  runtime, deployment, cross-cutting concepts, risks, glossary) with a decision log holding the six
  decisions taken while planning the roadmap: license, commercial-use-only components, where
  analysis runs, audio-hash identity, no renaming in the first Library version, and which roadmap
  features are in and out.

Closes #17 Refs #12

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>

- Add third-party notices ([#32](https://github.com/Fre0Grella/getsetmix/pull/32),
  [`78aef1b`](https://github.com/Fre0Grella/getsetmix/commit/78aef1b4137b11fb8a0dabfc84343124efbfae03))

Follow-up to the license check (#18), for #28.

- THIRD-PARTY-NOTICES.md lists every component GetSetMix ships or downloads, grouped by where it
  ships, with its license and, for the GPL ones (mutagen, each ffmpeg build), where the source is
  offered. The README's License section links to it. - docs/research/licenses.md: the macOS ffmpeg
  build Setup fetches is GPL-3.0-or-later with no non-free parts; madmom bundles its non-commercial
  models, so madmom and all-in-one are "don't use".

Still open on #28: the ffmpeg check inside the Docker image, the Harmonix Set audio terms, and
  shipping the notices in the builds.

Refs #28

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>

- **research**: Check tool licenses ([#26](https://github.com/Fre0Grella/getsetmix/pull/26),
  [`be15e67`](https://github.com/Fre0Grella/getsetmix/commit/be15e6703d89d8777c220e79e16f2b6bdbfcec2b))

Read the license of every tool in issue 18 from its own repository, package metadata or model card.
  Records the verdict for each under AGPL-3.0-only with a paid hosted offering, the findings that
  need a replacement or a way around, and the correction that the MTG models are CC BY-NC-SA 4.0,
  not CC BY-NC-ND.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>

- **research**: Read Rekordbox analysis ([#27](https://github.com/Fre0Grella/getsetmix/pull/27),
  [`00e9191`](https://github.com/Fre0Grella/getsetmix/commit/00e9191e56e6538d32af0226ecbcf25e65a10dc3))

Spike for #21: a read-only pass over a copy of a real Rekordbox library, to see how much analysis
  GetSetMix never has to compute.

- docs/research/rekordbox-read.md: key on 100% of 569 tracks, BPM and beat grid on 96%, phrases on
  72%, vocal data on 11%. Cues live only in master.db; the cue tags in the local analysis files are
  empty. - Verdicts: continue for BPM/key match and sort. Stop for cue points from Rekordbox's
  phrases: on 10 tracks with cues the maintainer vouches for, 64% of the cue positions sit on a
  phrase start and 57% of the phrase starts have no cue. - spikes/rekordbox-read/: the throwaway
  scripts behind the numbers.

Closes #21

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>


## v1.7.2 (2026-11-12)

### Bug Fixes

- **companion**: Avoid Defender trojan heuristics
  ([`8804c33`](https://github.com/Fre0Grella/getsetmix/commit/8804c33d2996083c08678d1144e494b5ad8d030e))

Defender quarantined gsm-companionw.exe as Trojan:Win32/Bearfoos.A!ml (#16). Remove two of the
  signals its machine-learning model reads:

- write shortcuts through the shell's ShellLink COM object in-process instead of spawning PowerShell
  to drive WScript.Shell, with a test that round-trips a real .lnk; - give gsm-companion.exe and
  gsm-companionw.exe an icon, version information and a manifest, as Setup already had, through a
  shared scripts/winres.sh.

Code signing, the main fix, is still open in #16.

Refs #16

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>


## v1.7.1 (2026-10-17)

### Bug Fixes

- **setup**: Picker and Tailscale ingress ([#15](https://github.com/Fre0Grella/getsetmix/pull/15),
  [`7ccb935`](https://github.com/Fre0Grella/getsetmix/commit/7ccb93522697508ebd9fbcf911e68f29369fba80))

* fix(setup): open the folder dialog in front

Clicking Change… did nothing visible: the folder dialog opened behind Setup's window. Windows
  doesn't let a background process bring a window forward, and the dialog's owner form was never
  shown, so the dialog was neither topmost nor in front.

Show a 1-pixel invisible, topmost owner first; the dialog then opens topmost. PowerShell now starts
  without a console but not "hidden", which would have applied to that owner. Checked on a real
  Setup window with Edge in front: before, topmost=False; after, topmost=True. macOS gets `activate`
  before `choose folder` (untested there).

If the dialog fails anyway, Setup now says so and points to the text box, instead of silently doing
  nothing.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

* fix(setup): find an ingress's default backend

Adopting a GetSetMix reached only through a Tailscale ingress asked for the address by hand: such an
  ingress usually has no rules, just `defaultBackend` pointing at the service and a ts.net name in
  its status, and the bootstrap only read backends from the rules.

Read `defaultBackend` too. The bootstrap regression test now runs against a fake kubectl with
  exactly that ingress, as found on a real homelab.

* fix(setup): drop the trailing dot from addresses

Kubernetes reports a Tailscale ingress's name fully qualified, "x.ts.net.". Setup used it as the
  server's address: the companion was fine (Go drops the dot), but the Done screen's Open button and
  the QR code sent the dot on to the browser, whose TLS handshake for the dotted name fails with
  ERR_SSL_PROTOCOL_ERROR.

Trim it from the host names the bootstrap reports, and from an address typed by hand.

---------

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.7.0 (2026-10-17)

### Continuous Integration

- Lint PR titles before squash merges ([#13](https://github.com/Fre0Grella/getsetmix/pull/13),
  [`d91fa3c`](https://github.com/Fre0Grella/getsetmix/commit/d91fa3c82596491f27f3480a04f69b9cfe663e8a))

A squash merge makes the PR title the commit headline on main, but the commit check only saw the
  branch's own commits. PR #10's title, "feat(setup): GetSetMix Setup installer", passed review and
  then failed commitlint on main (subject-case: it starts with capitalised words).

Lint the title on every PR, including when it is renamed, with the same config, and fail when
  "<title> (#N)" passes 50 characters.

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>

### Features

- **ui**: Add the FreoGrella footer ([#14](https://github.com/Fre0Grella/getsetmix/pull/14),
  [`2c73785`](https://github.com/Fre0Grella/getsetmix/commit/2c73785dd2c9f2bf5436a58103bf95486dd7e256))

The same thin footer as BottleCount and Treblewise, in the app and on both pages of the website: the
  year, GetSetMix, the source and the docs on the left; "Made with ❤️ by FreoGrella", GitHub,
  LinkedIn and Donate (in the accent) on the right. It wraps into two rows on a phone.

In the app it closes the page, after the list, and keeps the bottom bar's height free below itself
  so the bar never covers it; the page is a column now, so the footer stays at the bottom even when
  the list is short. The labels are in English and Italian.

On the site it replaces the old footer, whose "open source, MIT" isn't backed by a LICENSE file yet;
  the rights notice moves just above it.

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.6.0 (2026-10-17)

### Features

- **setup**: Getsetmix Setup installer ([#10](https://github.com/Fre0Grella/getsetmix/pull/10),
  [`4a22193`](https://github.com/Fre0Grella/getsetmix/commit/4a221931718ff6280c0fc4930bad3acd427ff8c3))

* feat(link): serve finished tracks to paired PCs

A computer paired by GetSetMix Setup can now download the library's finished tracks itself, so a
  home server no longer needs Nextcloud or Syncthing to get them to the computer that runs
  Rekordbox.

- GET /api/link/files lists the audio files under the library root as library-relative paths (size,
  mtime); GET /api/link/file?path= serves one. Hidden and .part files, other file types and paths
  that escape the root are refused. - Each computer has its own token, one per line in
  DATA_DIR/link-tokens (or GSM_LINK_TOKEN). The file is read per request, so pairing needs no
  restart. These tokens open only /api/link, and the UI's token never opens /api/link. - The worker
  lands a track under a hidden .part name and renames it, so a download can't catch half a file even
  when the move is a copy.

It is one way: nothing a computer does through /api/link changes the server's library, which stays
  the full copy and the backup.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

* feat(setup): add the GetSetMix Setup installer

One download (Windows .exe, macOS .app) that asks where GetSetMix should run and installs it, built
  for people who don't want to touch a terminal more than once. It is the companion itself: opened
  with no arguments it shows Setup, then copies itself into place.

Just this computer - Downloads the app from the matching release plus ffmpeg and Deno, pinned by
  SHA-256; adds a GetSetMix shortcut that opens the app in a browser's app mode (run_local.py
  --window), which stops GetSetMix when the window closes.

With my home server - Shows one command to paste on the server. Its bootstrap reports what the
  server has (Docker, Kubernetes/MicroK8s/k3s, an existing GetSetMix, Tailscale, disks) back to
  Setup and waits; Setup answers with a plain shell script generated and validated in Go
  (internal/serverscript) that installs GetSetMix on Docker (with Watchtower) or Kubernetes (with
  Keel 0.20.0, vendored), or adopts the install already there: Recreate strategy, imagePullPolicy
  Always, Keel annotations, one restart. Each step reports back to the window. - Optional HTTPS
  through `tailscale serve`, which the phone needs to install the PWA; the done screen says so
  plainly when it's missing. - Pairs this computer (a token in link-tokens), finds the address that
  answers, and sets up the companion: tracks download one way into a local folder with
  `gsm-companion fetch`, every 15 minutes (Task Scheduler / launchd) and before Rekordbox starts,
  then import. A server folder already synced by Nextcloud/Syncthing can be watched instead.

The window is a local page on 127.0.0.1 behind a per-run key, in Edge or Chrome app mode with a
  seeded profile (no sign-in or translate bubbles, no background mode, so closing it ends Setup).
  The network listener for the server opens only for the home-server path.

CI builds Setup on every PR as an artifact; releases attach it.

* docs: install GetSetMix with Setup

Lead the README with GetSetMix Setup: the two ways to run GetSetMix, the one command for a home
  server, one-way delivery as the backup, and why the phone needs HTTPS. Document `fetch` and the
  wizard in the companion README, and add screenshots of Setup.

* fix(setup): keep an adopted install's own address

Adopting a GetSetMix on Kubernetes read the ports and host names of every Service and Ingress in its
  namespace. When it shares one with other apps (say, Nextcloud), Setup could take Nextcloud's
  NodePort as GetSetMix's and offer to publish it with `tailscale serve`.

Only Services named after GetSetMix (or its deployment), and the Ingresses that route to them, count
  now; a test runs the real bootstrap against a fake kubectl with Nextcloud next door. An adopted
  install that already has a host name keeps it: Setup no longer offers Tailscale for it.

* fix(companion): fetch on battery too

`schtasks /SC MINUTE` tasks never start on battery and stop when the cable comes out, so a DJ's
  unplugged laptop would never have fetched. Register the task from XML instead: runs on battery,
  catches up after sleep, waits for the network and never overlaps itself. It now sits at the top
  level of Task Scheduler, so uninstalling leaves no empty folder.

An opt-in test (GSM_TEST_SCHTASKS=1) registers a real task, checks those settings and deletes it.

* docs: say how to try a Setup build before release

* docs(site): lead with GetSetMix Setup

The home page's deploy section becomes "One download, one question": Just this computer, With my
  home server (with the command Setup shows) and By hand. The docs get a GetSetMix Setup section and
  a home-server walkthrough (pairing, adoption, one-way delivery as the backup, why the phone needs
  HTTPS), and the Rekordbox section starts from the companion instead of the XML.

* docs: rewrite the README's opening

Lead with what GetSetMix does, in one line, with the download, the docs and screenshots of the app
  on a computer and a phone (made-up tracks, drawn covers). Then four steps for how it works, and
  the feature list grouped by stage instead of one long list. The logo is the vector mark, which
  follows GitHub's light or dark theme.

* docs: open with the problem GetSetMix solves

Getting a track you heard into Rekordbox used to mean a later session at the computer: find it
  again, download, tag, import. Say that first, and that GetSetMix removes it: share the link from
  your phone when you hear it, and it's downloaded, tagged and in Rekordbox by the time you play.
  "How it works" now follows that moment, from the share sheet to opening Rekordbox; the website's
  hero says the same.

* docs: tell the story as Get, Set, Mix

The name already is the flow, like a sprinter's "get set, go": GET the track the moment you hear it
  (Share > GetSetMix from YouTube or SoundCloud), SET the tags with one thumb, MIX it when you play,
  already downloaded and in Rekordbox.

- A three-panel picture of that flow on a running track: the phone's share menu (drawn, no
  third-party UI), the real app right after a share, and the playlist waiting on the computer
  (drawn). It leads the README and the website's flow section. - README: tagline, "How it works" and
  the feature groups follow Get / Set / Mix, with Share to GetSetMix first; app screenshots move to
  Features. - Website: "Get. Set. Mix." hero with the real phone screen instead of the old desktop
  mock-up, and no docker command in the hero.

---------

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>


## v1.5.0 (2026-10-17)

### Features

- **ui**: Mobile-first layout and theme switch
  ([`19e0985`](https://github.com/Fre0Grella/getsetmix/commit/19e0985dc595fda86816bc958ac207013d65e8e7))

The UI is now designed for the phone first, since that is where links arrive (share sheet or
  clipboard) and where most edits happen:

- Adding and downloading live in a bottom deck within thumb reach, with the batch progress on top of
  it. On wide screens it becomes a transport bar. - Rows are compact on a phone (cover, title,
  artist, genre, state and the one action that moves the track on). Tapping a row opens it with
  full-size fields, labels, every action, and one-tap genre picks (genres already used in the list
  first). Fields in a compact row don't take taps, so opening a row never throws up the keyboard. -
  Inputs are 16px or more, so iOS no longer zooms in on focus. Tap targets are 44px. The deck steps
  aside while a row field is being edited, and interactive-widget=resizes-content keeps it above the
  Android keyboard. - Settings is a full-screen sheet on a phone and stays a side panel on a
  computer. From 721px the Rekordbox-style columns are unchanged.

Theme: Auto, Light or Dark in Settings > Interface. It applies at once and is stored per device in
  localStorage, so a phone can be dark while the desktop follows the system. An inline script
  applies it before first paint, and the theme-color meta (Android status bar) follows the choice.

Logo: the header and app icons were raster cut-outs with chewed edges and a halo around the speed
  dashes. They are replaced by the vector redraw from the wizard branch (icon.svg,
  icon-maskable.svg, mark.svg), recoloured from teal to the master logo's blue to match the UI
  accent. The header mark is inline, so its figure follows the theme. Rasters come from
  scripts/build_icons.py (Playwright), which replaces fix_icon.py; the Pages site uses the same
  assets.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV


## v1.4.0 (2026-10-17)

### Continuous Integration

- **companion**: Test and release Windows and macOS
  ([`6acb179`](https://github.com/Fre0Grella/getsetmix/commit/6acb179ffec467eb0932597194d87fa02714dcf9))

Tests run on Windows (cgo through MSYS2 UCRT64 gcc), macOS and Linux. Releases are automated from
  companion/VERSION: a push to main whose VERSION has no companion-vX.Y.Z tag yet builds a static
  Windows pair (gsm-companion.exe + the windowless gsm-companionw.exe) and a universal macOS binary,
  then publishes the release with SHA256SUMS. Pushing a companion-v* tag releases that commit, as a
  pre-release when the version has a suffix. The prefix keeps these tags apart from the server's
  semantic-release vX.Y.Z tags, and make_latest stays false so the server remains the repo's latest
  release.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Documentation

- Point to the companion from the README
  ([`99ff140`](https://github.com/Fre0Grella/getsetmix/commit/99ff1407f0a7a51d343917ffab14ce1de58b6109))

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

- **deploy**: Plan auto-update with Keel
  ([`58c2d29`](https://github.com/Fre0Grella/getsetmix/commit/58c2d29f28956923869570dc3cc6d12774097d79))

Handoff for the session that sets up self-updating on the home server: Keel polls GHCR and rolls the
  deployment whenever the digest behind :latest changes, so pushes to main and the weekly yt-dlp
  refresh both reach the server without a manual rollout. Covers the checks to run against the live
  deployment first (it lives in namespace nextcloud, not the repo manifest's getsetmix), install,
  verification, rollback, and the release-only variant.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Features

- **companion**: Import deliveries into Rekordbox
  ([`20a69ba`](https://github.com/Fre0Grella/getsetmix/commit/20a69babc404b087972bd274c006797de7e5bd4d))

gsm-companion runs on the DJ's computer and adds the tracks a sync client delivers straight into
  Rekordbox's collection (master.db), into a "GetSetMix" playlist. No XML source to refresh, no drag
  and drop.

Rekordbox must be closed while its database is written, so nothing has to stay resident: the default
  "Rekordbox (GetSetMix)" launcher imports (about 1 s, 0.1 s when nothing is new) and then starts
  Rekordbox. Unattended imports are opt-in: on Windows a watcher that sleeps on
  ReadDirectoryChangesW and on the Rekordbox process handle (about 10 MB, 0% CPU idle); on macOS a
  launchd agent with WatchPaths, so nothing of ours runs between changes.

Safety: - never writes while Rekordbox runs (checked before reading and again before writing); opens
  nothing unless a file is new; - backs up master.db and masterPlaylists6.xml, writes in one
  transaction, runs quick_check, and restores the backup on failure; - remembers handled files, so a
  track deleted in Rekordbox stays deleted; files still syncing (temp names, conflicts, modified in
  the last 10 s) are left alone.

Rows mirror Rekordbox's own, checked against a real 7.2 library rather than copied from pyrekordbox:
  the local device from djmdProperty (not the first djmdDevice), ContentLink from the latest local
  import, rb_file_id = NTFS file ID / inode, UTC "…mmm +00:00" timestamps, localUpdateCount and
  per-row rb_local_usn, and the playlist mirrored into masterPlaylists6.xml without reformatting it.
  Stream facts are parsed from MP3/FLAC/WAV/AIFF/MP4 headers; on 514 real tracks they match what
  Rekordbox stored (file ID, rate, depth, type 514/514, length 513, bitrate 510). An end-to-end run
  on a copy of that library reads back cleanly with pyrekordbox and passes integrity_check.

Go with SQLCipher compiled in (go-sqlcipher, no OpenSSL): one ~5 MB static binary per platform.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Testing

- **companion**: Build test paths natively per OS
  ([`a4fe23f`](https://github.com/Fre0Grella/getsetmix/commit/a4fe23fa7d996cc5b35264fe32caf799681881c2))

Two library tests spelled Windows paths with backslashes, which are ordinary filename characters on
  macOS and Linux, so CI failed there. Build them with filepath.FromSlash instead.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV


## v1.3.0 (2026-10-17)

### Bug Fixes

- **ytdlp**: Bundle Deno and keep yt-dlp fresh
  ([`4d1e743`](https://github.com/Fre0Grella/getsetmix/commit/4d1e74369ee4442926b845edf28a271beacee13a))

YouTube now serves media only to clients that solve its JavaScript challenges. yt-dlp does that with
  an external JS runtime plus the yt-dlp-ejs scripts; the image had neither and a months-old yt-dlp,
  so metadata resolved through a fallback client while every download died with "HTTP Error 403:
  Forbidden".

- Dockerfile: copy a pinned Deno (bin-2.9.3, amd64 + arm64) and install yt-dlp[default], which
  brings yt-dlp-ejs; the build fails fast if either is missing. - Weekly scheduled image rebuild. CI
  resolves the newest yt-dlp from PyPI and passes it as YTDLP_VERSION, which busts the cached pip
  layer (a plain rebuild would reuse the stale install from the GHA cache). - app/ytdl.py: one place
  that builds YoutubeDL options, enabling whichever supported runtime is installed (deno, node,
  quickjs, bun), so local mode works with Node too. - 403s now carry the fix ("install Deno…")
  instead of a bare error, GET /api/status reports yt-dlp age and runtime, and the UI shows a banner
  when downloads are bound to fail. - PyInstaller builds collect yt_dlp_ejs; k8s pulls :latest
  always. - CI pins ruff to the pre-commit version (newer releases widen the default rule set and
  would fail lint with no code change) and runs node --check on the UI scripts, which have no build
  step to catch a syntax error.

Verified with a real YouTube download inside the built image: yt-dlp reports "JS runtimes:
  deno-2.9.3" and writes the MP3, no 403.

Closes #9

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV

### Features

- **ui**: Redesign as a track browser
  ([`8a70ae4`](https://github.com/Fre0Grella/getsetmix/commit/8a70ae468ac12630cc8da8499bda85eb53d21ffc))

The list is now laid out like Rekordbox's own browser instead of a stack of floating cards: dense
  rows under column headers (track, album, genre, time, status), artwork kept 16:9, and fields that
  read as plain text until hovered or focused, so editing metadata is in place.

- A real link field in the top bar: Enter adds, pasting a link adds it at once, and Ctrl+V anywhere
  on the page works too. With the field empty, Add reads the clipboard; no more prompt() fallback. -
  Status is one cell per row (dot + label: ready, queued, %, writing tags, in your library, error)
  with only the actions that apply; yt-dlp's "ERROR:" prefix is trimmed, the full text is the
  tooltip. - Settings is a grouped side panel (downloads, library and Rekordbox, interface,
  housekeeping) that leaves the list in view. It opens at once and stays inert until its values
  load, so neither Escape nor a fast Save can race the fetch (a Save could have written an empty
  library folder). - Follows the system theme, both designed: OKLCH neutrals tinted toward the
  logo's navy, the logo's "mix" blue as the only accent. - Phones: the Download action moves to a
  bottom dock within thumb reach, rows wrap album and genre onto a second line. - Copy rewritten in
  both languages (EN/IT keys kept in parity), without em dashes; picker emoji replaced with the UI's
  icons.

Every DOM id app.js binds to is kept; the share-target flow is unchanged. Checked in Chrome at 1280
  and 390 px, dark and light, with every row state, and by driving the real flows (add by Enter,
  paste anywhere, inline edit persisted, settings save + language switch, Escape, cover search).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01XFY6vYvZ9nsAYS2hfXqHHV


## v1.2.1 (2026-07-05)

### Bug Fixes

- **ui**: Fix genre textbox flickering
  ([`1a4a8ac`](https://github.com/Fre0Grella/getsetmix/commit/1a4a8ac3ff0aabe26fc1086a99c018c18d141073))

### Continuous Integration

- Scope release asset download to executables
  ([`7f02307`](https://github.com/Fre0Grella/getsetmix/commit/7f023076a6e8c47652c252f19f84e10f834c27ab))

The attach job downloaded all run artifacts, which now includes the buildx .dockerbuild artifact
  from the image job, causing the download to fail. Filter to getsetmix-* so only the executables
  are pulled and attached.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

- Use .mjs commitlint config required by commitlint-github-action
  ([`d6c663c`](https://github.com/Fre0Grella/getsetmix/commit/d6c663c8b06bb99f4df6f77153c9dee9ae2f7ab3))

wagoid/commitlint-github-action v6 rejects a .js configFile with ".js extension is not allowed for
  the configFile, please use .mjs instead", which made the Commit lint job red on every push.
  Convert the config to an ESM commitlint.config.mjs and point the workflow at it.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>


## v1.2.0 (2026-06-16)

### Chores

- Trigger release pipeline
  ([`06f9ad1`](https://github.com/Fre0Grella/getsetmix/commit/06f9ad19aba4252cb12e35704334bbdb6bac3309))

### Continuous Integration

- Automate semantic versioning and enforce Conventional Commits
  ([`345c1de`](https://github.com/Fre0Grella/getsetmix/commit/345c1de230fc86621f07e0e2e4740ce4b1069c3e))

Releases are now driven by Conventional Commits on main instead of manual tags.
  python-semantic-release reads the commit history and bumps the version (fix -> patch, feat ->
  minor, breaking -> major), tags vX.Y.Z, creates the GitHub Release, and builds the executables +
  versioned images in one run.

- pyproject.toml: python-semantic-release config; single version source in app/__init__.py
  (__version__), wired into FastAPI - release.yml: consolidated version -> executables -> versioned
  images, no PAT needed (self-contained run; release commit carries [skip ci]) - docker-publish.yml:
  now main-only (latest/main/sha); versioned tags moved to release.yml - commitlint.yml +
  commitlint.config.js + .pre-commit-config.yaml: make Conventional Commits mandatory in CI and
  locally (commit-msg hook) - docs + test for the version wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

- Sign semantic-release commits to satisfy signed-commit protection
  ([`281a846`](https://github.com/Fre0Grella/getsetmix/commit/281a8463975eee28ff0cf1e3ee2f67d6098f7562))

main has branch protection requiring verified signatures, which rejected the release bot's unsigned
  version-bump push. Configure python-semantic-release to SSH-sign its commit using a signing key on
  the owner account, supplied via the SSH_SIGNING_PRIVATE_KEY / SSH_SIGNING_PUBLIC_KEY repo secrets.
  Setup steps added to the README.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

### Features

- Share to GetSetMix from YouTube/SoundCloud via PWA share target
  ([`1496657`](https://github.com/Fre0Grella/getsetmix/commit/1496657ac357e48623378ac93484b864fa180b53))

Make GetSetMix installable as a PWA with a Web Share Target so a track can be shared straight from
  the YouTube/SoundCloud Android share sheet: the link is fetched and lands staged in the existing
  review/download UI.

- main.py: serve /manifest.webmanifest, /sw.js, and the /share landing - manifest + minimal
  (no-cache) service worker; 192/512 maskable icons generated by scripts/fix_icon.py - app.js:
  register SW, consumeShare() extracts the first URL from the shared text and reuses the paste flow;
  new row scrolls into view and flashes - k8s: TLS Ingress example (HTTPS is required for PWA
  install) - docs + tests for the new routes

Android only -- iOS Safari has no Web Share Target API.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>


## v1.1.1 (2026-06-10)

### Bug Fixes

- Upgrade mobile ui
  ([`51d7aa9`](https://github.com/Fre0Grella/getsetmix/commit/51d7aa98a73605b7ce66401a88c9d8a4e0e1d810))


## v1.1.0 (2026-06-10)

### Features

- Duplicate now are showed in the main view by a warning badge,
  ([`cddd4c6`](https://github.com/Fre0Grella/getsetmix/commit/cddd4c6880c26409bf9960263be55eb1b10121eb))


## v1.0.0 (2026-06-10)

### Bug Fixes

- Add proper .gitignore
  ([`7aec5c3`](https://github.com/Fre0Grella/getsetmix/commit/7aec5c3b51fd77e73bb580d52926ff59d55c2115))

- Fix deployment name for container
  ([`e7754d0`](https://github.com/Fre0Grella/getsetmix/commit/e7754d03ca18d0486ebcd73406b851b2219a7d8c))

- Remove placeholders
  ([`35789bb`](https://github.com/Fre0Grella/getsetmix/commit/35789bb0423fd9f7b8a45a28ece5775c732b578e))

### Chores

- Add a development mode
  ([`b79a012`](https://github.com/Fre0Grella/getsetmix/commit/b79a0125d4caf5bf6d72606c8adbd18817373e7b))

- Add deployement manifest for k8s
  ([`6f5e647`](https://github.com/Fre0Grella/getsetmix/commit/6f5e6477babf277a595953ddc73b6db8bb74f4fe))

### Continuous Integration

- Add gh pages and some ci/cd
  ([`4b6d220`](https://github.com/Fre0Grella/getsetmix/commit/4b6d2204d67d0b1a23c9ede79d48cde6240ccceb))

- Setup ci/cd and add a build system
  ([`65fe4d9`](https://github.com/Fre0Grella/getsetmix/commit/65fe4d9c0833e3e13febe2002c4df8c6c0426895))

### Documentation

- Add a product documentation
  ([`bacd534`](https://github.com/Fre0Grella/getsetmix/commit/bacd534978a75aa6487197a744b97f8e5808e6f4))

- Add concept ui
  ([`8b8a0db`](https://github.com/Fre0Grella/getsetmix/commit/8b8a0db27d1b4fca8b2118935ac650a7e015e240))

- Adding design concept
  ([`d1b7033`](https://github.com/Fre0Grella/getsetmix/commit/d1b7033ce12ac6b2d65ad878dc7cc365d4e6d6cd))

- Improve architecture design
  ([`58a4548`](https://github.com/Fre0Grella/getsetmix/commit/58a45485803e81c5d50bbe1ce048c5d0146a13fa))

- Initialize context
  ([`a17918c`](https://github.com/Fre0Grella/getsetmix/commit/a17918cdb1a55311e770f8b21eb99efcc1914b81))

- Updated architectural design choices
  ([`a3898e8`](https://github.com/Fre0Grella/getsetmix/commit/a3898e80e3705fe1d5f8cd13f8a2d56aad7975a1))

### Features

- Add service orchestration for api and state
  ([`88dd11d`](https://github.com/Fre0Grella/getsetmix/commit/88dd11dbd6e84b4597eebb6a9c531612ddc4fced))

- Add staging ui
  ([`a7a3cab`](https://github.com/Fre0Grella/getsetmix/commit/a7a3cab0da70df7a3abf0908364c82338b621727))

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>

- Add the python adapter runtime
  ([`1ce7815`](https://github.com/Fre0Grella/getsetmix/commit/1ce7815fa26bff1d36f883fe07f8da8d28a070fc))

- All done, good job fable
  ([`8575d53`](https://github.com/Fre0Grella/getsetmix/commit/8575d533839464b85f42dee0d9111ca4f286d707))

- Collection-aware inbox, path picker, EN default, exe releases, UI fixes
  ([`c50582b`](https://github.com/Fre0Grella/getsetmix/commit/c50582ba519d001eec244490455ae65de1d9a419))

- brand icon: black square removed (transparent bg), new light variant for dark surfaces, favicons
  regenerated (scripts/fix_icon.py) - GH pages mock translated to English; English is now the
  default UI language and the GSM_LANGUAGE default everywhere - new optional "Rekordbox collection
  XML" setting (GSM_COLLECTION_XML_PATH): before each batch, tracks already imported into the full
  collection are purged from the inbox XML (matched by file location, title+artist fallback) -
  server-side path picker (GET /api/fs/list) with Browse buttons for the library folder and both XML
  paths - track rows no longer squash when many links/playlists are added (flex: none) - improved
  mobile layout: touch targets, bottom-sheet modals, 16px inputs, always-visible cover button on
  touch screens - release.yml builds standalone executables (Windows/macOS/Linux, PyInstaller) on
  v*.*.* tags; frozen builds keep their data in ~/.getsetmix

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

### Refactoring

- Cleaning up for fable
  ([`77a222f`](https://github.com/Fre0Grella/getsetmix/commit/77a222f890ff2df74ce9d4ab2e3c8e91fe166373))
