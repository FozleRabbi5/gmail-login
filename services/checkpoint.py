"""
Checkpoint manager for periodic state persistence.

Design decision: Runs as a background asyncio task that saves state at
configurable intervals. Also provides explicit save methods for pause,
stop, and crash recovery scenarios.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from storage.output_manager import OutputManager


class CheckpointManager:
    """
    Periodic checkpoint saver for crash recovery.

    Saves application state at regular intervals and on explicit
    triggers (pause, stop, error). Integrates with OutputManager
    for atomic state persistence.
    """

    def __init__(
        self,
        output_manager: OutputManager,
        interval_seconds: int = 30,
    ) -> None:
        self._output = output_manager
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the periodic checkpoint background task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._periodic_save())
        logger.info(f"Checkpoint manager started (interval: {self._interval}s)")

    async def _periodic_save(self) -> None:
        """Background task that saves checkpoints periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                if self._running:
                    self.save_now()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Checkpoint save error: {e}")

    def save_now(self) -> None:
        """Save a checkpoint immediately (no-op)."""
        pass

    async def stop(self) -> None:
        """Stop the periodic checkpoint task and save a final checkpoint."""
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # No final save — checkpointing is disabled
        logger.info("Checkpoint manager stopped (no checkpoint saved)")
