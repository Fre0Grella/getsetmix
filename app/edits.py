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

Covers (design 3.2, 4.7) are not rule work: `set_cover` and `clear_cover`
steps are handled here. An image for `set_cover` is uploaded first and kept
under `<data>/edits/uploads/`; the cover an edit replaces is kept under
`<data>/edits/<edit id>/<file id>`, so an undo can put it back. A cover
change is written in the same single write as the track's tags.
"""
from __future__ import annotations

import base64
import errno
import json
import logging
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

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
COVER_OPS = ("set_cover", "clear_cover")
HAD_COVER = "cover"    # a cover change's old value before it is written: the file had one
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


FILTER_KEYS = ("q", "genre", "folder", "artist", "problem")   # as GET /api/library takes them


def _filter(raw) -> dict[str, str]:
    if not isinstance(raw, dict) or set(raw) - set(FILTER_KEYS) or \
            not all(isinstance(v, str) for v in raw.values()):
        raise LibraryError(400, "filter takes q, genre and folder, as text")
    return raw


def _is_cover(step) -> bool:
    return isinstance(step, dict) and step.get("op") in COVER_OPS


def _steps(raw) -> list[dict]:
    """The steps, checked once before any track: 400 names what is wrong."""
    if not isinstance(raw, list) or not raw:
        raise LibraryError(400, "steps must be a non-empty list")
    for step in raw:
        if isinstance(step, dict) and step.get("op") == "set" and step.get("field") in FIELDS:
            library.check_fields({step["field"]: step.get("value")})  # the year's range
        if _is_cover(step) and step["op"] == "set_cover" and \
                not str(step.get("source") or "").startswith("upload:"):
            raise LibraryError(400, "set_cover takes the source an image upload answered with")
    try:
        rules.run_steps({f: None if f == "year" else "" for f in FIELDS},
                        [s for s in raw if not _is_cover(s)])
    except rules.RuleError as exc:
        raise LibraryError(400, str(exc)) from None
    return raw


def _label(steps: list[dict]) -> str:
    """What the history calls an edit: its steps in short."""
    def part(s: dict) -> str:
        if "rule" in s:
            return s["rule"]
        if _is_cover(s):
            return "cover = " + ("new image" if s["op"] == "set_cover" else "none")
        if s["op"] == "set":
            return f"{s['field']} = {'' if s.get('value') is None else s['value']}"
        return f"{s['field']}: {s['op']}"
    return "; ".join(part(s) for s in steps)[:200]


def _warnings(field: str, new, multi: set[str], flagged: list[dict]) -> list[str]:
    """The warnings on one change: its own, and those the rules raised on its field."""
    out = list(dict.fromkeys(w["warning"] for w in flagged
                             if w.get("field") == field and w.get("warning") in WARNINGS))
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
                 history_days: Callable[[], int] | None = None,
                 store: Path | None = None) -> None:
        self.db = database
        self.store = store or config.DATA_DIR / "edits"   # images: uploads, replaced covers
        self.lib = lib
        self.clock = clock
        self.history_days = history_days or (lambda: int(config.settings["edit_history_days"]))
        self._purged_at: float | None = None
        self._starting = threading.Lock()   # two applies never both start
        self._idle = threading.Event()
        self._idle.set()
        self._current: dict[int, str] = {}  # edit id -> the file being written
        self._cancel: set[int] = set()       # edits asked to stop after the file in hand

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
        steps, label = body.get("steps"), None
        if body.get("ruleset_id") is not None:   # with both, the steps win; the set names it
            chosen = self.ruleset(body["ruleset_id"])
            if chosen is None:
                raise LibraryError(404, "no such rule set")
            steps = chosen["steps"] if steps is None else steps
            label = chosen["name"]
        eid, skipped_by_id, unchanged = self._store(ids, _steps(steps), label)
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

    def _store(self, ids: list[int], steps: list[dict],
               label: str | None = None) -> tuple[int, dict[int, str], list[int]]:
        """Run the steps over the index and store the preview: its id, the
        tracks left out with why, and the tracks the steps leave as they are."""
        rows = self._rows(ids)
        skipped: dict[int, str] = {}
        unchanged: list[int] = []
        changes = []
        tag_steps = [s for s in steps if not _is_cover(s)]
        cover = next(((i, s) for i, s in reversed(list(enumerate(steps))) if _is_cover(s)), None)
        source = cover[1].get("source") if cover else None
        if source and self._image_file(source) is None:
            raise LibraryError(400, "that image upload is not kept here: upload it again")
        for fid in ids:
            row = rows.get(fid)
            why = self._skip(row)
            if why:
                skipped[fid] = why
                continue
            assert row is not None
            before = {f: row[f] for f in FIELDS}
            result = rules.run_steps(before, tag_steps) if tag_steps else rules.StepsResult(before)
            differ = [f for f in FIELDS if result.fields[f] != before[f]]
            # A new image always counts as a change; removing one only where there is one.
            covered = cover is not None and (source is not None or bool(row["has_cover"]))
            if not differ and not covered:
                unchanged.append(fid)
                continue
            if covered and cover is not None:
                changes.append((fid, row["audio_id"], "cover",
                                HAD_COVER if row["has_cover"] else None, source,
                                json.dumps([{"step": cover[0], "op": cover[1]["op"]}]), "[]",
                                "pending"))
            multi = set(row["multi"].split(","))
            for f in differ:
                warnings = _warnings(f, result.fields[f], multi, result.warnings)
                state = "blocked" if set(warnings) & set(BLOCKING) else "pending"
                changes.append((fid, row["audio_id"], f, _encode(before[f]),
                                _encode(result.fields[f]), json.dumps(result.by.get(f, [])),
                                json.dumps(warnings), state))
        rev = self.lib.rev()
        with self.db.transaction() as conn:
            eid = conn.execute(
                "INSERT INTO edits (state, label, selection, steps, catalogue, library_rev, "
                "created_at) VALUES ('preview', ?, ?, ?, ?, ?, ?)",
                (label or _label(steps), json.dumps({"ids": ids}), json.dumps(steps),
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

    # ----------------------------------------------------------- images
    def keep_image(self, data: bytes) -> dict:
        """Keep an uploaded image for a `set_cover` step; raises LibraryError
        400 or 413 for one that is not a JPEG, PNG or WebP of at most 10 MB."""
        data, _ = library.check_image(data)
        token = secrets.token_hex(16)
        path = self.store / "uploads" / token
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"source": f"upload:{token}"}

    def _image_file(self, handle: str | None) -> Path | None:
        """Where an image a change names is kept, if it is: `upload:<token>`
        or `store:<edit id>/<file id>`. Nothing else is ever a path."""
        kind, _, key = (handle or "").partition(":")
        if kind == "upload" and re.fullmatch(r"[0-9a-f]{32}", key):
            path = self.store / "uploads" / key
        elif kind == "store" and re.fullmatch(r"\d+/\d+", key):
            path = self.store / key
        else:
            return None
        return path if path.is_file() else None

    def _image(self, handle: str) -> tagger.Cover:
        path = self._image_file(handle)
        if path is None:
            raise LibraryError(410, "the image is no longer kept")
        data = path.read_bytes()
        return data, tagger.image_type(data) or "image/jpeg"

    # ------------------------------------------------------- leave out
    def leave_out(self, eid: int, body) -> dict:
        """Leave tracks or single changes out of a preview, or put them back
        (design 3.5, PATCH). Only `pending` changes go out and only
        `excluded` ones come back; blocked ones stay blocked. Raises
        LibraryError: 400 a body that is not valid, 404 unknown edit, 409 not a
        preview."""
        if not isinstance(body, dict) or set(body) - {"exclude", "include"}:
            raise LibraryError(400, "send exclude and include, each with files and changes")
        moves = []
        for key, src, dst in (("exclude", "pending", "excluded"), ("include", "excluded", "pending")):
            part = body.get(key) or {}
            if not isinstance(part, dict) or set(part) - {"files", "changes"}:
                raise LibraryError(400, "send exclude and include, each with files and changes")
            files, changes = part.get("files") or [], part.get("changes") or []
            for ids in (files, changes):
                if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool)
                                                        for i in ids):
                    raise LibraryError(400, "files and changes are lists of ids")
            moves.append((src, dst, files, changes))
        with self.db.transaction() as conn:
            e = conn.execute("SELECT state FROM edits WHERE id = ?", (eid,)).fetchone()
            if e is None:
                raise LibraryError(404, "no such edit")
            if e["state"] != "preview":
                raise LibraryError(409, "only a preview can be changed")
            for src, dst, files, changes in moves:
                for column, ids in (("file_id", files), ("id", changes)):
                    for start in range(0, len(ids), 500):
                        chunk = ids[start:start + 500]
                        conn.execute(
                            f"UPDATE edit_changes SET state = ? WHERE edit_id = ? AND state = ? "
                            f"AND {column} IN ({', '.join('?' for _ in chunk)})",
                            (dst, eid, src, *chunk))
        out = self.get(eid)
        assert out is not None
        return out

    # ------------------------------------------------------- rule sets
    def _seed(self, conn) -> None:
        """The built-in rule sets, as the catalogue has them now."""
        now = dbmod.iso(self.clock())
        for rs in rules.BUILTIN_RULESETS:
            conn.execute(
                "INSERT INTO rule_sets (name, steps, builtin, created_at, updated_at) "
                "VALUES (?, ?, 1, ?, ?) ON CONFLICT(name) DO UPDATE SET steps = excluded.steps "
                "WHERE builtin = 1", (rs["name"], json.dumps(rs["steps"]), now, now))

    @staticmethod
    def _ruleset(r) -> dict:
        return {"id": r["id"], "name": r["name"], "builtin": bool(r["builtin"]),
                "steps": json.loads(r["steps"]), "updated_at": r["updated_at"]}

    def rulesets(self) -> list[dict]:
        """The saved rule sets, the built-in ones first."""
        with self.db.transaction() as conn:
            self._seed(conn)
            rows = conn.execute("SELECT * FROM rule_sets ORDER BY builtin DESC, name").fetchall()
        return [self._ruleset(r) for r in rows]

    def ruleset(self, rid) -> dict | None:
        if not isinstance(rid, int) or isinstance(rid, bool):
            raise LibraryError(400, "ruleset_id is a rule set id")
        with self.db.transaction() as conn:
            self._seed(conn)
            r = conn.execute("SELECT * FROM rule_sets WHERE id = ?", (rid,)).fetchone()
        return self._ruleset(r) if r else None

    def save_ruleset(self, body, rid: int | None = None) -> dict:
        """Save a new rule set, or rename, reorder or change one (design 3.5).
        A built-in set is copied, never changed. Raises LibraryError: 400 a
        body that is not valid, 404 unknown set, 409 built in, or the name is
        taken."""
        if not isinstance(body, dict):
            raise LibraryError(400, "a rule set has a name and steps")
        old = self.ruleset(rid) if rid is not None else None
        if rid is not None and old is None:
            raise LibraryError(404, "no such rule set")
        if old and old["builtin"]:
            raise LibraryError(409, "the built-in rule set cannot be changed: save a copy")
        name = body.get("name", old["name"] if old else None)
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise LibraryError(400, "a rule set needs a name of up to 100 characters")
        steps = _steps(body.get("steps", old["steps"] if old else None))
        now = dbmod.iso(self.clock())
        with self.db.transaction() as conn:
            taken = conn.execute("SELECT id FROM rule_sets WHERE name = ?", (name.strip(),)).fetchone()
            if taken and taken["id"] != rid:
                raise LibraryError(409, "another rule set has this name")
            if old is None:
                rid = conn.execute(
                    "INSERT INTO rule_sets (name, steps, builtin, created_at, updated_at) "
                    "VALUES (?, ?, 0, ?, ?)", (name.strip(), json.dumps(steps), now, now)).lastrowid
            else:
                conn.execute("UPDATE rule_sets SET name = ?, steps = ?, updated_at = ? WHERE id = ?",
                             (name.strip(), json.dumps(steps), now, rid))
        out = self.ruleset(rid)
        assert out is not None
        return out

    def delete_ruleset(self, rid: int) -> None:
        """Raises LibraryError: 404 unknown set, 409 built in."""
        old = self.ruleset(rid)
        if old is None:
            raise LibraryError(404, "no such rule set")
        if old["builtin"]:
            raise LibraryError(409, "the built-in rule set cannot be removed")
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM rule_sets WHERE id = ?", (rid,))

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

    def cancel(self, eid: int) -> dict:
        """Stop an apply after the file in hand (design 4.4): what was written
        stays and can be undone; applying again carries on. Raises
        LibraryError: 404 unknown edit, 409 not applying."""
        with self._starting:
            with self.db.transaction() as conn:
                e = conn.execute("SELECT state FROM edits WHERE id = ?", (eid,)).fetchone()
            if e is None:
                raise LibraryError(404, "no such edit")
            if e["state"] != "applying":
                raise LibraryError(409, "only an edit being applied can be stopped")
            self._cancel.add(eid)
        out = self.get(eid)
        assert out is not None
        return out

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

    def _keep_replaced(self, eid: int, fid: int, previous: tagger.Cover | None) -> str | None:
        """Keep the cover an edit replaced, for its undo; its handle, or None."""
        if previous is None:
            return None
        path = self.store / str(eid) / str(fid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(previous[0])
        return f"store:{eid}/{fid}"

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
        for eid in (*unused, *done):
            shutil.rmtree(self.store / str(eid), ignore_errors=True)
        self._purge_uploads(now)
        if unused or done:
            log.info("edits: purged %d unused previews and %d old journals", len(unused), len(done))
        return {"previews": len(unused), "journals": len(done)}

    def _purge_uploads(self, now: float) -> None:
        """Uploads a day old that no change names any more."""
        folder = self.store / "uploads"
        if not folder.is_dir():
            return
        with self.db.transaction() as conn:
            named = {r[0] for r in conn.execute(
                "SELECT new_value FROM edit_changes WHERE field = 'cover' AND new_value LIKE "
                "'upload:%' UNION SELECT old_value FROM edit_changes WHERE field = 'cover' "
                "AND old_value LIKE 'upload:%'")}
        for path in folder.iterdir():
            if f"upload:{path.name}" not in named and now - path.stat().st_mtime > PREVIEW_SECONDS:
                path.unlink(missing_ok=True)

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
                if eid in self._cancel:
                    state = "cancelled"
                    break
                with self.db.transaction() as conn:
                    rows = conn.execute(
                        f"SELECT * FROM edit_changes WHERE edit_id = ? AND file_id = ? "
                        f"AND state IN ({marks})", (eid, fid, *TO_WRITE)).fetchall()
                self._write(eid, fid, [dict(r) for r in rows])
            else:
                state = "applied"
        except Exception:
            log.exception("edit %s: the apply stopped", eid)
        finally:
            self._cancel.discard(eid)
            with self.db.transaction() as conn:
                conn.execute("UPDATE edits SET state = ?, finished_at = ? WHERE id = ?",
                             (state, dbmod.iso(self.clock()), eid))
            self._current.pop(eid, None)
            self._idle.set()

    def _write(self, eid: int, fid: int, rows: list[dict]) -> None:
        """All pending changes of one file in one write, expecting the old values."""
        tags = [r for r in rows if r["field"] != "cover"]
        changes = {r["field"]: _decode(r["field"], r["new_value"]) for r in tags}
        expect = {r["field"]: _decode(r["field"], r["old_value"]) for r in tags}
        pic = next((r for r in rows if r["field"] == "cover"), None)
        self._current[eid] = (self.lib.file(fid) or {}).get("path", "")
        state, error = "applied", ""
        try:
            kw = {}
            if pic:
                old = pic["old_value"]
                kw["cover"] = self._image(pic["new_value"]) if pic["new_value"] else None
                kw["expect_cover"] = (tagger.KEEP if old == HAD_COVER else None if old is None
                                      else library.cover_digest(self._image(old)))
            result = self.lib.write_tags(fid, changes, expect, **kw)
            if result.written and pic and pic["old_value"] == HAD_COVER:
                pic["old_value"] = self._keep_replaced(eid, fid, result.previous_cover)
            if not result.written:
                state, error = "conflict", "the file changed: " + ", ".join(result.differs or {})
        except LibraryError as exc:
            state, error = "failed", f"{FAILURE.get(exc.status, 'write error')}: {exc.detail}"
        except OSError as exc:
            reason = "no space" if exc.errno == errno.ENOSPC else "write error"
            state, error = "failed", f"{reason}: {exc}"
        except Exception as exc:   # anything else from the tagger fails this file only
            log.exception("edit %s: writing file %s failed", eid, fid)
            state, error = "failed", f"write error: {exc}"
        with self.db.transaction() as conn:
            conn.executemany("UPDATE edit_changes SET state = ?, error = ?, old_value = ? "
                             "WHERE id = ?", [(state, error, r["old_value"], r["id"]) for r in rows])
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
