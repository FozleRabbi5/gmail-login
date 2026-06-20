"""
Worker scheduler for managing login worker lifecycle.

Design decision: Workers are asyncio tasks managed centrally. The scheduler
monitors their health and restarts any that crash unexpectedly. This provides
fault tolerance — a single browser crash won't stop the entire process.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from loguru import logger


class WorkerScheduler:
    """
    Manages the lifecycle of login worker coroutines.

    Features:
    - Dynamic worker start/stop
    - Health monitoring with automatic restart
    - Graceful drain on shutdown
    - Worker count tracking for statistics
    """

    def __init__(self, worker_count: int = 5) -> None:
        self._target_count = worker_count
        self._workers: dict[int, asyncio.Task] = {}
        self._worker_factory: Callable[
            [int], Coroutine[Any, Any, None]
        ] | None = None
        self._next_id = 0
        self._running = False
        self._monitor_task: asyncio.Task | None = None

    def set_worker_factory(
        self,
        factory: Callable[[int], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Set the factory function that creates worker coroutines.

        Args:
            factory: Async function that takes a worker_id and runs the worker loop.
        """
        self._worker_factory = factory

    async def start(self) -> None:
        """Start all workers and the health monitor."""
        if self._worker_factory is None:
            raise RuntimeError("Worker factory not set. Call set_worker_factory() first.")

        self._running = True

        # Start workers
        for _ in range(self._target_count):
            self._start_worker()

        # Start health monitor
        self._monitor_task = asyncio.create_task(self._monitor_health())

        logger.info(f"Scheduler started {self._target_count} workers")

    def _start_worker(self) -> int:
        """Start a single worker and return its ID."""
        worker_id = self._next_id
        self._next_id += 1

        task = asyncio.create_task(
            self._worker_factory(worker_id),
            name=f"worker-{worker_id}",
        )
        self._workers[worker_id] = task

        logger.debug(f"Worker {worker_id} started")
        return worker_id

    async def _monitor_health(self) -> None:
        """
        Background task that monitors worker health.

        Restarts crashed workers to maintain the target count.
        """
        while self._running:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds

                if not self._running:
                    break

                # Find and clean up finished workers
                finished = []
                for worker_id, task in self._workers.items():
                    if task.done():
                        finished.append(worker_id)
                        # Check for unexpected errors
                        if task.exception() is not None:
                            logger.error(
                                f"Worker {worker_id} crashed: {task.exception()}"
                            )
                        else:
                            logger.debug(f"Worker {worker_id} completed normally")

                for worker_id in finished:
                    del self._workers[worker_id]

                # Restart workers if below target and still running
                if self._running:
                    while len(self._workers) < self._target_count:
                        new_id = self._start_worker()
                        logger.info(f"Restarted worker as {new_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")

    async def stop(self, timeout: float = 30.0) -> None:
        """
        Stop all workers gracefully.

        Waits up to `timeout` seconds for workers to finish,
        then cancels any remaining workers.
        """
        self._running = False

        # Stop health monitor
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if not self._workers:
            return

        logger.info(f"Stopping {len(self._workers)} workers (timeout: {timeout}s)...")

        # Wait for workers to finish naturally (they should get poison pills)
        tasks = list(self._workers.values())
        done, pending = await asyncio.wait(tasks, timeout=timeout)

        # Cancel any workers that didn't finish in time
        if pending:
            logger.warning(f"Force-cancelling {len(pending)} workers")
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        self._workers.clear()
        logger.info("All workers stopped")

    @property
    def active_count(self) -> int:
        """Number of currently active workers."""
        return sum(1 for t in self._workers.values() if not t.done())

    @property
    def worker_ids(self) -> list[int]:
        """List of active worker IDs."""
        return [
            wid for wid, task in self._workers.items() if not task.done()
        ]
