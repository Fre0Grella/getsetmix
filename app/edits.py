"""Batch editing: the tags of many tracks, previewed, stored, then applied
(docs/design/batch-editing.md, 3.5, 3.6, 4.3 and 4.4).

An edit is a selection of Library files and an ordered list of steps, rules
and field operations, which app/rules.py runs. Making an edit reads only the
index: for each track it runs the steps and stores one change per field that
would differ, with the old value, the new one and the steps that made it.
Nothing is written then.

Applying writes exactly what was stored, never running the steps again: one
file at a time, all of its changes in one write through the Library, with the
stored old values as the write's precondition. A file changed since the
preview is a `conflict` and is not written; any other failure fails that file
only, and applying again retries only what failed. One edit applies at a
time; previews can be made meanwhile. An edit cut short by a restart is
`interrupted`, and applying it again carries on.

Undo is a new edit (design 4.7) that writes the old values back through the
same job and the same precondition with the roles swapped, so a field changed
again since is a `conflict` and never overwritten. The changes of an applied
edit are kept `edit_history_days`; then its line stays in the history with
its counts, and it can no longer be undone. An unused preview goes after 24
hours. The purge runs at most once a day, when the edits are used.
"""
from __future__ import annotations

import base64
import errno
import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime

from . import config, library, rules, tagger
from . import db as dbmod
from .library import LibraryError

log = logging.getLogger("getsetmix.edits")

FIELDS = tagger.EDIT_FIELDS
MAX_LENGTH = 255            # the width of Rekordbox's columns
PREVIEW_SECONDS = 24 * 3600  # an unused preview expires
WARNINGS = ("would_empty", "merges_values", "not_in_genre_list", "too_long")
BLOCKING = ("would_empty", "too_long")
CHANGE_STATES = ("pending", "excluded", "blocked", "applied", "failed", "conflict", "undone")
TO_WRITE = ("pending", "failed")
APPLIABLE = ("preview", "applied", "cancelled", "interrupted")
FINISHED = ("applied", "cancelled", "interrupted")   # in the history; may be undone
UNUSED = ("preview", "expired", "discarded")          # never applied: purged after a day
DAY = 24 * 3600
# Why a selected track takes no part (design 3.3).
SKIPPED_STATE = {"trashed": "in the trash", "missing": "not on disk", "gone": "not in the library"}
# How a failed write is named in a change's error (design 4.4).
FAILURE = {410: "gone", 404: "gone", 409: "read-only", 423: "in use"}
# The status a skipped track answers with in a bulk request.
SKIP_STATUS = {"no such track": 404, "in the trash": 410, "not on disk": 410,
               "not in the library": 410, "read-only format": 409, "damaged file": 409}


def _encode(value) -> str | None:
    return None if value is None else str(value)


def _decode(field: str, text: str | None):
    if field == "year":
        return None if text is None else int(text)
    return text or ""


def _cursor(cursor: str) -> int:
    try:
        return int(json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))["i"])
    except Exception:
        raise LibraryError(400, "cursor does not belong to this list") from None


def _next(last_id: int) -> str:
    raw = json.dumps({"i": last_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


FILTER_KEYS = ("q", "genre", "folder")   # as GET /api/library takes them


def _filter(raw) -> dict[str, str]:
    if not isinstance(raw, dict) or set(raw) - set(FILTER_KEYS) or \
            not all(isinstance(v, str) for v in raw.values()):
        raise LibraryError(400, "filter takes q, genre and folder, as text")
    return raw


def _steps(raw) -> list[dict]:
    """The steps, checked once before any track: 400 names what is wrong."""
    if not isinstance(raw, list) or not raw:
        raise LibraryError(400, "steps must be a non-empty list")
    for step in raw:
        if isinstance(step, dict) and step.get("op") == "set" and step.get("field") in FIELDS:
            library.check_fields({step["field"]: step.get("value")})  # the year's range
    try:
        rules.run_steps({f: None if f == "year" else "" for f in FIELDS}, raw)
    except rules.RuleError as exc:
        raise LibraryError(400, str(exc)) from None
    return raw


def _label(steps: list[dict]) -> str:
    """What the history calls an edit: its steps in short."""
    parts = [f"{s['field']} = {'' if s.get('value') is None else s['value']}" if "op" in s
             else s["rule"] for s in steps]
    return "; ".join(parts)[:200]


def _warnings(field: str, new, multi: set[str]) -> list[str]:
    out = []
    if field in ("title", "artist") and not str(new or "").strip():
        out.append("would_empty")
    if field in multi:
        out.append("merges_values")
    if isinstance(new, str) and len(new) > MAX_LENGTH:
        out.append("too_long")
    return out


class Edits:
    """The edits over one Library and its database."""

    def __init__(self, database, lib: library.Library,
                 clock: Callable[[], float] = time.time,
                 history_days: Callable[[], int] | None = None) -> None:
        self.db = database
        self.lib = lib
        self.clock = clock
        self.history_days = history_days or (lambda: int(config.settings["edit_history_days"]))
        self._purged_at: float | None = None
        self._starting = threading.Lock()   # two applies never both start
        self._idle = threading.Event()
        self._idle.set()
        self._current: dict[int, str] = {}  # edit id -> the file being written

    def recover(self) -> int:
        """At startup: an edit left `applying` by a stop is `interrupted`."""
        with self.db.transaction() as conn:
            return conn.execute("UPDATE edits SET state = 'interrupted' "
                                "WHERE state = 'applying'").rowcount

    def wait(self, timeout: float | None = None) -> bool:
        """Until no edit is being applied; False on timeout."""
        return self._idle.wait(timeout)

    # ----------------------------------------------------------- preview
    def preview(self, body) -> dict:
        """Make and store a preview (design 4.3). Raises LibraryError: 400 a
        request that is not valid, 413 too many tracks."""
        if not isinstance(body, dict):
            raise LibraryError(400, "the edit must be an object")
        ids = self._selection(body.get("selection"))
        eid, skipped_by_id, unchanged = self._store(ids, _steps(body.get("steps")))
        skipped: dict[str, int] = {}
        for why in skipped_by_id.values():
            skipped[why] = skipped.get(why, 0) + 1
        out = self.get(eid)
        assert out is not None
        out["counts"].update(selected=len(ids), unchanged=len(unchanged),
                             skipped=len(skipped_by_id), skipped_by_reason=skipped)
        return out

    def _selection(self, raw) -> list[int]:
        """The tracks of a selection, frozen now (design 3.3): the ids given,
        or every present track a filter of the Library list matches. A filter
        that matches nothing is an empty selection, not an error."""
        if isinstance(raw, dict) and "filter" in raw:
            found = [r["id"] for r in self.lib.select(**_filter(raw["filter"]))]
            if len(found) > library.MAX_SELECTION:
                raise LibraryError(413, f"at most {library.MAX_SELECTION} tracks at once")
            return found
        if not isinstance(raw, dict) or "ids" not in raw:
            raise LibraryError(400, "selection must hold the track ids or a filter")
        return library.check_ids(raw["ids"])

    def _store(self, ids: list[int], steps: list[dict]) -> tuple[int, dict[int, str], list[int]]:
        """Run the steps over the index and store the preview: its id, the
        tracks left out with why, and the tracks the steps leave as they are."""
        rows = self._rows(ids)
        skipped: dict[int, str] = {}
        unchanged: list[int] = []
        changes = []
        for fid in ids:
            row = rows.get(fid)
            why = self._skip(row)
            if why:
                skipped[fid] = why
                continue
            assert row is not None
            before = {f: row[f] for f in FIELDS}
            result = rules.run_steps(before, steps)
            differ = [f for f in FIELDS if result.fields[f] != before[f]]
            if not differ:
                unchanged.append(fid)
                continue
            multi = set(row["multi"].split(","))
            for f in differ:
                warnings = _warnings(f, result.fields[f], multi)
                state = "blocked" if set(warnings) & set(BLOCKING) else "pending"
                changes.append((fid, row["audio_id"], f, _encode(before[f]),
                                _encode(result.fields[f]), json.dumps(result.by.get(f, [])),
                                json.dumps(warnings), state))
        rev = self.lib.rev()
        with self.db.transaction() as conn:
            eid = conn.execute(
                "INSERT INTO edits (state, label, selection, steps, catalogue, library_rev, "
                "created_at) VALUES ('preview', ?, ?, ?, ?, ?, ?)",
                (_label(steps), json.dumps({"ids": ids}), json.dumps(steps),
                 rules.CATALOGUE_VERSION, rev, dbmod.iso(self.clock()))).lastrowid
            conn.executemany(
                "INSERT INTO edit_changes (edit_id, file_id, audio_id, field, old_value, "
                "new_value, by, warnings, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(eid, *c) for c in changes])
        assert eid is not None
        return eid, skipped, unchanged

    def at_once(self, ids, steps) -> dict:
        """Preview and apply in one call, and wait for the end: the Library's
        bulk `set_genre` (library design 3.3, L9), so it is journalled and can
        be undone. The answer is the bulk one: `{"done": [ids], "failed":
        [{"id", "status", "detail"}]}`, each id once in the order given.
        Raises LibraryError like preview and apply."""
        ids = library.check_ids(ids)
        eid, skipped, _ = self._store(ids, _steps(steps))
        failed = {fid: (SKIP_STATUS.get(why, 409), why) for fid, why in skipped.items()}
        with self.db.transaction() as conn:
            pending = conn.execute("SELECT 1 FROM edit_changes WHERE edit_id = ? "
                                   "AND state = 'pending'", (eid,)).fetchone()
        if pending:
            self.apply(eid)
            self.wait()
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT file_id, state, error FROM edit_changes "
                                "WHERE edit_id = ? AND state <> 'applied'", (eid,)).fetchall()
        for r in rows:
            reason = r["error"].split(":", 1)[0]
            status = 412 if r["state"] == "conflict" else 400 if r["state"] == "blocked" else \
                next((s for s, name in FAILURE.items() if name == reason), 500)
            failed.setdefault(r["file_id"], (status, r["error"] or r["state"]))
        return {"done": [fid for fid in ids if fid not in failed],
                "failed": [{"id": fid, "status": failed[fid][0], "detail": failed[fid][1]}
                           for fid in ids if fid in failed]}

    def _rows(self, ids: list[int]) -> dict[int, dict]:
        found: dict[int, dict] = {}
        with self.db.transaction() as conn:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ", ".join("?" for _ in chunk)
                for r in conn.execute(f"SELECT * FROM library_files WHERE id IN ({marks})", chunk):
                    found[r["id"]] = dict(r)
        return found

    def _skip(self, row: dict | None) -> str | None:
        if row is None:
            return "no such track"
        if row["state"] != "present":
            return SKIPPED_STATE.get(row["state"], row["state"])
        if not self.lib.editable(row["format"], row["audio_id"]):
            return "damaged file" if row["format"] in tagger.EDITABLE_FORMATS else "read-only format"
        return None

    # ------------------------------------------------------------- reads
    def get(self, eid: int) -> dict | None:
        """One edit: its state, its counts and the progress of its apply."""
        with self.db.transaction() as conn:
            e = conn.execute("SELECT * FROM edits WHERE id = ?", (eid,)).fetchone()
            if e is None:
                return None
            rows = conn.execute("SELECT file_id, field, state, warnings FROM edit_changes "
                                "WHERE edit_id = ?", (eid,)).fetchall()
            # what every paired computer downloads again once it is written (design 4.6)
            tracks, size = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM library_files WHERE id IN "
                "(SELECT DISTINCT file_id FROM edit_changes WHERE edit_id = ? "
                "AND state = 'pending')", (eid,)).fetchone()
        if e["purged_at"]:
            return self._line(e, json.loads(e["summary"] or "{}"),
                              {"files_total": 0, "files_done": 0, "files_failed": 0,
                               "files_conflict": 0})
        by_field: dict[str, int] = {}
        by_state: dict[str, int] = {}
        files: dict[str, set[int]] = {}
        warned = 0
        for r in rows:
            by_field[r["field"]] = by_field.get(r["field"], 0) + 1
            by_state[r["state"]] = by_state.get(r["state"], 0) + 1
            files.setdefault(r["state"], set()).add(r["file_id"])
            warned += r["warnings"] != "[]"
        written = set().union(*(files.get(s, set()) for s in
                                ("pending", "applied", "failed", "conflict")))
        line = self._line(
            e, {"changed": len({r["file_id"] for r in rows}), "changes": len(rows),
                "by_field": by_field, "by_state": by_state, "warnings": warned},
            {"files_total": len(written), "files_done": len(files.get("applied", set())),
             "files_failed": len(files.get("failed", set())),
             "files_conflict": len(files.get("conflict", set()))})
        line["resend"] = {"tracks": tracks, "bytes": size}
        return line

    def _line(self, e, counts: dict, progress: dict) -> dict:
        """An edit as the API shows it. `undone` is "all" when every change it
        wrote was reverted, "some" when only part was; `undoable` says whether
        anything it wrote can still be reverted."""
        by_state = counts.get("by_state", {})
        reverted, kept = by_state.get("undone", 0), by_state.get("applied", 0)
        return {
            "id": e["id"], "state": e["state"], "label": e["label"],
            "catalogue": e["catalogue"], "library_rev": e["library_rev"],
            "undo_of": e["undo_of"], "created_at": e["created_at"],
            "applied_at": e["applied_at"], "finished_at": e["finished_at"],
            "counts": counts, "progress": progress, "current": self._current.get(e["id"]),
            "undone": ("some" if kept else "all") if reverted else None,
            "undoable": not e["purged_at"] and e["state"] in FINISHED and kept > 0,
            "purged": bool(e["purged_at"]),
        }

    def history(self, limit: int = 50, cursor: str | None = None) -> dict:
        """The edits that were applied, newest first (design 3.5)."""
        if not 1 <= limit <= 200:
            raise LibraryError(400, "limit must be between 1 and 200")
        marks = ", ".join("?" for _ in UNUSED)
        where = [f"state NOT IN ({marks})"]
        params: list[object] = [*UNUSED]
        if cursor:
            where.append("id < ?")
            params.append(_cursor(cursor))
        with self.db.transaction() as conn:
            found = [r[0] for r in conn.execute(
                f"SELECT id FROM edits WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
                (*params, limit + 1))]
        items = [item for item in (self.get(i) for i in found[:limit]) if item]
        return {"next": _next(found[limit - 1]) if len(found) > limit else None,
                "items": items}

    def changes(self, eid: int, field: str = "", state: str = "", warning: str = "",
                limit: int = 200, cursor: str | None = None) -> dict:
        """One page of an edit's changes, in the order of the preview, so the
        changes of one track are together (design 3.5)."""
        if not 1 <= limit <= 500:
            raise LibraryError(400, "limit must be between 1 and 500")
        where: list[str] = ["c.edit_id = ?"]
        params: list[object] = [eid]
        for value, allowed, clause in ((field, FIELDS, "c.field = ?"),
                                       (state, CHANGE_STATES, "c.state = ?")):
            if value:
                if value not in allowed:
                    raise LibraryError(400, f"{value} is not one of {', '.join(allowed)}")
                where.append(clause)
                params.append(value)
        if warning:
            if warning not in WARNINGS:
                raise LibraryError(400, f"{warning} is not one of {', '.join(WARNINGS)}")
            where.append("c.warnings LIKE ?")
            params.append(f'%"{warning}"%')
        if cursor:
            where.append("c.id > ?")
            params.append(_cursor(cursor))
        with self.db.transaction() as conn:
            if conn.execute("SELECT 1 FROM edits WHERE id = ?", (eid,)).fetchone() is None:
                raise LibraryError(404, "no such edit")
            rows = conn.execute(
                "SELECT c.*, f.path FROM edit_changes c LEFT JOIN library_files f "
                f"ON f.id = c.file_id WHERE {' AND '.join(where)} ORDER BY c.id LIMIT ?",
                (*params, limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = _next(rows[-1]["id"]) if more else None
        return {"next": nxt, "items": [{
            "change_id": r["id"], "file_id": r["file_id"], "path": r["path"] or "",
            "field": r["field"], "old": _decode(r["field"], r["old_value"]),
            "new": _decode(r["field"], r["new_value"]), "by": json.loads(r["by"]),
            "warnings": json.loads(r["warnings"]), "state": r["state"], "error": r["error"],
        } for r in rows]}

    # ------------------------------------------------------------- apply
    def apply(self, eid: int) -> dict:
        """Start writing an edit in the background (design 4.4).

        Raises LibraryError: 404 unknown edit; 409 another edit is being
        applied, this one cannot be applied, or nothing is left to write; 410
        the preview expired (24 hours unused, or another edit was applied
        since it was made).
        """
        with self._starting:
            expired = False
            with self.db.transaction() as conn:
                e = conn.execute("SELECT * FROM edits WHERE id = ?", (eid,)).fetchone()
                if e is None:
                    raise LibraryError(404, "no such edit")
                self._not_busy(conn)
                if e["state"] == "preview":
                    newer = conn.execute("SELECT 1 FROM edits WHERE id <> ? AND applied_at > ?",
                                         (eid, e["created_at"])).fetchone()
                    old = self.clock() - datetime.fromisoformat(e["created_at"]).timestamp()
                    expired = bool(newer) or old > PREVIEW_SECONDS
                    if expired:
                        conn.execute("UPDATE edits SET state = 'expired' WHERE id = ?", (eid,))
                elif e["state"] == "expired":
                    expired = True
                elif e["state"] not in APPLIABLE:
                    raise LibraryError(409, f"an edit that is {e['state']} cannot be applied")
                if not expired:
                    marks = ", ".join("?" for _ in TO_WRITE)
                    left = conn.execute(f"SELECT COUNT(*) FROM edit_changes WHERE edit_id = ? "
                                        f"AND state IN ({marks})", (eid, *TO_WRITE)).fetchone()[0]
                    if not left:
                        raise LibraryError(409, "nothing is left to apply")
                    conn.execute("UPDATE edits SET state = 'applying', finished_at = NULL, "
                                 "applied_at = COALESCE(applied_at, ?) WHERE id = ?",
                                 (dbmod.iso(self.clock()), eid))
            if expired:
                raise LibraryError(410, "the preview expired: make it again")
            self._start(eid)
        out = self.get(eid)
        assert out is not None
        return out

    @staticmethod
    def _not_busy(conn) -> None:
        if conn.execute("SELECT 1 FROM edits WHERE state = 'applying'").fetchone():
            raise LibraryError(409, "another edit is being applied: wait for it to end")

    def _start(self, eid: int) -> None:
        self._idle.clear()
        threading.Thread(target=self._run, args=(eid,), name=f"edit-{eid}", daemon=True).start()

    # -------------------------------------------------------------- undo
    def undo(self, eid: int, files=None) -> dict:
        """Revert an edit, whole or for some tracks, as a new edit that starts
        applying at once (design 4.7). Each change it wrote gets its old value
        back, expecting the value it wrote; what an unfinished edit left
        pending is dropped.

        Raises LibraryError: 400 `files` not a list of track ids, 404 unknown
        edit, 409 another edit is applying or nothing is left to undo, 410 its
        changes were purged.
        """
        only = library.check_ids(files) if files is not None else None
        rev = self.lib.rev()
        now = dbmod.iso(self.clock())
        with self._starting:
            with self.db.transaction() as conn:
                e = conn.execute("SELECT * FROM edits WHERE id = ?", (eid,)).fetchone()
                if e is None:
                    raise LibraryError(404, "no such edit")
                if e["purged_at"]:
                    raise LibraryError(410, "this edit can no longer be undone")
                self._not_busy(conn)
                scope, params = "", [eid]
                if only:
                    scope = f" AND file_id IN ({', '.join('?' for _ in only)})"
                    params += only
                source = conn.execute(f"SELECT * FROM edit_changes WHERE edit_id = ? "
                                      f"AND state = 'applied'{scope} ORDER BY id", params).fetchall()
                if e["state"] not in FINISHED or not source:
                    raise LibraryError(409, "nothing is left to undo")
                if e["state"] != "applied":   # cancelled or interrupted: the rest is dropped
                    conn.execute(f"UPDATE edit_changes SET state = 'excluded' WHERE edit_id = ? "
                                 f"AND state IN ('pending', 'failed'){scope}", params)
                fids = list(dict.fromkeys(r["file_id"] for r in source))
                new = conn.execute(
                    "INSERT INTO edits (state, label, selection, steps, catalogue, library_rev, "
                    "undo_of, created_at, applied_at) VALUES ('applying', ?, ?, '[]', ?, ?, ?, ?, ?)",
                    (f"undo: {e['label']}"[:200], json.dumps({"ids": fids}),
                     rules.CATALOGUE_VERSION, rev, eid, now, now)).lastrowid
                conn.executemany(
                    "INSERT INTO edit_changes (edit_id, file_id, audio_id, field, old_value, "
                    "new_value, by, state) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                    [(new, r["file_id"], r["audio_id"], r["field"], r["new_value"],
                      r["old_value"], json.dumps([{"undo": r["id"]}])) for r in source])
            assert new is not None
            self._start(new)
        out = self.get(new)
        assert out is not None
        return out

    def _reverted(self, conn, rows: list[dict]) -> None:
        """The changes an undo has just written back: their sources are
        `undone`, and when a source was itself an undo, what it had undone is
        `applied` again."""
        for r in rows:
            for step in json.loads(r["by"]):
                if "undo" not in step:
                    continue
                conn.execute("UPDATE edit_changes SET state = 'undone' WHERE id = ?",
                             (step["undo"],))
                src = conn.execute("SELECT by FROM edit_changes WHERE id = ?",
                                   (step["undo"],)).fetchone()
                for back in json.loads(src["by"]) if src else []:
                    if "undo" in back:
                        conn.execute("UPDATE edit_changes SET state = 'applied' "
                                     "WHERE id = ? AND state = 'undone'", (back["undo"],))

    # ------------------------------------------------------------- purge
    def purge(self) -> dict:
        """Remove previews unused for a day, and the changes of edits that
        finished more than `edit_history_days` ago (0 keeps them). Such an
        edit keeps its line and counts in the history."""
        now = self.clock()
        days = self.history_days()
        marks = ", ".join("?" for _ in UNUSED)
        with self.db.transaction() as conn:
            unused = [r[0] for r in conn.execute(
                f"SELECT id FROM edits WHERE state IN ({marks}) AND created_at < ?",
                (*UNUSED, dbmod.iso(now - PREVIEW_SECONDS)))]
            for eid in unused:
                conn.execute("DELETE FROM edit_changes WHERE edit_id = ?", (eid,))
                conn.execute("DELETE FROM edits WHERE id = ?", (eid,))
            done = [] if days <= 0 else [r[0] for r in conn.execute(
                f"SELECT id FROM edits WHERE purged_at IS NULL AND finished_at < ? "
                f"AND state IN ({', '.join('?' for _ in FINISHED)})",
                (dbmod.iso(now - days * DAY), *FINISHED))]
        for eid in done:
            line = self.get(eid)
            with self.db.transaction() as conn:
                conn.execute("UPDATE edits SET purged_at = ?, summary = ? WHERE id = ?",
                             (dbmod.iso(now), json.dumps(line["counts"] if line else {}), eid))
                conn.execute("DELETE FROM edit_changes WHERE edit_id = ?", (eid,))
        if unused or done:
            log.info("edits: purged %d unused previews and %d old journals", len(unused), len(done))
        return {"previews": len(unused), "journals": len(done)}

    def purge_due(self) -> bool:
        """The purge, if it has not run in the last day; True if it ran."""
        now = self.clock()
        if self._purged_at is not None and now - self._purged_at < DAY:
            return False
        self._purged_at = now
        self.purge()
        return True

    def _run(self, eid: int) -> None:
        state = "interrupted"
        try:
            marks = ", ".join("?" for _ in TO_WRITE)
            with self.db.transaction() as conn:
                fids = [r[0] for r in conn.execute(
                    f"SELECT file_id FROM edit_changes WHERE edit_id = ? AND state IN ({marks}) "
                    "GROUP BY file_id ORDER BY MIN(id)", (eid, *TO_WRITE))]
            for fid in fids:
                with self.db.transaction() as conn:
                    rows = conn.execute(
                        f"SELECT * FROM edit_changes WHERE edit_id = ? AND file_id = ? "
                        f"AND state IN ({marks})", (eid, fid, *TO_WRITE)).fetchall()
                self._write(eid, fid, [dict(r) for r in rows])
            state = "applied"
        except Exception:
            log.exception("edit %s: the apply stopped", eid)
        finally:
            with self.db.transaction() as conn:
                conn.execute("UPDATE edits SET state = ?, finished_at = ? WHERE id = ?",
                             (state, dbmod.iso(self.clock()), eid))
            self._current.pop(eid, None)
            self._idle.set()

    def _write(self, eid: int, fid: int, rows: list[dict]) -> None:
        """All pending changes of one file in one write, expecting the old values."""
        changes = {r["field"]: _decode(r["field"], r["new_value"]) for r in rows}
        expect = {r["field"]: _decode(r["field"], r["old_value"]) for r in rows}
        self._current[eid] = (self.lib.file(fid) or {}).get("path", "")
        state, error = "applied", ""
        try:
            result = self.lib.write_tags(fid, changes, expect)
            if not result.written:
                state, error = "conflict", "the file changed: " + ", ".join(result.differs or {})
        except LibraryError as exc:
            state, error = "failed", f"{FAILURE.get(exc.status, 'write error')}: {exc.detail}"
        except OSError as exc:
            reason = "no space" if exc.errno == errno.ENOSPC else "write error"
            state, error = "failed", f"{reason}: {exc}"
        with self.db.transaction() as conn:
            conn.executemany("UPDATE edit_changes SET state = ?, error = ? WHERE id = ?",
                             [(state, error, r["id"]) for r in rows])
            if state == "applied":
                self._reverted(conn, rows)
        log.info("edit %s: %s %s", eid, state, self._current[eid])


# ------------------------------------------------------------ the app's one
_current: Edits | None = None
_current_lock = threading.Lock()


def current() -> Edits:
    """The edits over the app's Library (rebuilt if the Library is). The first
    one after a start finds an apply that the stop cut short `interrupted`;
    the daily purge runs from here, the first time the edits are used each day."""
    global _current
    lib = library.current()
    with _current_lock:
        if _current is None or _current.lib is not lib:
            _current = Edits(dbmod.db, lib)
            _current.recover()
        edits = _current
    try:
        edits.purge_due()
    except Exception:
        log.exception("edits: the daily purge failed")
    return edits
