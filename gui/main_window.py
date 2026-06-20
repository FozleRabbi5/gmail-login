"""
Main Window for the Login Tester GUI.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk
from typing import Callable, Any

from loguru import logger

from config.settings import Settings
from gui.themes import DarkTheme
from gui.widgets import ConfigPanel, StatsPanel, ProgressPanel, ControlBar, LogPanel
from gui import dialogs
from services.statistics import StatsSnapshot


class MainWindow(tk.Tk):
    """
    Main application window.
    
    Runs in the main thread and communicates with the async automation
    thread via thread-safe queues and callbacks.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        
        self.settings = settings
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        
        # Callbacks to be set by app.py
        self.on_start_cb: Callable[[Settings], None] | None = None
        self.on_pause_cb: Callable[[], None] | None = None
        self.on_resume_cb: Callable[[], None] | None = None
        self.on_stop_cb: Callable[[], None] | None = None
        
        self._setup_window()
        self._build_ui()
        self._setup_menu()
        
        # Start periodic GUI update loop
        self._update_loop()

    def _setup_window(self) -> None:
        self.title("Login Tester - Professional")
        self.geometry("1100x750")
        self.minsize(900, 600)
        DarkTheme.apply(self)
        
        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self) -> None:
        # Main layout: PanedWindow for resizable split
        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left Pane (Config & Controls)
        self.left_pane = ttk.Frame(self.paned)
        self.paned.add(self.left_pane, weight=1)
        
        # Credentials file selector
        file_frame = ttk.Frame(self.left_pane)
        file_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(file_frame, text="Credentials:").pack(side="left")
        self.file_var = tk.StringVar(value=self.settings.credentials_file)
        ttk.Entry(file_frame, textvariable=self.file_var, state="readonly").pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(file_frame, text="Browse...", command=self._browse_file).pack(side="left")
        
        # Config Panel
        self.config_panel = ConfigPanel(self.left_pane, self.settings)
        self.config_panel.pack(fill="both", expand=True, pady=(0, 10))
        
        # Control Bar
        self.control_bar = ControlBar(
            self.left_pane,
            on_start=self._handle_start,
            on_pause=self._handle_pause,
            on_resume=self._handle_resume,
            on_stop=self._handle_stop,
        )
        self.control_bar.pack(fill="x")
        
        # Right Pane (Stats & Logs)
        self.right_pane = ttk.Frame(self.paned)
        self.paned.add(self.right_pane, weight=2)
        
        # Stats Panel
        self.stats_panel = StatsPanel(self.right_pane)
        self.stats_panel.pack(fill="x", pady=(0, 10))
        
        # Progress Panel
        self.progress_panel = ProgressPanel(self.right_pane)
        self.progress_panel.pack(fill="x", pady=(0, 10))
        
        # Log Panel
        self.log_panel = LogPanel(self.right_pane)
        self.log_panel.pack(fill="both", expand=True)

    def _setup_menu(self) -> None:
        menubar = tk.Menu(self)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Config...", command=self._load_config)
        file_menu.add_command(label="Save Config As...", command=self._save_config)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=lambda: dialogs.AboutDialog(self))
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.config(menu=menubar)

    # --- Actions ---

    def _browse_file(self) -> None:
        path = dialogs.select_credentials_file(self.file_var.get())
        if path:
            self.file_var.set(path)
            self.settings.credentials_file = path

    def _load_config(self) -> None:
        new_settings = dialogs.load_config_dialog()
        if new_settings:
            self.settings = new_settings
            self.config_panel.set_settings(self.settings)
            self.file_var.set(self.settings.credentials_file)

    def _save_config(self) -> None:
        self.settings = self.config_panel.get_settings()
        self.settings.credentials_file = self.file_var.get()
        dialogs.save_config_dialog(self.settings)

    def _handle_start(self) -> None:
        # Get latest settings from UI
        self.settings = self.config_panel.get_settings()
        self.settings.credentials_file = self.file_var.get()
        
        if self.on_start_cb:
            self.on_start_cb(self.settings)

    def _handle_pause(self) -> None:
        if self.on_pause_cb:
            self.on_pause_cb()

    def _handle_resume(self) -> None:
        if self.on_resume_cb:
            self.on_resume_cb()

    def _handle_stop(self) -> None:
        if dialogs.ask_yes_no("Stop", "Are you sure you want to stop processing?\nA checkpoint will be saved."):
            if self.on_stop_cb:
                self.on_stop_cb()

    def _on_closing(self) -> None:
        """Handle window close."""
        if self.control_bar.btn_start.cget("state") == "disabled":
            # Currently running or paused
            if not dialogs.ask_yes_no("Exit", "Process is running.\nAre you sure you want to exit?"):
                return
            if self.on_stop_cb:
                self.on_stop_cb()
        self.destroy()

    # --- Updates ---

    def update_state(self, state_name: str) -> None:
        """Called by app.py when session state changes."""
        # Must run in main thread
        self.after(0, self._update_state_ui, state_name)

    def _update_state_ui(self, state_name: str) -> None:
        self.control_bar.set_state(state_name)
        if state_name in ("IDLE", "STOPPED", "ERROR"):
            self.config_panel.enable_all()
        else:
            self.config_panel.disable_all()
            
        if state_name == "ERROR":
            dialogs.show_error("Error", "A fatal error occurred. Check logs for details.")

    def update_progress(self, stats: StatsSnapshot, format_eta: Callable, format_runtime: Callable) -> None:
        """Called periodically by app.py with fresh stats."""
        self.after(0, self._update_progress_ui, stats, format_eta, format_runtime)

    def _update_progress_ui(self, stats: StatsSnapshot, format_eta: Callable, format_runtime: Callable) -> None:
        self.stats_panel.update_stats(stats)
        self.progress_panel.update_progress(stats, format_eta, format_runtime)

    def _update_loop(self) -> None:
        """Periodic loop to process logs from the queue."""
        try:
            # Process up to 100 log messages per UI update
            for _ in range(100):
                level, msg = self.log_queue.get_nowait()
                self.log_panel.write_log(level, msg)
                self.log_queue.task_done()
        except queue.Empty:
            pass
        finally:
            # Schedule next update
            self.after(100, self._update_loop)
