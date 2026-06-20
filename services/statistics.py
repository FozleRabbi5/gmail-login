"""
Statistics tracker for real-time monitoring of login testing progress.

Design decision: Uses thread-safe operations since stats are updated
from async workers but read from the Tkinter main thread. All numeric
operations use simple attribute assignments which are atomic in CPython.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import psutil
from loguru import logger


@dataclass
class StatsSnapshot:
    """Immutable snapshot of current statistics for GUI display."""

    # Progress
    total_accounts: int = 0
    processed: int = 0
    remaining: int = 0
    percentage: float = 0.0

    # Results
    success: int = 0
    failure: int = 0
    disabled: int = 0
    changepassword: int = 0
    errors: int = 0
    timeouts: int = 0
    captcha: int = 0
    locked: int = 0

    # Workers
    running_workers: int = 0
    browser_count: int = 0

    # Performance
    avg_speed: float = 0.0  # checks per second
    eta_seconds: float = 0.0
    runtime_seconds: float = 0.0

    # System
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0

    # Queue
    queue_depth: int = 0


class StatisticsTracker:
    """
    Thread-safe statistics collection for real-time monitoring.

    Uses a rolling window for speed calculation (last 100 operations)
    and psutil for system resource monitoring.
    """

    def __init__(self, total_accounts: int = 0) -> None:
        self._lock = threading.Lock()

        # Progress
        self._total_accounts = total_accounts
        self._processed = 0

        # Results
        self._success = 0
        self._failure = 0
        self._disabled = 0
        self._changepassword = 0
        self._errors = 0
        self._timeouts = 0
        self._captcha = 0
        self._locked = 0

        # Workers
        self._running_workers = 0
        self._browser_count = 0

        # Performance tracking
        self._start_time: float | None = None
        self._speed_window: deque[float] = deque(maxlen=100)
        self._accumulated_runtime: float = 0.0

        # Queue
        self._queue_depth = 0

        # System process handle
        self._process = psutil.Process()

    def start(self) -> None:
        """Mark the start of processing."""
        self._start_time = time.monotonic()

    def pause(self) -> None:
        """Accumulate runtime on pause."""
        if self._start_time is not None:
            self._accumulated_runtime += time.monotonic() - self._start_time
            self._start_time = None

    def resume(self) -> None:
        """Resume timing."""
        self._start_time = time.monotonic()

    def set_total(self, total: int) -> None:
        """Set the total number of accounts to process."""
        with self._lock:
            self._total_accounts = total

    def record_result(self, category: str) -> None:
        """
        Record a single login test result.

        Args:
            category: Result category (success, failure, error, etc.)
        """
        with self._lock:
            self._processed += 1
            self._speed_window.append(time.monotonic())

            category_map = {
                "success": "_success",
                "failure": "_failure",
                "disabled": "_disabled",
                "changepassword": "_changepassword",
                "error": "_errors",
                "timeout": "_timeouts",
                "captcha": "_captcha",
                "locked": "_locked",
            }

            attr = category_map.get(category)
            if attr:
                setattr(self, attr, getattr(self, attr) + 1)
            else:
                self._errors += 1

    def set_worker_count(self, count: int) -> None:
        """Update the running worker count."""
        self._running_workers = count

    def set_browser_count(self, count: int) -> None:
        """Update the active browser count."""
        self._browser_count = count

    def set_queue_depth(self, depth: int) -> None:
        """Update the current queue depth."""
        self._queue_depth = depth

    def _calculate_speed(self) -> float:
        """Calculate rolling average speed (operations per second)."""
        if len(self._speed_window) < 2:
            return 0.0

        window = list(self._speed_window)
        time_span = window[-1] - window[0]
        if time_span <= 0:
            return 0.0

        return (len(window) - 1) / time_span

    def _calculate_eta(self, speed: float) -> float:
        """Calculate estimated time to completion in seconds."""
        with self._lock:
            remaining = self._total_accounts - self._processed
        if speed <= 0 or remaining <= 0:
            return 0.0
        return remaining / speed

    def _get_runtime(self) -> float:
        """Get total runtime in seconds."""
        active_time = 0.0
        if self._start_time is not None:
            active_time = time.monotonic() - self._start_time
        return self._accumulated_runtime + active_time

    def snapshot(self) -> StatsSnapshot:
        """
        Create an immutable snapshot of current statistics.

        This is called from the GUI thread, so it must be thread-safe.
        """
        with self._lock:
            processed = self._processed
            total = self._total_accounts
            remaining = max(0, total - processed)
            percentage = (processed / total * 100) if total > 0 else 0.0

            speed = self._calculate_speed()
            eta = self._calculate_eta(speed)
            runtime = self._get_runtime()

            # System metrics
            try:
                memory_mb = self._process.memory_info().rss / (1024 * 1024)
                cpu = self._process.cpu_percent(interval=0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                memory_mb = 0.0
                cpu = 0.0

            return StatsSnapshot(
                total_accounts=total,
                processed=processed,
                remaining=remaining,
                percentage=percentage,
                success=self._success,
                failure=self._failure,
                disabled=self._disabled,
                changepassword=self._changepassword,
                errors=self._errors,
                timeouts=self._timeouts,
                captcha=self._captcha,
                locked=self._locked,
                running_workers=self._running_workers,
                browser_count=self._browser_count,
                avg_speed=round(speed, 2),
                eta_seconds=round(eta, 1),
                runtime_seconds=round(runtime, 1),
                memory_usage_mb=round(memory_mb, 1),
                cpu_percent=round(cpu, 1),
                queue_depth=self._queue_depth,
            )

    def reset(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self._processed = 0
            self._success = 0
            self._failure = 0
            self._disabled = 0
            self._changepassword = 0
            self._errors = 0
            self._timeouts = 0
            self._captcha = 0
            self._locked = 0
            self._start_time = None
            self._accumulated_runtime = 0.0
            self._speed_window.clear()
            self._running_workers = 0
            self._browser_count = 0
            self._queue_depth = 0

    def load_from_state(
        self,
        processed: int,
        success: int,
        failure: int,
        errors: int,
        disabled: int = 0,
        changepassword: int = 0,
        timeouts: int = 0,
        captcha: int = 0,
        locked: int = 0,
        runtime: float = 0.0,
    ) -> None:
        """Load statistics from a saved state (for resume)."""
        with self._lock:
            self._processed = processed
            self._success = success
            self._failure = failure
            self._disabled = disabled
            self._changepassword = changepassword
            self._errors = errors
            self._timeouts = timeouts
            self._captcha = captcha
            self._locked = locked
            self._accumulated_runtime = runtime

        logger.info(f"Stats loaded from state: {processed} processed")
