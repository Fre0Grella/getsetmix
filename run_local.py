"""GetSetMix — local app mode.

Same web UI, not always-on: starts the server and opens it. With --window
(what GetSetMix Setup's shortcut uses) it opens in a window of its own, a
browser's app mode, and stops when that window closes. Works on Linux,
Windows and macOS (ffmpeg must be on PATH, or in a `bin` folder next to the
packaged app, where Setup puts it).

    python run_local.py [--port 8765] [--window]
"""
import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def default_data_dir() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller build: __file__ lives in a temp dir wiped on exit,
        # so persist next to the user profile instead.
        return os.path.join(os.path.expanduser("~"), ".getsetmix")
    return os.path.join(os.path.dirname(__file__), "data")


def add_bundled_tools() -> None:
    """Setup installs ffmpeg and Deno into `bin` next to the packaged app."""
    if getattr(sys, "frozen", False):
        tools = os.path.join(os.path.dirname(sys.executable), "bin")
        if os.path.isdir(tools):
            os.environ["PATH"] = tools + os.pathsep + os.environ.get("PATH", "")


def chromium() -> str | None:
    """A browser with an app mode (no tabs, no address bar): Edge ships with Windows."""
    if sys.platform == "win32":
        bases = [os.environ.get(v, "") for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe",
               r"BraveSoftware\Brave-Browser\Application\brave.exe"]
        candidates = [os.path.join(b, r) for b in bases if b for r in rel]
    elif sys.platform == "darwin":
        roots = ["/Applications", os.path.expanduser("~/Applications")]
        rel = ["Google Chrome.app/Contents/MacOS/Google Chrome", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
               "Brave Browser.app/Contents/MacOS/Brave Browser", "Chromium.app/Contents/MacOS/Chromium"]
        candidates = [os.path.join(r, x) for r in roots for x in rel]
    else:
        names = ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "brave-browser")
        candidates = [p for p in map(shutil.which, names) if p]
    return next((c for c in candidates if os.path.isfile(c)), None)


def already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/healthz", timeout=2) as r:
            return r.read().strip() == b"ok"
    except OSError:
        return False


def open_window(url: str, profile: str) -> "subprocess.Popen | None":
    exe = chromium()
    if not exe:
        webbrowser.open(url)
        return None
    seed_profile(profile)
    # Without --disable-background-mode, Edge keeps its process alive after
    # the window closes, and GetSetMix would never notice it was closed.
    return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1200,820",
                             "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
                             "--disable-sync", "--disable-features=Translate,msImplicitSignin,msEdgeStartupBoost"])


def seed_profile(profile: str) -> None:
    """A fresh Edge profile signs in to the Windows account and offers to
    translate the page, both in bubbles over the window (one of which blocks
    closing it). Turn both off before the first launch."""
    prefs = os.path.join(profile, "Default", "Preferences")
    if not os.path.exists(prefs):
        os.makedirs(os.path.dirname(prefs), exist_ok=True)
        with open(prefs, "w", encoding="utf-8") as f:
            f.write('{"translate": {"enabled": false}, "signin": {"allowed": false}}')


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GetSetMix locally")
    parser.add_argument("--port", type=int, default=int(os.environ.get("GSM_PORT", 8765)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--window", action="store_true",
                        help="open in an app window and stop when it closes")
    args = parser.parse_args()

    os.environ.setdefault("GSM_DATA_DIR", default_data_dir())
    add_bundled_tools()
    url = f"http://{args.host}:{args.port}"
    profile = os.path.join(os.environ["GSM_DATA_DIR"], "window")

    if args.window and already_running(url):
        # A second click on the shortcut: show the running one, start nothing.
        open_window(url, profile)
        return

    import uvicorn
    from app.main import app  # noqa: WPS433 (after env is set)

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="info"))

    def show() -> None:
        while not server.started and not server.should_exit:
            time.sleep(0.1)
        if args.window:
            proc = open_window(url, profile)
            if proc is not None:
                proc.wait()
                server.should_exit = True
        elif not args.no_browser:
            webbrowser.open(url)

    threading.Thread(target=show, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
