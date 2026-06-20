"""
Queue manager with producer-consumer pattern and backpressure.

Design decision: Uses a bounded asyncio.Queue to limit memory usage.
The producer reads credentials lazily from disk and enqueues them,
while workers consume from the queue. Backpressure is automatic —
when the queue is full, the producer blocks until workers consume items.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger

from storage.file_reader import Credential, CredentialFileReader


# Sentinel value to signal workers to shut down
POISON_PILL = None


@dataclass
class QueueStats:
    """Snapshot of queue state for monitoring."""
    current_size: int = 0
    max_size: int = 0
    total_enqueued: int = 0
    total_dequeued: int = 0
    is_producing: bool = False
    is_finished: bool = False


class QueueManager:
    """
    Manages an asyncio.Queue with producer-consumer pattern.

    Features:
    - Bounded queue with configurable max size for memory control
    - Lazy producer that reads credentials on-demand from disk
    - Pause/resume support for the producer
    - Poison pill pattern for clean worker shutdown
    - Real-time queue depth monitoring

    Usage:
        qm = QueueManager(reader, max_size=1000)
        await qm.start_producer(start_line=1)

        # In workers:
        credential = await qm.get()
        if credential is POISON_PILL:
            break  # Shutdown signal
    """

    def __init__(
        self,
        reader: CredentialFileReader,
        max_size: int = 1000,
        worker_count: int = 5,
    ) -> None:
        self._reader = reader
        self._queue: asyncio.Queue[Credential | None] = asyncio.Queue(
            maxsize=max_size
        )
        self._max_size = max_size
        self._worker_count = worker_count

        # Control flags
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Start in un-paused state
        self._stop_event = asyncio.Event()
        self._producer_task: asyncio.Task | None = None

        # Stats
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._is_producing = False
        self._is_finished = False

    async def start_producer(self, start_line: int = 1) -> None:
        """
        Start the producer coroutine that feeds credentials into the queue.

        Args:
            start_line: Line number to start reading from (for resume).
        """
        if self._producer_task and not self._producer_task.done():
            logger.warning("Producer already running")
            return

        self._stop_event.clear()
        self._is_finished = False
        self._producer_task = asyncio.create_task(
            self._produce(start_line)
        )
        logger.info(f"Producer started from line {start_line}")

    async def _produce(self, start_line: int) -> None:
        """Producer coroutine: reads credentials and enqueues them."""
        self._is_producing = True

        try:
            async for credential in self._reader.read(start_line=start_line):
                # Check for stop signal
                if self._stop_event.is_set():
                    logger.info("Producer stopped by stop signal")
                    break

                # Wait if paused
                await self._pause_event.wait()

                # Enqueue (blocks if queue is full — backpressure)
                await self._queue.put(credential)
                self._total_enqueued += 1

                if self._total_enqueued % 1000 == 0:
                    logger.info(
                        f"Producer: {self._total_enqueued} credentials enqueued, "
                        f"queue depth: {self._queue.qsize()}"
                    )

        except Exception as e:
            logger.error(f"Producer error: {e}")
        finally:
            self._is_producing = False

            # Send poison pills to all workers
            if not self._stop_event.is_set():
                for _ in range(self._worker_count):
                    await self._queue.put(POISON_PILL)
                logger.info(
                    f"Producer finished: {self._total_enqueued} total enqueued, "
                    f"sent {self._worker_count} poison pills"
                )

            self._is_finished = True

    async def get(self) -> Credential | None:
        """
        Get the next credential from the queue.

        Returns:
            A Credential, or None (poison pill) signaling shutdown.
        """
        item = await self._queue.get()
        if item is not POISON_PILL:
            self._total_dequeued += 1
        self._queue.task_done()
        return item

    def pause(self) -> None:
        """Pause the producer (workers continue draining the queue)."""
        self._pause_event.clear()
        logger.info("Producer paused")

    def resume(self) -> None:
        """Resume the producer."""
        self._pause_event.set()
        logger.info("Producer resumed")

    async def stop(self) -> None:
        """Stop the producer and send poison pills to all workers."""
        self._stop_event.set()
        self._pause_event.set()  # Unpause so producer can exit

        # Send poison pills to unblock waiting workers
        for _ in range(self._worker_count):
            try:
                self._queue.put_nowait(POISON_PILL)
            except asyncio.QueueFull:
                # Queue is full, worker will eventually get a poison pill
                break

        if self._producer_task and not self._producer_task.done():
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        logger.info("QueueManager stopped")

    def get_stats(self) -> QueueStats:
        """Get current queue statistics."""
        return QueueStats(
            current_size=self._queue.qsize(),
            max_size=self._max_size,
            total_enqueued=self._total_enqueued,
            total_dequeued=self._total_dequeued,
            is_producing=self._is_producing,
            is_finished=self._is_finished,
        )

    @property
    def is_finished(self) -> bool:
        """Whether the producer has finished and the queue is drained."""
        return self._is_finished and self._queue.empty()
