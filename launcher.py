"""
PyInstaller-compatible launcher for the application.
Handles setup for frozen environments (like checking _MEIPASS).
"""

import multiprocessing
import sys
from pathlib import Path

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
