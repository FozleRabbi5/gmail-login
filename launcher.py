"""
PyInstaller-compatible launcher for the application.
Handles setup for frozen environments (like checking _MEIPASS).
"""

import multiprocessing
import os
import sys
from pathlib import Path

# ── Step 1: Silence None streams BEFORE any other import ────────────────────
# In --windowed / --noconsole PyInstaller builds on Windows, Python sets
# sys.stdout and sys.stderr to None.  Libraries like loguru will crash if
# they try to write to None, so redirect them to devnull first.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# ── Step 2: Fix the working directory BEFORE any relative-path import ───────
# PyInstaller extracts to a temp _MEIPASS dir but the .exe lives in dist/app/.
# We want CWD = the folder that contains app.exe so that config/, logs/, and
# results/ are resolved correctly at runtime.
if getattr(sys, "frozen", False):
    _exe_dir = Path(sys.executable).parent
else:
    _exe_dir = Path(__file__).resolve().parent
os.chdir(_exe_dir)

# ── Step 3: Tell Playwright where browsers live ──────────────────────────────
# PLAYWRIGHT_BROWSERS_PATH=0 makes Playwright look inside its own package dir
# (i.e. inside _internal/playwright/driver/package/.local-browsers/) which is
# exactly where PyInstaller bundles them when --collect-all playwright is used.
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

# ── Step 4: Required for frozen multiprocessing on Windows ───────────────────
multiprocessing.freeze_support()


if __name__ == "__main__":
    # Import app only after all env vars and CWD are set
    from app import main as run_app
    run_app()

