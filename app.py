"""
Entry point for the Login Tester application.
Bridges the Tkinter GUI thread with the async automation thread.
Sets up logging.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Redirect stdout and stderr to devnull if they are None (common in PyInstaller --windowed/--noconsole mode)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from loguru import logger

from config.settings import Settings
from gui.main_window import MainWindow
from automation.session_manager import SessionManager, SessionState
from services.progress import ProgressTracker


class LoguruHandler:
    """Loguru sink that pipes logs to a queue for the GUI."""
    def __init__(self, queue):
        self.queue = queue

    def write(self, message):
        record = message.record
        level = record["level"].name
        msg = f"{record['time'].strftime('%H:%M:%S')} | {level} | {record['message']}"
        self.queue.put((level, msg))


def setup_logging(gui_queue=None, log_dir="logs", level="INFO"):
    """Configure loguru logging with file and GUI handlers."""
    logger.remove()  # Remove default handler

    # Console handler
    logger.add(sys.stderr, level=level, colorize=True)

    # File handler
    log_path = Path(log_dir) / "login_tester.log"
    logger.add(
        str(log_path),
        rotation="10 MB",
        retention=5,
        level="DEBUG",  # Always log debug to file
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )

    # GUI handler
    if gui_queue:
        logger.add(LoguruHandler(gui_queue), level=level, format="{message}")


def main():
    """Main application entry point."""
    # Load default settings
    settings = Settings.load()

    # Create main window
    app = MainWindow(settings)

    # Setup logging to GUI
    setup_logging(app.log_queue, settings.log_directory, settings.log_level)
    logger.info("Application starting...")

    # Initialize components
    session_manager = SessionManager(settings)
    progress_tracker = None

    # GUI Callbacks
    def on_start(new_settings: Settings):
        nonlocal progress_tracker
        progress_tracker = None  # reset on each new run
        session_manager.update_settings(new_settings)
        session_manager.start()

        # poll_stats waits until the background thread finishes _initialize()
        # and sets session_manager.stats, then keeps refreshing every 500 ms.
        def poll_stats():
            nonlocal progress_tracker
            try:
                # Stop immediately if window was closed
                if not app.winfo_exists():
                    return

                # One-time setup: create tracker as soon as stats object is ready
                if progress_tracker is None and session_manager.stats is not None:
                    progress_tracker = ProgressTracker(session_manager.stats)
                    def update_gui(stats):
                        if app.winfo_exists():
                            app.update_progress(stats, ProgressTracker.format_eta, ProgressTracker.format_runtime)
                    progress_tracker.register_callback(update_gui)

                # Push a fresh snapshot to the GUI on every tick
                if progress_tracker is not None:
                    progress_tracker.update()

                # Keep looping while the session is active
                if session_manager.state in (SessionState.STARTING, SessionState.RUNNING, SessionState.PAUSED):
                    app.after(500, poll_stats)
                else:
                    # One final update so the UI shows the finished numbers
                    if progress_tracker is not None:
                        progress_tracker.update()
            except Exception:
                pass  # Window may have been destroyed; stop polling silently

        app.after(500, poll_stats)

    def on_pause():
        session_manager.pause()

    def on_resume():
        session_manager.resume()

    def on_stop():
        session_manager.stop()

    def on_state_change(state: SessionState):
        app.update_state(state.name)

    # Connect callbacks
    app.on_start_cb = on_start
    app.on_pause_cb = on_pause
    app.on_resume_cb = on_resume
    app.on_stop_cb = on_stop
    session_manager.on_state_change(on_state_change)

    # Initial state
    app.update_state(SessionState.IDLE.name)

    # Start Tkinter event loop
    app.mainloop()

    # Force exit if Tkinter closes
    sys.exit(0)


if __name__ == "__main__":
    main()
