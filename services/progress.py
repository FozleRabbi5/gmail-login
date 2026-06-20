"""
Progress tracker bridging statistics to GUI updates.

Design decision: Uses a callback-based approach for thread safety.
The Tkinter GUI registers a callback, and the progress tracker
calls it from its own update cycle. The callback is always invoked
with a StatsSnapshot (immutable dataclass) to avoid race conditions.
"""

from __future__ import annotations

from typing import Callable

from services.statistics import StatsSnapshot, StatisticsTracker


class ProgressTracker:
    """
    Bridges StatisticsTracker to GUI progress updates.

    Provides formatted display values and callback-based updates.
    """

    def __init__(self, stats: StatisticsTracker) -> None:
        self._stats = stats
        self._callbacks: list[Callable[[StatsSnapshot], None]] = []

    def register_callback(
        self, callback: Callable[[StatsSnapshot], None]
    ) -> None:
        """Register a callback to receive progress updates."""
        self._callbacks.append(callback)

    def unregister_callback(
        self, callback: Callable[[StatsSnapshot], None]
    ) -> None:
        """Remove a previously registered callback."""
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    def update(self) -> StatsSnapshot:
        """
        Get current snapshot and notify all callbacks.

        Returns:
            Current StatsSnapshot.
        """
        snapshot = self._stats.snapshot()

        for callback in self._callbacks:
            try:
                callback(snapshot)
            except Exception:
                pass  # GUI callbacks should not crash the tracker

        return snapshot

    @staticmethod
    def format_eta(seconds: float) -> str:
        """Format ETA seconds into human-readable string."""
        if seconds <= 0:
            return "N/A"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    @staticmethod
    def format_runtime(seconds: float) -> str:
        """Format runtime seconds into human-readable string."""
        if seconds <= 0:
            return "0s"

        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")

        return " ".join(parts)

    @staticmethod
    def format_speed(speed: float) -> str:
        """Format speed into human-readable string."""
        if speed <= 0:
            return "0.00/s"
        return f"{speed:.2f}/s"

    @staticmethod
    def format_memory(mb: float) -> str:
        """Format memory usage into human-readable string."""
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb:.0f} MB"
