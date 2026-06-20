"""
Output manager — facade coordinating result writing and state management.

Provides a single entry point for recording login test results, ensuring
both the result file and the state file are updated atomically.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from storage.result_writer import ResultWriter
from storage.state_manager import ApplicationState, StateManager


class OutputManager:
    """
    Facade coordinating ResultWriter and StateManager.

    Ensures directory structure exists and provides a unified interface
    for recording results with state tracking.
    """

    def __init__(
        self,
        base_directory: str | Path,
        output_directory: str | Path,
        categories: list[str] | None = None,
    ) -> None:
        self.base_dir = Path(base_directory)
        self.result_writer = ResultWriter(output_directory, categories)
        self.state_manager = StateManager(base_directory)

    async def initialize(self) -> ApplicationState:
        """
        Initialize output infrastructure.

        Creates directories, initializes writers, and loads any
        existing checkpoint for resume capability.

        Returns:
            Current application state (loaded from checkpoint or fresh).
        """
        # Ensure directories exist
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Initialize sub-components
        await self.result_writer.initialize()
        self.state_manager.initialize()

        # Load existing state if available
        state = self.state_manager.load()

        logger.info("OutputManager initialized")
        return state

    async def record_result(
        self,
        category: str,
        username: str,
        password: str,
        line_number: int,
        extra_info: str = "",
    ) -> None:
        """
        Record a login test result.

        Writes the result to the appropriate category file and updates
        the application state.

        Args:
            category: Result category (success, failure, error, etc.)
            username: Tested username.
            password: Tested password.
            line_number: Source line number in credentials file.
            extra_info: Optional additional information.
        """
        # Write result to file
        await self.result_writer.write_with_timestamp(
            category, username, password, extra_info
        )

        # Update state
        self.state_manager.update(
            last_processed_line=line_number,
        )
        self.state_manager.increment("total_processed")

        # Increment the specific category counter if it exists as a field
        category_field = f"{category}_count"
        if hasattr(self.state_manager.state, category_field):
            self.state_manager.increment(category_field)

        # Also update the flexible category counts
        self.state_manager.update_category_count(
            category,
            self.result_writer.get_counts().get(category, 0),
        )

    def save_checkpoint(self) -> None:
        """Save current state as a checkpoint."""
        self.state_manager.save()

    def get_state(self) -> ApplicationState:
        """Get current application state."""
        return self.state_manager.state

    def get_result_counts(self) -> dict[str, int]:
        """Get result counts per category."""
        return self.result_writer.get_counts()

    async def close(self) -> None:
        """Cleanup and final checkpoint save."""
        self.state_manager.save()
        await self.result_writer.close()
        logger.info("OutputManager closed with final checkpoint saved")
