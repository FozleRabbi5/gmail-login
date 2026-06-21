"""
State manager for checkpoint/resume capability.

Design decision: Uses atomic file writes (write-to-temp + rename) to prevent
corruption from crashes during writes. The state file is a simple JSON
document that can be manually inspected and edited if needed.
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from loguru import logger


@dataclass
class ApplicationState:
    """Serializable application state for checkpoint/resume."""

    # Progress tracking
    last_processed_line: int = 0
    total_processed: int = 0
    total_lines: int = 0

    # Result counts
    success_count: int = 0
    failure_count: int = 0
    disabled_count: int = 0
    changepassword_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    captcha_count: int = 0
    locked_count: int = 0
    unknown_count: int = 0
    codeverify_count: int = 0
    numberverify_count: int = 0
    phoneveryify_count: int = 0
    valid_mail_to_count: int = 0
    deleted_count: int = 0

    # Timing
    start_time: float = 0.0
    total_runtime_seconds: float = 0.0
    last_checkpoint_time: float = 0.0

    # Configuration snapshot (for validation on resume)
    config_hash: str = ""
    credentials_file: str = ""

    # Category counts (flexible)
    category_counts: dict[str, int] = field(default_factory=dict)


class StateManager:
    """
    Persists and loads application state for checkpoint/resume.

    Features:
    - Atomic writes using temp-file + rename pattern
    - Validates state integrity on load
    - Thread-safe via file-level operations
    - Human-readable JSON format
    """

    STATE_FILE = "state.json"
    STATE_DIR = "state"

    def __init__(self, base_directory: str | Path) -> None:
        self.base_dir = Path(base_directory)
        self.state_dir = self.base_dir / self.STATE_DIR
        self.state_file = self.state_dir / self.STATE_FILE
        self._state = ApplicationState()

    @property
    def state(self) -> ApplicationState:
        """Current application state."""
        return self._state

    def initialize(self) -> None:
        """Create state directory if it doesn't exist."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """
        Save current state to disk using atomic write.

        Atomic write pattern: write to temp file in the same directory,
        then rename. This ensures the state file is never in a
        half-written state, even if the process crashes mid-write.
        """
        self._state.last_checkpoint_time = time.time()

        data = asdict(self._state)

        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)

            # Write to temp file first (same directory for atomic rename)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.state_dir),
                prefix="state_",
                suffix=".tmp",
            )

            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                # Atomic rename (same filesystem guarantees atomicity on Linux/POSIX)
                Path(tmp_path).replace(self.state_file)

            except Exception:
                # Clean up temp file on error
                Path(tmp_path).unlink(missing_ok=True)
                raise

            logger.debug(
                f"State saved: line {self._state.last_processed_line}, "
                f"processed {self._state.total_processed}"
            )

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    def load(self) -> ApplicationState:
        """
        Load state from disk.

        Returns:
            Loaded ApplicationState, or a fresh state if no checkpoint exists.
        """
        if not self.state_file.exists():
            logger.info("No checkpoint found, starting fresh")
            self._state = ApplicationState()
            return self._state

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._state = ApplicationState(**data)

            logger.info(
                f"Checkpoint loaded: line {self._state.last_processed_line}, "
                f"processed {self._state.total_processed}"
            )

            return self._state

        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Corrupted checkpoint file, starting fresh: {e}")
            self._state = ApplicationState()
            return self._state

    def update(self, **kwargs) -> None:
        """Update state fields by keyword arguments."""
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
            else:
                logger.warning(f"Unknown state field: {key}")

    def increment(self, field_name: str, amount: int = 1) -> None:
        """Increment a numeric state field."""
        current = getattr(self._state, field_name, None)
        if isinstance(current, (int, float)):
            setattr(self._state, field_name, current + amount)
        else:
            logger.warning(f"Cannot increment non-numeric field: {field_name}")

    def update_category_count(self, category: str, count: int) -> None:
        """Update count for a specific result category."""
        self._state.category_counts[category] = count

    def clear(self) -> None:
        """Reset state and delete checkpoint file."""
        self._state = ApplicationState()
        if self.state_file.exists():
            self.state_file.unlink()
            logger.info("Checkpoint cleared")

    def has_checkpoint(self) -> bool:
        """Check if a valid checkpoint exists."""
        return self.state_file.exists()
