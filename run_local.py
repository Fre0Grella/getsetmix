"""GetSetMix — local app mode.

Same web UI, not always-on: starts the server and auto-opens a browser
window. Works on Linux, Windows and macOS (ffmpeg must be on PATH).

    python run_local.py [--port 8765]
"""
import argparse
import os
import sys
import threading
import webbrowser


def default_data_dir() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller build: __file__ lives in a temp dir wiped on exit,
        # so persist next to the user profile instead.
        return os.path.join(os.path.expanduser("~"), ".getsetmix")
    return os.path.join(os.path.dirname(__file__), "data")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GetSetMix locally")
    parser.add_argument("--port", type=int, default=int(os.environ.get("GSM_PORT", 8765)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("GSM_DATA_DIR", default_data_dir())

    import uvicorn
    from app.main import app  # noqa: WPS433 (after env is set)

    if not args.no_browser:
        threading.Timer(1.2, webbrowser.open, args=(f"http://{args.host}:{args.port}",)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
