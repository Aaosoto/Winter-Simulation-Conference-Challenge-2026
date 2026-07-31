"""
Lightweight static server for the Port Network Simulation Dashboard.

This script lives inside the dashboard/ directory. It serves the project root
(parent of this file) so both the dashboard (this directory) and the CSV
outputs (../Output) are reachable from the same origin, which is what
app.js expects when it fetches `../Output/<file>.csv`.

Usage (from the dashboard/ directory):
    python serve_gui.py            # default port 8000
    python serve_gui.py 8765        # custom port
    python serve_gui.py --no-open   # do not launch the browser

The server opens http://localhost:<port>/dashboard/ in the default browser on start.
Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

# This script sits inside dashboard/, so the project root is its parent.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "Output"
INDEX_FILE = DASHBOARD_DIR / "index.html"

REQUIRED_CSVS = (
    "Port_Waiting_Statistics.csv",
    "Service_Route_Utilization.csv",
    "Average_Origin_Waiting_TEU_By_OD.csv",
    "Average_In_Transit_TEU_By_OD.csv",
    "Cumulative_Completed_TEU_By_OD.csv",
    "Average_Vessel_State_Counts.csv",
    "ATT_By_Statistics_Interval.csv",
)

DEFAULT_PORT = 8000
HOST = "127.0.0.1"  # loopback only — dashboard is local-only


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Static handler rooted at PROJECT_ROOT, with cache disabled for dev."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self) -> None:
        # Prevent the browser from caching CSVs / HTML between runs.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


class ReusableServer(socketserver.TCPServer):
    """Allow quick restarts without TIME_WAIT socket conflicts."""

    allow_reuse_address = True


def _validate_layout() -> list[str]:
    """Return a list of human-readable warnings about the workspace."""
    warnings: list[str] = []
    if not DASHBOARD_DIR.is_dir():
        warnings.append(f"Dashboard directory missing: {DASHBOARD_DIR}")
    if not INDEX_FILE.is_file():
        warnings.append(f"Entry HTML missing: {INDEX_FILE}")
    if not OUTPUT_DIR.is_dir():
        warnings.append(f"Output directory missing: {OUTPUT_DIR}")
    else:
        missing = [name for name in REQUIRED_CSVS if not (OUTPUT_DIR / name).is_file()]
        if missing:
            warnings.append(
                "Output directory is missing CSV(s) the dashboard expects:\n  - "
                + "\n  - ".join(missing)
            )
    return warnings


def _open_browser_delayed(url: str, delay: float = 0.6) -> None:
    """Wait briefly for the server to bind, then open the dashboard URL."""
    time.sleep(delay)
    try:
        if not webbrowser.open(url, new=2):
            print(f"  (could not auto-launch a browser; open {url} manually)")
    except webbrowser.Error as exc:
        print(f"  (browser launch failed: {exc}; open {url} manually)")


def _print_banner(port: int, open_browser: bool) -> None:
    url = f"http://{HOST}:{port}/dashboard/"
    print("=" * 64)
    print(" Port Network Simulation Dashboard — dev server")
    print("=" * 64)
    print(f" Project root : {PROJECT_ROOT}")
    print(f" GUI entry    : {url}")
    print(f" Output CSVs  : http://{HOST}:{port}/Output/")
    if open_browser:
        print(f" Launching    : {url}")
    else:
        print(" Launching    : (skipped, --no-open)")
    print(" Stop         : Ctrl+C")
    print("=" * 64)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port to bind (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the browser automatically.",
    )
    parser.add_argument(
        "--host",
        default=HOST,
        help="Interface to bind (default: 127.0.0.1). Use 0.0.0.0 to expose on LAN.",
    )
    args = parser.parse_args(argv)

    warnings = _validate_layout()
    for warn in warnings:
        print(f"WARNING: {warn}", file=sys.stderr)

    # Refuse to start if the entry HTML is missing — everything else is a warning.
    if not INDEX_FILE.is_file():
        print("ERROR: cannot find gui/index.html — aborting.", file=sys.stderr)
        return 1

    os.chdir(PROJECT_ROOT)
    _print_banner(args.port, open_browser=not args.no_open)

    try:
        with ReusableServer((args.host, args.port), DashboardHandler) as httpd:
            if not args.no_open:
                threading.Thread(
                    target=_open_browser_delayed,
                    args=(f"http://{args.host}:{args.port}/dashboard/",),
                    daemon=True,
                ).start()
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down...")
                httpd.shutdown()
    except OSError as exc:
        # Most commonly: address already in use.
        print(f"ERROR: failed to bind {args.host}:{args.port} — {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
