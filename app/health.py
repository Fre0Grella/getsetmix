"""Continuous self-diagnosis for the Rekordbox link.

Every way this feature breaks used to be invisible until Rekordbox showed a
red missing-file icon. These checks run the same questions the setup wizard
asks, on demand and behind the toolbar status chip, and each failure carries
the fix rather than just the symptom.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config, rekordbox, targets
from .profiles import Profile, path_from_location

OK, WARN, ERROR = "ok", "warn", "error"
_RANK = {OK: 0, WARN: 1, ERROR: 2}

# A collection export older than this is almost certainly out of date, which
# silently defeats the already-imported purge.
STALE_COLLECTION_DAYS = 30
# An agent that hasn't checked in for this long is treated as offline.
AGENT_OFFLINE_HOURS = 24
SAMPLE_SIZE = 25


@dataclass
class Check:
    id: str
    level: str
    title: str
    detail: str = ""
    fix: str = ""
    profile: str = ""


@dataclass
class Report:
    status: str = OK
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> None:
        self.checks.append(check)
        if _RANK[check.level] > _RANK[self.status]:
            self.status = check.level

    def to_dict(self) -> dict:
        return {"status": self.status, "checks": [asdict(c) for c in self.checks]}


# --------------------------------------------------------------- utilities
def _writable(directory: Path) -> tuple[bool, str]:
    """Probe a real write rather than trusting os.access — permissions on
    network mounts and container volumes routinely lie."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".gsm-probe-"):
            pass
        return True, ""
    except OSError as exc:
        return False, str(exc).splitlines()[0]


def _age_days(path: Path) -> float | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return (datetime.now(timezone.utc).timestamp() - mtime) / 86400.0


def _age_hours(iso: str) -> float | None:
    if not iso:
        return None
    try:
        stamp = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0


# ----------------------------------------------------------------- checks
def _check_library(report: Report) -> None:
    root = Path(str(config.settings["library_root"]))
    ok, err = _writable(root)
    if ok:
        report.add(Check("library", OK, "Library folder is writable", str(root)))
    else:
        report.add(Check(
            "library", ERROR, "Library folder is not writable", f"{root}: {err}",
            "Check the volume mount and its permissions — downloads cannot be saved.",
        ))


def _check_xml(report: Report, target: targets.XmlTarget) -> None:
    pid = target.profile.id if target.profile else ""
    path = Path(target.xml_path)
    ok, err = _writable(path.parent)
    if not ok:
        report.add(Check(
            "xml_writable", ERROR, f"Cannot write the XML for {target.label}",
            f"{path.parent}: {err}",
            "Point the XML somewhere the server can write, or fix the mount permissions.",
            pid,
        ))
        return

    count = rekordbox.track_count(target.xml_path)
    if count < 0 and path.exists():
        report.add(Check(
            "xml_valid", ERROR, f"The XML for {target.label} is unreadable", str(path),
            "It will be moved aside as .corrupt.xml and rebuilt on the next download.",
            pid,
        ))
        return
    report.add(Check(
        "xml_valid", OK, f"XML for {target.label} is valid",
        f"{max(count, 0)} track(s) · {path}", "", pid,
    ))


def _check_locations(report: Report, target: targets.XmlTarget) -> None:
    """Do the paths we wrote point at files that actually exist?

    This is the check that would have caught the original bug on day one.
    """
    pid = target.profile.id if target.profile else ""
    locations = rekordbox.sample_locations(target.xml_path, SAMPLE_SIZE)
    if not locations:
        return  # nothing ingested yet; not a failure

    library = str(config.settings["library_root"])
    resolved, unmappable, missing = 0, 0, []
    for loc in locations:
        dj_path = path_from_location(loc)
        server_path = dj_path
        if target.profile is not None:
            back = target.profile.unmap_path(dj_path, library)
            if back is None:
                unmappable += 1
                continue
            server_path = back
        if os.path.exists(server_path):
            resolved += 1
        elif len(missing) < 3:
            missing.append(dj_path)

    total = len(locations)
    if unmappable:
        report.add(Check(
            "locations", ERROR,
            f"{unmappable}/{total} sampled tracks fall outside {target.label}'s library root",
            f"library root: {target.profile.library_root if target.profile else library}",
            "The XML holds paths from an older configuration. Fix the library root, "
            "then re-ingest or clean the inbox.",
            pid,
        ))
    elif resolved == total:
        report.add(Check(
            "locations", OK, f"{resolved}/{total} sampled tracks resolve for {target.label}",
            "", "", pid,
        ))
    else:
        report.add(Check(
            "locations", ERROR,
            f"only {resolved}/{total} sampled tracks resolve for {target.label}",
            "missing: " + ", ".join(missing),
            "The files are not where the XML says they are — check that the library "
            "has finished syncing and that the machine's library root is right.",
            pid,
        ))


def _check_collection(report: Report, target: targets.XmlTarget) -> None:
    pid = target.profile.id if target.profile else ""
    coll = target.collection_xml
    if not coll:
        report.add(Check(
            "collection", WARN, f"No collection export for {target.label}", "",
            "Export your collection from Rekordbox (File ▸ Export Collection in xml "
            "format) and point GetSetMix at it, so tracks you already imported stop "
            "reappearing in the inbox.",
            pid,
        ))
        return
    path = Path(coll)
    if not path.exists():
        report.add(Check(
            "collection", ERROR, f"Collection export for {target.label} is missing",
            coll, "Re-export it, or clear the path to disable the inbox purge.", pid,
        ))
        return
    age = _age_days(path)
    if age is not None and age > STALE_COLLECTION_DAYS:
        report.add(Check(
            "collection", WARN, f"Collection export for {target.label} is stale",
            f"last updated {int(age)} days ago",
            "Re-export it from Rekordbox — until you do, tracks you imported since "
            "then keep coming back into the inbox.",
            pid,
        ))
        return
    report.add(Check(
        "collection", OK, f"Collection export for {target.label} is current",
        f"updated {int(age or 0)} day(s) ago", "", pid,
    ))


def _check_agent(report: Report, profile: Profile) -> None:
    if not profile.agent_token:
        report.add(Check(
            "agent", WARN, f"No companion paired with {profile.name or profile.id}", "",
            "Pairing gsm-link on that machine lets GetSetMix confirm the files really "
            "land where Rekordbox expects them. Optional, but it is how you find out "
            "before a gig instead of during one.",
            profile.id,
        ))
        return
    hours = _age_hours(profile.last_seen)
    if hours is None:
        report.add(Check(
            "agent", WARN, f"Companion on {profile.name or profile.id} has never checked in",
            "", "Run `gsm-link run` on that machine.", profile.id,
        ))
        return
    if hours > AGENT_OFFLINE_HOURS:
        report.add(Check(
            "agent", WARN, f"Companion on {profile.name or profile.id} is offline",
            f"last seen {int(hours)}h ago",
            "Start `gsm-link run` on that machine if you want live verification.",
            profile.id,
        ))
        return

    rep = profile.last_report or {}
    checked, found = int(rep.get("checked") or 0), int(rep.get("resolved") or 0)
    if checked and found < checked:
        report.add(Check(
            "agent_files", ERROR,
            f"{profile.name or profile.id} can only see {found}/{checked} of its tracks",
            ", ".join(rep.get("missing", [])[:3]),
            "The XML points at files that machine cannot open — usually the sync is "
            "still running, or its library root is wrong.",
            profile.id,
        ))
    elif checked:
        report.add(Check(
            "agent_files", OK,
            f"{profile.name or profile.id} resolves {found}/{checked} sampled tracks",
            "", "", profile.id,
        ))
    else:
        report.add(Check(
            "agent", OK, f"Companion on {profile.name or profile.id} is connected",
            f"last seen {int(hours)}h ago", "", profile.id,
        ))

    if rep.get("rekordbox_xml") == "manual":
        report.add(Check(
            "rekordbox_pref", WARN,
            f"Set the XML path by hand on {profile.name or profile.id}",
            profile.dj_xml_path(),
            "Rekordbox ▸ Preferences ▸ Advanced ▸ Database ▸ rekordbox xml — point it "
            "at that file. The companion could not set it safely on this version.",
            profile.id,
        ))


def _check_setup(report: Report) -> None:
    if config.settings.get("setup_complete"):
        return
    report.add(Check(
        "setup", WARN, "Setup has not been run", "",
        "Open /setup — it configures the paths and then verifies them end to end.",
    ))


def run() -> dict:
    """Full link report. Safe to call from a request handler thread."""
    report = Report()
    _check_setup(report)
    _check_library(report)

    profiles = config.settings.active_profiles()
    if not profiles and config.settings.profiles():
        report.add(Check(
            "profiles", ERROR, "Every machine profile is missing a library root", "",
            "A profile without the machine's own library root cannot produce paths "
            "Rekordbox can open. Set it in the wizard.",
        ))

    for target in targets.write_targets():
        _check_xml(report, target)
        _check_locations(report, target)
        _check_collection(report, target)

    for profile in profiles:
        _check_agent(report, profile)

    return report.to_dict()
