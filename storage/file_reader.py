"""
Credential file reader with memory-efficient line-by-line streaming.

Design decision: Uses aiofiles for non-blocking I/O so the event loop
isn't blocked while reading large files. The reader never loads more than
one line into memory at a time, supporting multi-GB credential files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import aiofiles
from loguru import logger


@dataclass(frozen=True, slots=True)
class Credential:
    """A single username:password pair with its source line number."""

    username: str
    password: str
    line_number: int


class CredentialFileReader:
    """
    Async generator that reads credentials line-by-line from a file.

    Supports:
    - Memory-efficient streaming (one line at a time)
    - Seeking to a specific line (for resume after checkpoint)
    - Counting total lines without loading the file
    - Graceful handling of malformed lines

    Usage:
        reader = CredentialFileReader("config/credentials.txt")
        total = await reader.count_lines()
        async for credential in reader.read(start_line=100):
            process(credential)
    """

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self._total_lines: int | None = None

    async def count_lines(self) -> int:
        """
        Count total lines in the file efficiently.

        Uses byte-level reading to avoid loading the entire file.
        Caches the result for subsequent calls.
        """
        if self._total_lines is not None:
            return self._total_lines

        if not self.file_path.exists():
            logger.warning(f"Credentials file not found: {self.file_path}")
            self._total_lines = 0
            return 0

        count = 0
        async with aiofiles.open(self.file_path, mode="rb") as f:
            # Read in 64KB chunks for efficiency
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                count += chunk.count(b"\n")

        # Account for the last line if it doesn't end with newline
        if chunk and not chunk.endswith(b"\n"):
            count += 1

        self._total_lines = count
        logger.info(f"Counted {count} lines in {self.file_path}")
        return count

    def _parse_line(self, line: str, line_number: int) -> Credential | None:
        """
        Parse a single line into a Credential.

        Returns None for blank or malformed lines (logged as warnings).
        """
        line = line.strip()

        # Skip empty lines
        if not line:
            return None

        # Split on the FIRST colon only — passwords may contain colons
        parts = line.split(":", 1)

        if len(parts) != 2:
            logger.warning(
                f"Malformed line {line_number}: expected 'username:password' format"
            )
            return None

        username, password = parts
        username = username.strip()
        password = password.strip()

        if not username or not password:
            logger.warning(
                f"Empty username or password at line {line_number}"
            )
            return None

        return Credential(
            username=username,
            password=password,
            line_number=line_number,
        )

    async def read(self, start_line: int = 1):
        """
        Async generator yielding Credential objects line-by-line.

        Args:
            start_line: 1-indexed line number to start reading from.
                        Use for resume capability after checkpoint.

        Yields:
            Credential objects for each valid line.
        """
        if not self.file_path.exists():
            logger.error(f"Credentials file not found: {self.file_path}")
            return

        line_number = 0
        skipped = 0
        yielded = 0

        async with aiofiles.open(
            self.file_path, mode="r", encoding="utf-8", errors="replace"
        ) as f:
            async for line in f:
                line_number += 1

                # Skip lines before the start position (for resume)
                if line_number < start_line:
                    continue

                credential = self._parse_line(line, line_number)

                if credential is not None:
                    yielded += 1
                    yield credential
                else:
                    skipped += 1

        logger.info(
            f"File reading complete: {yielded} valid credentials, "
            f"{skipped} skipped, {line_number} total lines"
        )

    async def validate(self) -> tuple[bool, str]:
        """
        Validate the credentials file exists and is readable.

        Returns:
            Tuple of (is_valid, message).
        """
        if not self.file_path.exists():
            return False, f"File not found: {self.file_path}"

        if not os.access(self.file_path, os.R_OK):
            return False, f"File not readable: {self.file_path}"

        file_size = self.file_path.stat().st_size
        if file_size == 0:
            return False, "Credentials file is empty"

        return True, f"Valid ({file_size:,} bytes)"
