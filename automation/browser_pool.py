"""
Browser pool managing Playwright browser lifecycle.

Design decision: Maintains a single Browser instance but creates a fresh
BrowserContext for EACH credential check. This gives each check clean
cookies/storage (isolation) while avoiding the overhead of launching a
new browser process per check. A semaphore limits concurrent contexts
to the configured worker count.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    BrowserType,
    Playwright,
    async_playwright,
)


class BrowserPool:
    """
    Manages Playwright browser instances with context pooling.

    Each login check gets a fresh BrowserContext (clean session).
    A semaphore controls the maximum number of concurrent contexts.
    The browser is automatically restarted if it crashes.

    Usage:
        pool = BrowserPool(max_contexts=10, headless=True)
        await pool.start()

        async with pool.acquire_context() as context:
            page = await context.new_page()
            # ... perform login check ...

        await pool.stop()
    """

    def __init__(
        self,
        max_contexts: int = 5,
        headless: bool = True,
        browser_type: str = "chromium",
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        self._max_contexts = max_contexts
        self._headless = headless
        self._browser_type_name = browser_type
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height

        # Playwright instances
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_type: BrowserType | None = None

        # Concurrency control
        self._semaphore = asyncio.Semaphore(max_contexts)
        self._active_contexts: int = 0
        self._total_contexts_created: int = 0
        self._lock = asyncio.Lock()

        # State
        self._running = False

    async def start(self) -> None:
        """Start Playwright and launch the browser."""
        if self._running:
            return

        self._playwright = await async_playwright().start()

        # Select browser type
        browser_types = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }
        self._browser_type = browser_types.get(
            self._browser_type_name,
            self._playwright.chromium,
        )

        await self._launch_browser()
        self._running = True

        logger.info(
            f"BrowserPool started: {self._browser_type_name}, "
            f"headless={self._headless}, max_contexts={self._max_contexts}"
        )

    async def _launch_browser(self) -> None:
        """Launch a new browser instance."""
        if self._browser_type is None:
            raise RuntimeError("Playwright not initialized")

        self._browser = await self._browser_type.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-extensions",
            ],
        )

        logger.info("Browser launched")

    async def _ensure_browser(self) -> Browser:
        """Ensure browser is running, restart if crashed."""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                logger.warning("Browser disconnected, restarting...")
                await self._cleanup_browser()
                await self._launch_browser()

            assert self._browser is not None
            return self._browser

    async def acquire_context(self) -> BrowserContext:
        """
        Acquire a fresh browser context.

        Blocks if the maximum number of concurrent contexts is reached.
        The caller MUST call release_context() when done.

        Returns:
            A new BrowserContext with clean cookies/storage.
        """
        await self._semaphore.acquire()

        try:
            browser = await self._ensure_browser()

            context = await browser.new_context(
                viewport={
                    "width": self._viewport_width,
                    "height": self._viewport_height,
                },
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
            )

            async with self._lock:
                self._active_contexts += 1
                self._total_contexts_created += 1

            return context

        except Exception:
            self._semaphore.release()
            raise

    async def release_context(self, context: BrowserContext) -> None:
        """
        Release a browser context back to the pool.

        Closes the context and releases the semaphore.
        """
        try:
            await context.close()
        except Exception as e:
            logger.warning(f"Error closing context: {e}")
        finally:
            async with self._lock:
                self._active_contexts = max(0, self._active_contexts - 1)
            self._semaphore.release()

    async def _cleanup_browser(self) -> None:
        """Close the current browser instance."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            self._browser = None

    async def stop(self) -> None:
        """Stop the browser pool and cleanup all resources."""
        self._running = False

        await self._cleanup_browser()

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

        logger.info(
            f"BrowserPool stopped. Total contexts created: "
            f"{self._total_contexts_created}"
        )

    @property
    def active_contexts(self) -> int:
        """Number of currently active browser contexts."""
        return self._active_contexts

    @property
    def total_created(self) -> int:
        """Total number of contexts created since start."""
        return self._total_contexts_created

    @property
    def is_running(self) -> bool:
        """Whether the pool is running."""
        return self._running
