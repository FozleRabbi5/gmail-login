"""
Dialog windows for the GUI.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any

from config.settings import Settings
from gui.themes import DarkTheme


def show_error(title: str, message: str) -> None:
    """Show an error dialog."""
    messagebox.showerror(title, message)


def show_info(title: str, message: str) -> None:
    """Show an info dialog."""
    messagebox.showinfo(title, message)


def ask_yes_no(title: str, message: str) -> bool:
    """Show a confirmation dialog. Returns True if Yes."""
    return messagebox.askyesno(title, message)


def select_credentials_file(current_path: str) -> str | None:
    """Open a file dialog to select the credentials file."""
    filepath = filedialog.askopenfilename(
        title="Select Credentials File",
        initialdir=".",
        initialfile=current_path,
        filetypes=[
            ("Text Files", "*.txt"),
            ("CSV Files", "*.csv"),
            ("All Files", "*.*")
        ]
    )
    return filepath if filepath else None


def save_config_dialog(settings: Settings) -> None:
    """Open a save dialog to export config."""
    filepath = filedialog.asksaveasfilename(
        title="Save Configuration",
        initialdir=".",
        defaultextension=".yaml",
        filetypes=[("YAML Files", "*.yaml"), ("All Files", "*.*")]
    )
    
    if filepath:
        try:
            settings.save(filepath)
            show_info("Success", f"Configuration saved to:\n{filepath}")
        except Exception as e:
            show_error("Error", f"Failed to save configuration:\n{e}")


def load_config_dialog() -> Settings | None:
    """Open an open dialog to import config."""
    filepath = filedialog.askopenfilename(
        title="Load Configuration",
        initialdir=".",
        filetypes=[("YAML Files", "*.yaml *.yml"), ("All Files", "*.*")]
    )
    
    if filepath:
        try:
            return Settings.load(filepath)
        except Exception as e:
            show_error("Error", f"Failed to load configuration:\n{e}")
    
    return None


class AboutDialog(tk.Toplevel):
    """Custom about dialog with dark theme."""
    
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.title("About Login Tester")
        self.geometry("400x300")
        self.resizable(False, False)
        self.configure(bg=DarkTheme.BG_ROOT)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 150
        self.geometry(f"+{x}+{y}")
        
        self._build_ui()
        
    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(
            frame, 
            text="Login Tester", 
            font=("Segoe UI", 24, "bold"), 
            foreground=DarkTheme.ACCENT
        ).pack(pady=(0, 10))
        
        ttk.Label(
            frame,
            text="Production Desktop Application",
            font=("Segoe UI", 12)
        ).pack(pady=(0, 20))
        
        info = (
            "Version: 1.0.0\n"
            "Framework: Playwright & Tkinter\n\n"
            "Disclaimer:\n"
            "This tool is strictly for testing systems\n"
            "you own or have explicit authorization to test."
        )
        
        ttk.Label(
            frame,
            text=info,
            justify="center",
            style="Dim.TLabel"
        ).pack(pady=(0, 20))
        
        ttk.Button(frame, text="Close", command=self.destroy).pack(side="bottom")
