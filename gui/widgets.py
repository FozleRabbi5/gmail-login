"""
GUI Widgets for the Login Tester application.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Callable, Any

from config.settings import Settings
from services.statistics import StatsSnapshot
from gui.themes import DarkTheme


class ConfigPanel(ttk.LabelFrame):
    """Panel for editing configuration settings."""

    def __init__(self, parent: tk.Widget, settings: Settings) -> None:
        super().__init__(parent, text="Configuration", padding=10)
        self._settings = settings
        self._vars: dict[str, tk.Variable] = {}
        
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the configuration form."""
        row = 0
        
        # Helper to create labeled inputs
        def add_entry(name: str, key: str, default: str) -> None:
            nonlocal row
            ttk.Label(self, text=name).grid(row=row, column=0, sticky="w", pady=(0, 5))
            var = tk.StringVar(value=default)
            entry = ttk.Entry(self, textvariable=var, width=40)
            entry.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=(0, 5))
            self._vars[key] = var
            row += 1

        def add_spinbox(name: str, key: str, default: int, from_: int, to: int) -> None:
            nonlocal row
            ttk.Label(self, text=name).grid(row=row, column=0, sticky="w", pady=(0, 5))
            var = tk.IntVar(value=default)
            spin = ttk.Spinbox(self, textvariable=var, from_=from_, to=to, width=10)
            spin.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=(0, 5))
            self._vars[key] = var
            row += 1

        def add_combo(name: str, key: str, default: str, values: list[str]) -> None:
            nonlocal row
            ttk.Label(self, text=name).grid(row=row, column=0, sticky="w", pady=(0, 5))
            var = tk.StringVar(value=default)
            combo = ttk.Combobox(self, textvariable=var, values=values, state="readonly", width=15)
            combo.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=(0, 5))
            self._vars[key] = var
            row += 1

        def add_check(name: str, key: str, default: bool) -> None:
            nonlocal row
            var = tk.BooleanVar(value=default)
            check = ttk.Checkbutton(self, text=name, variable=var)
            check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 5))
            self._vars[key] = var
            row += 1

        # Target Settings
        ttk.Label(self, text="Target", font=("Segoe UI", 10, "bold"), foreground=DarkTheme.ACCENT).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        
        add_entry("Login URL:", "login_url", self._settings.login_url)
        add_entry("Username Selector:", "username_selector", self._settings.username_selector)
        add_entry("Password Selector:", "password_selector", self._settings.password_selector)
        add_entry("Submit Selector:", "submit_selector", self._settings.submit_selector)
        add_check("Multi-step Login Flow (e.g. Google)", "multi_step_login", self._settings.multi_step_login)
        
        # Engine Settings
        ttk.Label(self, text="Engine", font=("Segoe UI", 10, "bold"), foreground=DarkTheme.ACCENT).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1
        
        add_spinbox("Worker Count:", "worker_count", self._settings.worker_count, 1, 100)
        add_spinbox("Timeout (s):", "timeout", self._settings.timeout, 5, 300)
        add_spinbox("Retries:", "retry_count", self._settings.retry_count, 0, 10)
        add_combo("Browser Type:", "browser_type", self._settings.browser_type, ["chromium", "firefox", "webkit"])
        add_check("Headless Mode", "headless", self._settings.headless)
        
        self.columnconfigure(1, weight=1)

    def get_settings(self) -> Settings:
        """Get updated settings from UI."""
        # Update current settings object with UI values
        s = self._settings
        s.login_url = self._vars["login_url"].get()
        s.username_selector = self._vars["username_selector"].get()
        s.password_selector = self._vars["password_selector"].get()
        s.submit_selector = self._vars["submit_selector"].get()
        s.multi_step_login = self._vars["multi_step_login"].get()
        
        s.worker_count = self._vars["worker_count"].get()
        s.timeout = self._vars["timeout"].get()
        s.retry_count = self._vars["retry_count"].get()
        s.browser_type = self._vars["browser_type"].get()
        s.headless = self._vars["headless"].get()
        
        return s

    def set_settings(self, settings: Settings) -> None:
        """Update UI to match settings object."""
        self._settings = settings
        
        self._vars["login_url"].set(settings.login_url)
        self._vars["username_selector"].set(settings.username_selector)
        self._vars["password_selector"].set(settings.password_selector)
        self._vars["submit_selector"].set(settings.submit_selector)
        self._vars["multi_step_login"].set(settings.multi_step_login)
        
        self._vars["worker_count"].set(settings.worker_count)
        self._vars["timeout"].set(settings.timeout)
        self._vars["retry_count"].set(settings.retry_count)
        self._vars["browser_type"].set(settings.browser_type)
        self._vars["headless"].set(settings.headless)

    def disable_all(self) -> None:
        """Disable all inputs while running."""
        for child in self.winfo_children():
            try:
                child.configure(state="disabled")
            except tk.TclError:
                pass

    def enable_all(self) -> None:
        """Enable all inputs when stopped."""
        for child in self.winfo_children():
            try:
                # Comboboxes should be readonly, not normal
                if isinstance(child, ttk.Combobox):
                    child.configure(state="readonly")
                else:
                    child.configure(state="normal")
            except tk.TclError:
                pass


class StatsPanel(ttk.LabelFrame):
    """Panel for displaying real-time statistics."""

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, text="Statistics", padding=10)
        self._labels: dict[str, ttk.Label] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the statistics grid."""
        metrics = [
            # Group 1: Progress
            [("Total", "total_accounts"), ("Processed", "processed"), ("Remaining", "remaining")],
            # Group 2: Results
            [("Success", "success"), ("Failure", "failure"), ("Errors", "errors")],
            # Group 3: Categories
            [("Timeouts", "timeouts"), ("Captcha", "captcha"), ("Locked", "locked")],
            # Group 4: Performance
            [("Speed (/s)", "avg_speed"), ("Workers", "running_workers"), ("Browsers", "browser_count")],
            # Group 5: System
            [("Queue", "queue_depth"), ("Memory (MB)", "memory_usage_mb"), ("CPU %", "cpu_percent")]
        ]

        for row_idx, row_metrics in enumerate(metrics):
            for col_idx, (name, key) in enumerate(row_metrics):
                frame = ttk.Frame(self)
                frame.grid(row=row_idx, column=col_idx, sticky="nsew", padx=10, pady=5)
                
                ttk.Label(frame, text=name, style="Dim.TLabel").pack(anchor="w")
                
                # Determine style based on metric
                style = "MetricValue.TLabel"
                if key == "success":
                    style = "Success.TLabel"
                elif key in ("failure", "errors", "timeouts"):
                    style = "Error.TLabel"
                    
                value_label = ttk.Label(frame, text="0", style=style)
                value_label.pack(anchor="w")
                
                self._labels[key] = value_label

        for i in range(3):
            self.columnconfigure(i, weight=1)

    def update_stats(self, stats: StatsSnapshot) -> None:
        """Update labels with new statistics."""
        for key, label in self._labels.items():
            if hasattr(stats, key):
                val = getattr(stats, key)
                # Format floats
                if isinstance(val, float):
                    label.config(text=f"{val:.1f}")
                else:
                    label.config(text=str(val))


class ProgressPanel(ttk.Frame):
    """Panel with progress bar and ETA."""

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, padding=10)
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        
        info_frame = ttk.Frame(self)
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        self.pct_label = ttk.Label(info_frame, text="0.0%", font=("Segoe UI", 12, "bold"), foreground=DarkTheme.ACCENT)
        self.pct_label.pack(side="left")
        
        self.eta_label = ttk.Label(info_frame, text="ETA: N/A | Runtime: 0s", style="Dim.TLabel")
        self.eta_label.pack(side="right")
        
        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew")

    def update_progress(self, stats: StatsSnapshot, format_eta: Callable, format_runtime: Callable) -> None:
        """Update progress bar and labels."""
        self.progress["value"] = stats.percentage
        self.pct_label.config(text=f"{stats.percentage:.1f}%")
        
        eta_str = format_eta(stats.eta_seconds)
        runtime_str = format_runtime(stats.runtime_seconds)
        self.eta_label.config(text=f"ETA: {eta_str} | Runtime: {runtime_str}")


class ControlBar(ttk.Frame):
    """Panel with action buttons."""

    def __init__(
        self, 
        parent: tk.Widget, 
        on_start: Callable[[], None],
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=10)
        
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_stop = on_stop
        
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure((0, 1), weight=1)
        
        self.btn_start = ttk.Button(self, text="Start", style="Primary.TButton", command=self.on_start)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.btn_pause = ttk.Button(self, text="Pause", command=self.on_pause, state="disabled")
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        
        self.btn_stop = ttk.Button(self, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def set_state(self, state: str) -> None:
        """Update button states based on application state."""
        if state == "IDLE" or state == "STOPPED" or state == "ERROR":
            self.btn_start.config(text="Start", state="normal")
            self.btn_pause.config(text="Pause", state="disabled")
            self.btn_stop.config(state="disabled")
            
        elif state == "RUNNING":
            self.btn_start.config(state="disabled")
            self.btn_pause.config(text="Pause", state="normal", command=self.on_pause)
            self.btn_stop.config(state="normal")
            
        elif state == "PAUSED":
            self.btn_start.config(state="disabled")
            self.btn_pause.config(text="Resume", state="normal", command=self.on_resume)
            self.btn_stop.config(state="normal")
            
        elif state in ("STARTING", "STOPPING"):
            self.btn_start.config(state="disabled")
            self.btn_pause.config(state="disabled")
            self.btn_stop.config(state="disabled")


class LogPanel(ttk.LabelFrame):
    """Panel for displaying live logs."""

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, text="Log Output", padding=10)
        self._build_ui()

    def _build_ui(self) -> None:
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        
        self.text = scrolledtext.ScrolledText(
            self, 
            wrap="word", 
            font=DarkTheme.FONT_MONO,
            bg=DarkTheme.BG_FRAME,
            fg=DarkTheme.FG_TEXT,
            insertbackground=DarkTheme.FG_TEXT,
            state="disabled",
            height=10
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        
        # Configure tags for color-coded logs
        self.text.tag_config("DEBUG", foreground=DarkTheme.FG_DIM)
        self.text.tag_config("INFO", foreground=DarkTheme.INFO)
        self.text.tag_config("WARNING", foreground=DarkTheme.WARNING)
        self.text.tag_config("ERROR", foreground=DarkTheme.ERROR, font=(DarkTheme.FONT_MONO[0], 10, "bold"))
        self.text.tag_config("CRITICAL", foreground="#ffffff", background=DarkTheme.ERROR, font=(DarkTheme.FONT_MONO[0], 10, "bold"))

    def write_log(self, level: str, message: str) -> None:
        """Write a log message to the text widget."""
        self.text.configure(state="normal")
        
        # Truncate if too long (prevent memory bloat)
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > 5000:
            self.text.delete("1.0", "1000.0")
            
        # Determine tag
        tag = level.upper() if level.upper() in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL") else ""
        
        self.text.insert("end", f"{message}\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")
