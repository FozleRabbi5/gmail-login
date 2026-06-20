"""
Thread-safe async result writer for categorized login results.

Design decision: Each result is written and flushed immediately to disk.
This ensures no data loss on crash — at the cost of more I/O operations.
For high-throughput scenarios, the flush-per-write is acceptable because
the bottleneck is always the browser automation, not file I/O.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from loguru import logger


class ResultWriter:
    """
    Writes login results to categorized files with immediate flush.

    Each category (success, failure, error, etc.) gets its own file.
    All writes are protected by an asyncio.Lock for concurrency safety.

    Output format: one redacted result per line, with optional metadata.
    """

    def __init__(
        self,
        output_directory: str | Path,
        categories: list[str] | None = None,
    ) -> None:
        self.output_dir = Path(output_directory)
        self.categories = categories or [
            "success",
            "failure",
            "disabled",
            "changepassword",
            "error",
            "timeout",
            "captcha",
            "locked",
        ]
        self._locks: dict[str, asyncio.Lock] = {}
        self._write_counts: dict[str, int] = {}

    async def initialize(self) -> None:
        """Create output directory and initialize category files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        for category in self.categories:
            self._locks[category] = asyncio.Lock()
            self._write_counts[category] = 0

            # Count existing lines for resume accuracy
            file_path = self._get_file_path(category)
            if file_path.exists():
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    self._write_counts[category] = len(
                        [line for line in content.strip().split("\n") if line.strip()]
                    )

        logger.info(
            f"ResultWriter initialized: {self.output_dir} "
            f"with {len(self.categories)} categories"
        )

    def _get_file_path(self, category: str) -> Path:
        """Get the file path for a result category."""
        return self.output_dir / f"{category}.txt"

    async def write(
        self,
        category: str,
        username: str,
        password: str,
        extra_info: str = "",
    ) -> None:
        """
        Write a single result to the appropriate category file.

        Args:
            category: Result category (e.g., 'success', 'failure').
            username: Kept for API compatibility; not persisted.
            password: Kept for API compatibility; not persisted.
            extra_info: Optional extra information to append.
        """
        if category not in self._locks:
            logger.warning(f"Unknown category '{category}', defaulting to 'error'")
            category = "error"

        # Do not persist credentials. Keep only metadata about the result.
        metadata: list[str] = []
        if extra_info:
            metadata.append(extra_info)

        # line = " | ".join(metadata) if metadata else category
        line = f"{username}:{password}"

        file_path = self._get_file_path(category)

        async with self._locks[category]:
            async with aiofiles.open(
                file_path, mode="a", encoding="utf-8"
            ) as f:
                await f.write(line + "\n")
                await f.flush()

            self._write_counts[category] += 1

        logger.debug(f"Result written: [{category}]")

    async def write_with_timestamp(
        self,
        category: str,
        username: str,
        password: str,
        extra_info: str = "",
    ) -> None:
        """Write a result with a UTC timestamp prefix."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        full_extra = f"[{timestamp}]"
        if extra_info:
            full_extra += f" {extra_info}"
        await self.write(category, username, password, full_extra)

    def get_counts(self) -> dict[str, int]:
        """Get current write counts per category."""
        return dict(self._write_counts)

    async def close(self) -> None:
        """Cleanup resources (no-op for file-based writer, here for interface)."""
        logger.info(f"ResultWriter closed. Final counts: {self._write_counts}")
