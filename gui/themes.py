"""
Theme definitions and styling for the Tkinter UI.

Implements a modern dark mode theme using ttk.Style.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class DarkTheme:
    """Dark mode color palette and styles for ttk."""

    # Color Palette
    BG_ROOT = "#1a1a2e"        # Deep dark blue/purple background
    BG_FRAME = "#16213e"       # Slightly lighter dark background
    BG_INPUT = "#0f3460"       # Accent dark blue for inputs
    FG_TEXT = "#e1e1e6"        # Off-white text
    FG_DIM = "#8b9bb4"         # Dimmed text
    
    ACCENT = "#e94560"         # Red/Pink accent
    ACCENT_HOVER = "#d13c55"   # Darker accent for hover
    
    SUCCESS = "#4caf50"        # Green
    ERROR = "#f44336"          # Red
    WARNING = "#ff9800"        # Orange
    INFO = "#2196f3"           # Blue

    # Fonts
    FONT_DEFAULT = ("Segoe UI", 10)
    FONT_HEADING = ("Segoe UI", 12, "bold")
    FONT_MONO = ("Consolas", 10)
    FONT_LARGE = ("Segoe UI", 16, "bold")

    @classmethod
    def apply(cls, root: tk.Tk) -> None:
        """Apply the dark theme to the root window and configure ttk styles."""
        root.configure(bg=cls.BG_ROOT)

        style = ttk.Style(root)
        
        # Use 'clam' theme as a base because it's highly customizable
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # --- Base Styles ---
        style.configure(
            ".",
            background=cls.BG_ROOT,
            foreground=cls.FG_TEXT,
            font=cls.FONT_DEFAULT,
            troughcolor=cls.BG_INPUT,
            selectbackground=cls.ACCENT,
            selectforeground=cls.FG_TEXT,
            fieldbackground=cls.BG_INPUT,
            insertcolor=cls.FG_TEXT,
        )

        # --- Frames & Labelframes ---
        style.configure("TFrame", background=cls.BG_ROOT)
        style.configure(
            "TLabelframe",
            background=cls.BG_ROOT,
            foreground=cls.ACCENT,
            bordercolor=cls.BG_INPUT,
            darkcolor=cls.BG_ROOT,
            lightcolor=cls.BG_ROOT,
            relief="solid",
            borderwidth=1,
        )
        style.configure("TLabelframe.Label", font=cls.FONT_HEADING)

        # --- Buttons ---
        style.configure(
            "TButton",
            background=cls.BG_INPUT,
            foreground=cls.FG_TEXT,
            bordercolor=cls.BG_ROOT,
            focuscolor=cls.ACCENT,
            padding=(10, 5),
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", cls.ACCENT), ("disabled", cls.BG_FRAME)],
            foreground=[("disabled", cls.FG_DIM)],
        )

        # Primary Button (Accent color)
        style.configure(
            "Primary.TButton",
            background=cls.ACCENT,
            foreground="#ffffff",
        )
        style.map(
            "Primary.TButton",
            background=[("active", cls.ACCENT_HOVER), ("disabled", cls.BG_FRAME)],
        )

        # --- Inputs ---
        style.configure(
            "TEntry",
            fieldbackground=cls.BG_FRAME,
            foreground=cls.FG_TEXT,
            bordercolor=cls.BG_INPUT,
            padding=5,
        )
        
        style.configure(
            "TCombobox",
            fieldbackground=cls.BG_FRAME,
            background=cls.BG_INPUT,
            foreground=cls.FG_TEXT,
            arrowcolor=cls.FG_TEXT,
        )
        
        style.configure(
            "TSpinbox",
            fieldbackground=cls.BG_FRAME,
            background=cls.BG_INPUT,
            foreground=cls.FG_TEXT,
            arrowcolor=cls.FG_TEXT,
        )

        # --- Labels ---
        style.configure("TLabel", background=cls.BG_ROOT)
        
        style.configure(
            "Dim.TLabel",
            foreground=cls.FG_DIM,
            font=("Segoe UI", 9)
        )
        
        style.configure(
            "MetricValue.TLabel",
            font=cls.FONT_LARGE,
        )
        
        style.configure(
            "Success.TLabel",
            foreground=cls.SUCCESS,
            font=cls.FONT_LARGE,
        )
        
        style.configure(
            "Error.TLabel",
            foreground=cls.ERROR,
            font=cls.FONT_LARGE,
        )

        # --- Progressbar ---
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=cls.BG_FRAME,
            background=cls.ACCENT,
            bordercolor=cls.BG_ROOT,
            thickness=15,
        )

        # --- PanedWindow ---
        style.configure(
            "Sash",
            background=cls.BG_INPUT,
            bordercolor=cls.BG_ROOT,
            sashthickness=4,
        )
