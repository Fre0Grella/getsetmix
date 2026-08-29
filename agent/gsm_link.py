#!/usr/bin/env python3
"""gsm-link — the GetSetMix companion for the machine that runs Rekordbox.

Headless by design: no window, no tray, nothing to look at. Everything you see
lives in the GetSetMix web UI. This process exists to answer the questions the
server cannot answer from the other side of a sync folder:

  * where did Nextcloud/Syncthing *actually* put the library on this machine?
  * where does Rekordbox keep its preferences, and can we point it at our XML?
  * do the paths in the XML resolve to files that really exist here?

Standard library only — it has to run on a DJ's laptop with whatever Python is
already there (3.9+), not in a virtualenv you maintain.

    python gsm_link.py detect                        # print findings, no server
    python gsm_link.py pair --server URL --code NNNNNN
    python gsm_link.py run                           # keep reporting
    python gsm_link.py doctor                        # one round, verbose
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

__version__ = "1.0.0"

CONFIG_PATH = Path.home() / ".getsetmix-link.json"
DEFAULT_INTERVAL = 300
HTTP_TIMEOUT = 30


# --------------------------------------------------------------------- util
def log(msg: str) -> None:
    print(f"[gsm-link] {msg}", flush=True)


def host_os() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2), "utf-8")
    try:  # the agent token is a credential
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


# ----------------------------------------------------------------- discovery
def _nextcloud_config_paths() -> list[Path]:
    home = Path.home()
    if host_os() == "windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        bases = [appdata / "Nextcloud", appdata / "ownCloud"]
    elif host_os() == "macos":
        bases = [home / "Library" / "Preferences" / "Nextcloud",
                 home / "Library" / "Application Support" / "Nextcloud"]
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        bases = [xdg / "Nextcloud", xdg / "ownCloud"]
    return [b / "nextcloud.cfg" for b in bases] + [b / "owncloud.cfg" for b in bases]


# Qt writes its config as `0\Folders\1\localPath=/home/m/Nextcloud/`. configparser
# mangles those backslash keys, so parse the lines directly.
_CFG_LINE = re.compile(r"^\s*([^=\[\]]+?)\s*=\s*(.*?)\s*$")


def parse_nextcloud_cfg(text: str) -> list[dict]:
    """Sync folder pairs: local directory <-> remote path on the server."""
    folders: dict[str, dict] = {}
    for line in text.splitlines():
        if line.lstrip().startswith(("#", ";", "[")):
            continue
        match = _CFG_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        parts = key.replace("/", "\\").split("\\")
        if len(parts) < 2 or "folders" not in [p.lower() for p in parts]:
            continue
        field = parts[-1]
        if field not in ("localPath", "targetPath"):
            continue
        group = "\\".join(parts[:-1])
        entry = folders.setdefault(group, {})
        if field == "localPath":
            entry["local"] = value.rstrip("/\\") or value
        else:
            entry["remote"] = value.strip("/")
    return [f for f in folders.values() if f.get("local")]


def detect_nextcloud() -> list[dict]:
    for path in _nextcloud_config_paths():
        try:
            text = path.read_text("utf-8", errors="replace")
        except OSError:
            continue
        found = parse_nextcloud_cfg(text)
        if found:
            for entry in found:
                entry["source"] = str(path)
            return found
    return []


def _syncthing_config_paths() -> list[Path]:
    home = Path.home()
    if host_os() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Syncthing"
    elif host_os() == "macos":
        base = home / "Library" / "Application Support" / "Syncthing"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state")) / "syncthing"
    return [base / "config.xml", home / ".config" / "syncthing" / "config.xml"]


def detect_syncthing() -> list[dict]:
    for path in _syncthing_config_paths():
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        folders = [
            {"local": f.get("path", "").rstrip("/\\"),
             "remote": f.get("label") or f.get("id") or "",
             "source": str(path)}
            for f in root.iter("folder") if f.get("path")
        ]
        if folders:
            return folders
    return []


def _rekordbox_dirs() -> list[Path]:
    home = Path.home()
    if host_os() == "windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        base = appdata / "Pioneer"
    elif host_os() == "macos":
        base = home / "Library" / "Application Support" / "Pioneer"
    else:
        return []  # Rekordbox ships for Windows and macOS only
    if not base.is_dir():
        return []
    return sorted(
        (d for d in base.iterdir() if d.is_dir() and d.name.lower().startswith("rekordbox")),
        reverse=True,  # rekordbox7 before rekordbox6 before rekordbox
    )


def detect_rekordbox() -> dict:
    """What we can see of the local Rekordbox install.

    Deliberately conservative: this reports, it does not guess. `xml_setting`
    is only "found" when there is an existing option holding an .xml path — the
    one case where updating it is safe.
    """
    dirs = _rekordbox_dirs()
    if not dirs:
        return {"found": False, "reason": "no Rekordbox application-data folder",
                "xml_setting": "unknown"}

    info = {"found": True, "config_dir": str(dirs[0]), "versions": [d.name for d in dirs],
            "xml_setting": "manual", "options_file": "", "option_key": ""}
    for directory in dirs:
        options = directory / "options.json"
        if not options.is_file():
            continue
        info["options_file"] = str(options)
        key = _find_xml_option(options)
        if key:
            info["option_key"] = key
            info["xml_setting"] = "found"
            break
    for directory in dirs:
        db = directory / "master.db"
        if db.is_file():
            info["master_db"] = str(db)
            break
    return info


def _load_options(path: Path):
    """Rekordbox's options.json is a list of [key, value] pairs under
    "options". Returns (payload, pairs) or (None, None)."""
    try:
        payload = json.loads(path.read_text("utf-8", errors="replace"))
    except (OSError, ValueError):
        return None, None
    pairs = payload.get("options") if isinstance(payload, dict) else None
    if not isinstance(pairs, list):
        return None, None
    return payload, pairs


def _find_xml_option(path: Path) -> str:
    """Key of an existing option whose value is an .xml file path, if any."""
    _, pairs = _load_options(path)
    if pairs is None:
        return ""
    for pair in pairs:
        if not (isinstance(pair, list) and len(pair) == 2):
            continue
        key, value = pair
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if value.lower().endswith(".xml") and "xml" in key.lower():
            return key
    return ""


def apply_rekordbox_xml(xml_path: str, dry_run: bool = False) -> str:
    """Point Rekordbox's XML setting at `xml_path`.

    Only ever *updates* an option that already exists and already holds an .xml
    path. Inventing a key on an undocumented, version-dependent config format
    is how you corrupt somebody's library, so when we can't find one we say
    "manual" and the wizard shows the path to paste. Rekordbox must be closed:
    it rewrites this file on exit.
    """
    info = detect_rekordbox()
    if info.get("xml_setting") != "found":
        return "manual"
    options_file = Path(info["options_file"])
    payload, pairs = _load_options(options_file)
    if pairs is None:
        return "manual"

    changed = False
    for pair in pairs:
        if isinstance(pair, list) and len(pair) == 2 and pair[0] == info["option_key"]:
            if pair[1] == xml_path:
                return "already-set"
            pair[1] = xml_path
            changed = True
    if not changed:
        return "manual"
    if dry_run:
        return "would-set"
    try:
        backup = options_file.with_suffix(".json.gsm-backup")
        if not backup.exists():
            shutil.copy2(options_file, backup)
        tmp = options_file.with_suffix(".json.gsm-tmp")
        tmp.write_text(json.dumps(payload), "utf-8")
        tmp.replace(options_file)
    except OSError as exc:
        log(f"could not write Rekordbox options: {exc}")
        return "manual"
    return "set"


def detect_music_dirs() -> list[str]:
    home = Path.home()
    candidates = [home / "Music", home / "Musica", home / "Musique", home / "Musik"]
    for sync in detect_nextcloud() + detect_syncthing():
        local = Path(sync["local"])
        candidates.append(local)
        for name in ("Music", "Musica", "DJ"):
            candidates.append(local / name)
    seen, out = set(), []
    for path in candidates:
        text = str(path)
        if text not in seen and path.is_dir():
            seen.add(text)
            out.append(text)
    return out


def machine_facts() -> dict:
    return {
        "hostname": socket.gethostname(),
        "os": host_os(),
        "os_release": platform.platform(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "",
        "agent_version": __version__,
        "python": platform.python_version(),
        "nextcloud": detect_nextcloud(),
        "syncthing": detect_syncthing(),
        "rekordbox": detect_rekordbox(),
        "music_dirs": detect_music_dirs(),
    }


# -------------------------------------------------------------- verification
def _path_from_location(location: str) -> str:
    path = urllib.parse.unquote(location or "")
    for prefix in ("file://localhost", "file://"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    if re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    return path


def verify_xml(xml_path: str, limit: int = 25) -> dict:
    """Do the Locations in our XML point at files this machine can open?

    This is the answer the server cannot produce on its own, and the reason
    "it's configured" stops being a guess.
    """
    result = {"xml_path": xml_path, "checked": 0, "resolved": 0, "missing": []}
    if not xml_path:
        result["error"] = "no XML path configured"
        return result
    path = Path(xml_path)
    if not path.is_file():
        result["error"] = "the XML has not arrived on this machine yet"
        return result
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        result["error"] = f"unreadable XML: {exc}"
        return result

    for track in root.iter("TRACK"):
        location = track.get("Location")
        if not location:
            continue
        local = _path_from_location(location)
        result["checked"] += 1
        if os.path.exists(local):
            result["resolved"] += 1
        elif len(result["missing"]) < 5:
            result["missing"].append(local)
        if result["checked"] >= limit:
            break
    return result


def find_collection_export(config: dict) -> str:
    """A collection export sitting next to the library is the common setup."""
    root = (config.get("library_root") or "").strip()
    if not root:
        return ""
    for name in ("collection.xml", "rekordbox.xml", "collection_export.xml"):
        candidate = Path(root) / name
        if candidate.is_file():
            return str(candidate)
    return ""


# --------------------------------------------------------------------- http
def request(server: str, path: str, payload: dict, token: str = "") -> dict:
    url = server.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": f"gsm-link/{__version__}"}
    if token:
        headers["X-GSM-Agent-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace") or "{}")


def _explain(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("detail", "")
        except Exception:
            detail = ""
        return f"HTTP {exc.code}{': ' + detail if detail else ''}"
    if isinstance(exc, urllib.error.URLError):
        return f"cannot reach the server ({exc.reason})"
    return str(exc)


# ----------------------------------------------------------------- commands
def cmd_detect(args: argparse.Namespace) -> int:
    facts = machine_facts()
    if args.json:
        print(json.dumps(facts, indent=2))
        return 0
    print(f"machine   {facts['hostname']} ({facts['os']}, {facts['os_release']})")
    print(f"python    {facts['python']}")
    rb = facts["rekordbox"]
    if rb.get("found"):
        print(f"rekordbox {rb['config_dir']}")
        print(f"          XML preference: {rb['xml_setting']}")
    else:
        print(f"rekordbox not found ({rb.get('reason', 'unknown')})")
    for label, key in (("nextcloud", "nextcloud"), ("syncthing", "syncthing")):
        entries = facts[key]
        if not entries:
            print(f"{label} no sync folders found")
            continue
        for entry in entries:
            print(f"{label} {entry['local']}  <-  /{entry.get('remote', '')}")
    print("music     " + (", ".join(facts["music_dirs"]) or "none found"))
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    try:
        result = request(args.server, "/api/link/pair",
                         {"code": args.code, "machine": machine_facts()})
    except Exception as exc:
        log(f"pairing failed: {_explain(exc)}")
        return 1
    config = result.get("config", {})
    save_config({
        "server": args.server.rstrip("/"),
        "token": result["token"],
        "profile_id": config.get("profile_id", ""),
        "config": config,
    })
    log(f"paired as '{config.get('name') or config.get('profile_id')}'")
    log(f"config saved to {CONFIG_PATH}")
    if not (config.get("library_root") or "").strip():
        log("the server does not know this machine's library folder yet — "
            "set it in the wizard, then this agent will pick it up")
    return 0


def sync_once(stored: dict, apply_prefs: bool, verbose: bool = False) -> dict | None:
    server, token = stored.get("server", ""), stored.get("token", "")
    if not server or not token:
        log("not paired yet — run: gsm_link.py pair --server URL --code NNNNNN")
        return None

    config = stored.get("config", {}) or {}
    report = verify_xml(config.get("xml_path", ""), int(config.get("verify_sample") or 25))

    if apply_prefs and config.get("xml_path"):
        report["rekordbox_xml"] = apply_rekordbox_xml(config["xml_path"])
    else:
        report["rekordbox_xml"] = detect_rekordbox().get("xml_setting", "unknown")

    collection = find_collection_export(config)
    if collection:
        report["collection_xml_path"] = collection

    try:
        result = request(server, "/api/link/sync",
                         {"machine": machine_facts(), "report": report}, token)
    except Exception as exc:
        log(f"sync failed: {_explain(exc)}")
        return None

    stored["config"] = result.get("config", config)
    save_config(stored)
    if verbose or report.get("error") or report["resolved"] < report["checked"]:
        _print_report(report, stored["config"])
    return report


def _print_report(report: dict, config: dict) -> None:
    log(f"profile      {config.get('name') or config.get('profile_id')}")
    log(f"library      {config.get('library_root') or '(not set on the server)'}")
    log(f"xml          {config.get('xml_path') or '(not set)'}")
    if report.get("error"):
        log(f"verify       {report['error']}")
    else:
        log(f"verify       {report['resolved']}/{report['checked']} tracks resolve")
        for missing in report.get("missing", []):
            log(f"  missing    {missing}")
    state = report.get("rekordbox_xml")
    if state == "set":
        log("rekordbox    XML preference updated (restart Rekordbox to pick it up)")
    elif state == "already-set":
        log("rekordbox    XML preference already correct")
    elif state == "manual":
        log("rekordbox    set this by hand: Preferences > Advanced > Database > "
            f"rekordbox xml -> {config.get('xml_path')}")


def cmd_run(args: argparse.Namespace) -> int:
    stored = load_config()
    if not stored.get("token"):
        log("not paired — run `pair` first")
        return 1
    log(f"reporting to {stored['server']} every {args.interval}s (ctrl-c to stop)")
    while True:
        sync_once(stored, apply_prefs=args.apply, verbose=args.verbose)
        try:
            time.sleep(max(30, args.interval))
        except KeyboardInterrupt:
            log("stopped")
            return 0
        stored = load_config() or stored


def cmd_doctor(args: argparse.Namespace) -> int:
    stored = load_config()
    if not stored.get("token"):
        log("not paired — run `pair` first")
        return 1
    report = sync_once(stored, apply_prefs=args.apply, verbose=True)
    if report is None:
        return 1
    if report.get("error") or report["resolved"] < report["checked"]:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gsm-link", description="GetSetMix companion for the Rekordbox machine")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("detect", help="print what this machine looks like")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("pair", help="claim a pairing code from the setup wizard")
    p.add_argument("--server", required=True, help="e.g. http://homelab:8765")
    p.add_argument("--code", required=True)
    p.set_defaults(func=cmd_pair)

    p = sub.add_parser("run", help="keep reporting to the server")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    p.add_argument("--apply", action="store_true",
                   help="also update Rekordbox's XML preference (close Rekordbox first)")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("doctor", help="run one check and print the result")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
