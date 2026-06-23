"""
PyInstaller-compatible launcher for the application.
Handles setup for frozen environments (like checking _MEIPASS).
"""

import multiprocessing
import os
import sys
from pathlib import Path

# Redirect stdout and stderr to devnull if they are None (common in PyInstaller --windowed/--noconsole mode)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Force Playwright to look for browsers inside the bundled application folder
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

# Important for PyInstaller multiprocessing support
multiprocessing.freeze_support()


def main():
    """Launcher entry point."""
    # Ensure current directory is where the executable is
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent
        
    import os
    os.chdir(exe_dir)
    
    # Import and run app
    from app import main as run_app
    run_app()


if __name__ == "__main__":
    main()
