"""
Session manager — orchestrates the entire automation pipeline.

Initializes all components, manages the async event loop, coordinates
startup/shutdown, and bridges the GUI thread with the async worker thread.
"""

from __future__ import annotations

import asyncio
import threading
import time
from enum import Enum, auto
from typing import Callable

from loguru import logger

from automation.browser_pool import BrowserPool
from automation.detector import CompositeDetector
from automation.login_worker import LoginWorker
from automation.navigation import NavigationHelper
from config.settings import Settings
from services.checkpoint import CheckpointManager
from services.queue_manager import QueueManager
from services.scheduler import WorkerScheduler
from services.statistics import StatisticsTracker
from storage.file_reader import CredentialFileReader
from storage.output_manager import OutputManager


class SessionState(Enum):
    """Current state of the automation session."""
    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


class SessionManager:
    """
    Orchestrates the full login testing pipeline.

    Manages the lifecycle of all components:
    - BrowserPool (browser instances)
    - QueueManager (credential queue)
    - WorkerScheduler (login workers)
    - CheckpointManager (state persistence)
    - OutputManager (results + state)

    Runs in a dedicated thread with its own asyncio event loop.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = SessionState.IDLE
        self._state_callbacks: list[Callable[[SessionState], None]] = []

        # Components (initialized on start)
        self._browser_pool: BrowserPool | None = None
        self._queue_manager: QueueManager | None = None
        self._scheduler: WorkerScheduler | None = None
        self._checkpoint: CheckpointManager | None = None
        self._output: OutputManager | None = None
        self._stats: StatisticsTracker | None = None
        self._reader: CredentialFileReader | None = None

        # Thread management
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def stats(self) -> StatisticsTracker | None:
        return self._stats

    def on_state_change(self, callback: Callable[[SessionState], None]) -> None:
        """Register a callback for state changes."""
        self._state_callbacks.append(callback)

    def _set_state(self, new_state: SessionState) -> None:
        old = self._state
        self._state = new_state
        logger.info(f"Session state: {old.name} -> {new_state.name}")
        for cb in self._state_callbacks:
            try:
                cb(new_state)
            except Exception:
                pass

    def start(self) -> None:
        """Start the automation session in a background thread."""
        if self._state not in (SessionState.IDLE, SessionState.STOPPED, SessionState.ERROR):
            logger.warning(f"Cannot start from state {self._state.name}")
            return

        self._set_state(SessionState.STARTING)
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="automation-thread",
            daemon=True,
        )
        self._thread.start()

    def _run_event_loop(self) -> None:
        """Create and run the async event loop in the background thread."""
        # On Windows, background threads default to SelectorEventLoop which does NOT
        # support subprocesses. Playwright requires ProactorEventLoop to communicate
        # with the browser process via subprocess pipes.
        import sys
        if sys.platform == "win32":
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            logger.error(f"Event loop error: {e}")
            self._set_state(SessionState.ERROR)
        finally:
            self._loop.close()
            self._loop = None

    async def _async_main(self) -> None:
        """Main async entry point — initializes and runs all components."""
        try:
            await self._initialize()
            self._set_state(SessionState.RUNNING)
            self._stats.start()

            # Start all components
            await self._checkpoint.start()
            await self._queue_manager.start_producer(
                start_line=1  # Always start from the first line — no resume/cache
            )
            await self._scheduler.start()

            # Wait for completion (workers will finish when queue is drained)
            await self._wait_for_completion()

        except asyncio.CancelledError:
            logger.info("Session cancelled")
        except Exception as e:
            logger.error(f"Session error: {e}")
            self._set_state(SessionState.ERROR)
        finally:
            await self._cleanup()

    async def _initialize(self) -> None:
        """Initialize all components."""
        s = self._settings

        # File reader
        self._reader = CredentialFileReader(s.credentials_file)
        total_lines = await self._reader.count_lines()

        # Statistics
        self._stats = StatisticsTracker(total_accounts=total_lines)

        # Output manager
        self._output = OutputManager(
            base_directory=".",
            output_directory=s.output_directory,
            categories=s.result_categories,
        )
        state = await self._output.initialize()

        # Always start fresh — clear any saved checkpoint so every run
        # begins from line 1 with zeroed statistics.
        self._output.state_manager.clear()
        state = self._output.state_manager.state  # fresh empty state

        logger.info("Starting fresh run from line 1 (no resume/cache)")

        # Update state with total lines
        self._output.state_manager.update(total_lines=total_lines)

        # Browser pool
        self._browser_pool = BrowserPool(
            max_contexts=s.worker_count,
            headless=s.headless,
            browser_type=s.browser_type,
            viewport_width=s.viewport_width,
            viewport_height=s.viewport_height,
        )
        await self._browser_pool.start()

        # Queue manager
        self._queue_manager = QueueManager(
            reader=self._reader,
            max_size=s.queue_max_size,
            worker_count=s.worker_count,
        )

        # Detector
        detector = CompositeDetector.from_config(
            success_indicators=s.success_indicators,
            failure_indicators=s.failure_indicators,
        )

        # Navigator
        navigator = NavigationHelper(
            login_url=s.login_url,
            username_selector=s.username_selector,
            password_selector=s.password_selector,
            submit_selector=s.submit_selector,
            timeout=s.timeout,
            multi_step=s.multi_step_login,
        )

        # Login worker factory
        login_worker = LoginWorker(
            browser_pool=self._browser_pool,
            queue_manager=self._queue_manager,
            detector=detector,
            navigator=navigator,
            output_manager=self._output,
            stats=self._stats,
            retry_count=s.retry_count,
            timeout=s.timeout,
        )

        # Worker scheduler
        self._scheduler = WorkerScheduler(worker_count=s.worker_count)
        self._scheduler.set_worker_factory(login_worker.run)

        # Checkpoint manager
        self._checkpoint = CheckpointManager(
            output_manager=self._output,
            interval_seconds=s.checkpoint_interval,
        )

        logger.info("All components initialized")

    async def _wait_for_completion(self) -> None:
        """Wait for all workers to finish processing."""
        while self._state == SessionState.RUNNING:
            if self._queue_manager and self._queue_manager.is_finished:
                if self._scheduler and self._scheduler.active_count == 0:
                    logger.info("All credentials processed")
                    break

            # Update stats for GUI
            if self._stats and self._browser_pool and self._scheduler:
                self._stats.set_browser_count(self._browser_pool.active_contexts)
                self._stats.set_worker_count(self._scheduler.active_count)
                if self._queue_manager:
                    self._stats.set_queue_depth(
                        self._queue_manager.get_stats().current_size
                    )

            await asyncio.sleep(0.5)

    async def _cleanup(self) -> None:
        """Clean up all components."""
        logger.info("Cleaning up session...")

        # Save runtime to state
        if self._output and self._stats:
            snapshot = self._stats.snapshot()
            self._output.state_manager.update(
                total_runtime_seconds=snapshot.runtime_seconds
            )

        if self._checkpoint:
            await self._checkpoint.stop()

        if self._scheduler:
            await self._scheduler.stop(timeout=15.0)

        if self._queue_manager:
            await self._queue_manager.stop()

        if self._browser_pool:
            await self._browser_pool.stop()

        if self._output:
            await self._output.close()

        if self._state != SessionState.ERROR:
            self._set_state(SessionState.STOPPED)

        logger.info("Session cleanup complete")

    def pause(self) -> None:
        """Pause the session."""
        if self._state != SessionState.RUNNING:
            return
        self._set_state(SessionState.PAUSED)
        if self._queue_manager:
            self._queue_manager.pause()
        if self._stats:
            self._stats.pause()
        if self._checkpoint:
            self._checkpoint.save_now()

    def resume(self) -> None:
        """Resume a paused session."""
        if self._state != SessionState.PAUSED:
            return
        self._set_state(SessionState.RUNNING)
        if self._queue_manager:
            self._queue_manager.resume()
        if self._stats:
            self._stats.resume()

    def stop(self) -> None:
        """Stop the session gracefully."""
        if self._state not in (SessionState.RUNNING, SessionState.PAUSED):
            return

        self._set_state(SessionState.STOPPING)

        if self._loop and self._loop.is_running():
            # Schedule cleanup in the event loop
            asyncio.run_coroutine_threadsafe(
                self._shutdown(), self._loop
            )

    async def _shutdown(self) -> None:
        """Async shutdown triggered from the main thread."""
        if self._queue_manager:
            await self._queue_manager.stop()
        # The _async_main will then proceed to cleanup

    def update_settings(self, settings: Settings) -> None:
        """Update settings (only effective before start)."""
        if self._state not in (SessionState.IDLE, SessionState.STOPPED):
            logger.warning("Cannot update settings while running")
            return
        self._settings = settings
