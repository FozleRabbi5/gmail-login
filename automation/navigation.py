"""
Navigation helper for page interactions during login testing.

Handles navigation, credential filling with human-like typing,
form submission, and multi-step login flows.
"""

from __future__ import annotations

import asyncio
import random

from loguru import logger
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


class NavigationHelper:
    """Page interaction utilities for login flows."""

    def __init__(
        self,
        login_url: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        timeout: int = 30,
        multi_step: bool = False,
    ) -> None:
        self._login_url = login_url
        self._username_selector = username_selector
        self._password_selector = password_selector
        self._submit_selector = submit_selector
        self._timeout_ms = timeout * 1000
        self._multi_step = multi_step

    async def navigate_to_login(self, page: Page) -> bool:
        """Navigate to the login page. Returns True on success."""
        try:
            response = await page.goto(
                self._login_url,
                wait_until="domcontentloaded",
                timeout=self._timeout_ms,
            )
            if response and response.status >= 400:
                logger.warning(f"Login page returned status {response.status}")
                return False
            await page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
            return True
        except PlaywrightTimeout:
            logger.warning(f"Timeout navigating to {self._login_url}")
            return False
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return False

    async def fill_credentials(self, page: Page, username: str, password: str) -> bool:
        """Fill username and password. Supports multi-step flows."""
        try:
            if self._multi_step:
                return await self._fill_multi_step(page, username, password)
            else:
                return await self._fill_single_step(page, username, password)
        except PlaywrightTimeout:
            logger.warning("Timeout filling credentials")
            return False
        except Exception as e:
            logger.error(f"Error filling credentials: {e}")
            return False

    async def _resolve_username_selector(self, page: Page) -> str:
        """
        Prefer a real email/username input over the Google identifier field.

        Some pages expose `#identifierId` as an intermediate identifier control.
        When that happens, we try more conventional username selectors first.
        """
        preferred_selectors = [
            self._username_selector.strip(),
            "input[type='email']",
            "input[name='identifier']",
            "[autocomplete='username']",
            "#identifierId",
        ]

        seen: set[str] = set()
        for selector in preferred_selectors:
            if not selector or selector in seen:
                continue
            seen.add(selector)

            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                if await locator.is_visible():
                    return selector
            except Exception:
                continue

        return self._username_selector.strip()

    async def _fill_single_step(self, page: Page, username: str, password: str) -> bool:
        username_selector = await self._resolve_username_selector(page)
        await page.wait_for_selector(username_selector, state="visible", timeout=self._timeout_ms)
        await page.fill(username_selector, "")
        await page.type(username_selector, username, delay=random.randint(30, 80))
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await page.wait_for_selector(self._password_selector, state="visible", timeout=self._timeout_ms)
        await page.fill(self._password_selector, "")
        await page.type(self._password_selector, password, delay=random.randint(30, 80))
        return True

    async def _fill_multi_step(self, page: Page, username: str, password: str) -> bool:
        username_selector = await self._resolve_username_selector(page)
        await page.wait_for_selector(username_selector, state="visible", timeout=self._timeout_ms)
        await page.fill(username_selector, "")
        await page.type(username_selector, username, delay=random.randint(30, 80))
        await asyncio.sleep(random.uniform(0.3, 0.6))

        submit_selectors = [s.strip() for s in self._submit_selector.split(",")]
        first_submit = submit_selectors[0]
        await page.wait_for_selector(first_submit, state="visible", timeout=self._timeout_ms)
        await page.click(first_submit)
        await asyncio.sleep(random.uniform(1.0, 2.0))

        try:
            await page.wait_for_selector(self._password_selector, state="visible", timeout=self._timeout_ms)
        except PlaywrightTimeout:
            logger.debug("Password field didn't appear after username step")
            return False

        await page.fill(self._password_selector, "")
        await page.type(self._password_selector, password, delay=random.randint(30, 80))
        return True

    async def submit_form(self, page: Page) -> bool:
        """Click the submit button."""
        try:
            submit_selectors = [s.strip() for s in self._submit_selector.split(",")]
            submit = submit_selectors[-1]
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await page.wait_for_selector(submit, state="visible", timeout=self._timeout_ms)
            await page.click(submit)
            return True
        except PlaywrightTimeout:
            logger.warning("Timeout submitting form")
            return False
        except Exception as e:
            logger.error(f"Submit error: {e}")
            return False

    async def wait_for_result(self, page: Page) -> None:
        """Wait for page to settle after submission."""
        try:
            await asyncio.sleep(random.uniform(1.5, 3.0))
            await page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
        except PlaywrightTimeout:
            logger.debug("Network didn't settle, proceeding with detection")
        except Exception:
            pass
