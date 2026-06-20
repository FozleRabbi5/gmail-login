"""
Configurable login outcome detection system.

Design decision: Uses a Strategy pattern where each detection method
is a separate class implementing a common interface. A CompositeDetector
runs all configured strategies and returns the first definitive match.
This makes the system extensible — new detection methods can be added
without modifying existing code (Open/Closed Principle).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum, auto

from loguru import logger
from playwright.async_api import Page

from config.settings import IndicatorConfig


class LoginResult(Enum):
    """Possible outcomes of a login attempt."""

    SUCCESS = auto()
    FAILURE = auto()
    ERROR = auto()
    TIMEOUT = auto()
    CAPTCHA = auto()
    LOCKED = auto()
    UNKNOWN = auto()

    @property
    def category(self) -> str:
        """Convert to category string for result writing."""
        return self.name.lower()


class BaseDetector(ABC):
    """Abstract base class for login outcome detectors."""

    @abstractmethod
    async def detect(self, page: Page) -> LoginResult | None:
        """
        Check the page for a login outcome.

        Returns:
            LoginResult if detected, None if inconclusive.
        """
        ...


class URLPatternDetector(BaseDetector):
    """Detects login outcome by matching URL patterns."""

    def __init__(
        self,
        success_patterns: list[str],
        failure_patterns: list[str],
    ) -> None:
        self._success_patterns = [re.compile(p) for p in success_patterns]
        self._failure_patterns = [re.compile(p) for p in failure_patterns]

    async def detect(self, page: Page) -> LoginResult | None:
        url = page.url

        for pattern in self._success_patterns:
            if pattern.search(url):
                logger.debug(f"URL success match: {pattern.pattern} in {url}")
                return LoginResult.SUCCESS

        for pattern in self._failure_patterns:
            if pattern.search(url):
                logger.debug(f"URL failure match: {pattern.pattern} in {url}")
                return LoginResult.FAILURE

        return None


class TitleDetector(BaseDetector):
    """Detects login outcome by matching page title."""

    def __init__(
        self,
        success_titles: list[str],
        failure_titles: list[str],
    ) -> None:
        self._success_titles = [t.lower() for t in success_titles]
        self._failure_titles = [t.lower() for t in failure_titles]

    async def detect(self, page: Page) -> LoginResult | None:
        try:
            title = (await page.title()).lower()
        except Exception:
            return None

        for pattern in self._success_titles:
            if pattern in title:
                logger.debug(f"Title success match: '{pattern}' in '{title}'")
                return LoginResult.SUCCESS

        for pattern in self._failure_titles:
            if pattern in title:
                logger.debug(f"Title failure match: '{pattern}' in '{title}'")
                return LoginResult.FAILURE

        return None


class SelectorDetector(BaseDetector):
    """Detects login outcome by checking for DOM elements."""

    def __init__(
        self,
        success_selectors: list[str],
        failure_selectors: list[str],
    ) -> None:
        self._success_selectors = success_selectors
        self._failure_selectors = failure_selectors

    async def detect(self, page: Page) -> LoginResult | None:
        for selector in self._success_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    logger.debug(f"Selector success match: {selector}")
                    return LoginResult.SUCCESS
            except Exception:
                continue

        for selector in self._failure_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    logger.debug(f"Selector failure match: {selector}")
                    return LoginResult.FAILURE
            except Exception:
                continue

        return None


class TextPatternDetector(BaseDetector):
    """Detects login outcome by searching for text patterns on the page."""

    def __init__(
        self,
        success_patterns: list[str] | None = None,
        failure_patterns: list[str] | None = None,
    ) -> None:
        self._success_patterns = [p.lower() for p in (success_patterns or [])]
        self._failure_patterns = [p.lower() for p in (failure_patterns or [])]

    async def detect(self, page: Page) -> LoginResult | None:
        try:
            # Get visible text content from the page body
            body_text = await page.inner_text("body")
            body_lower = body_text.lower()
        except Exception:
            return None

        for pattern in self._failure_patterns:
            if pattern in body_lower:
                logger.debug(f"Text failure match: '{pattern}'")
                return LoginResult.FAILURE

        for pattern in self._success_patterns:
            if pattern in body_lower:
                logger.debug(f"Text success match: '{pattern}'")
                return LoginResult.SUCCESS

        return None


class CompositeDetector(BaseDetector):
    """
    Runs multiple detectors and returns the first definitive result.

    Priority order matches the order detectors are added.
    """

    def __init__(self) -> None:
        self._detectors: list[BaseDetector] = []

    def add(self, detector: BaseDetector) -> "CompositeDetector":
        """Add a detector to the composite. Returns self for chaining."""
        self._detectors.append(detector)
        return self

    async def detect(self, page: Page) -> LoginResult | None:
        for detector in self._detectors:
            try:
                result = await detector.detect(page)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(
                    f"Detector {detector.__class__.__name__} error: {e}"
                )

        return None

    @classmethod
    def from_config(
        cls,
        success_indicators: IndicatorConfig,
        failure_indicators: IndicatorConfig,
    ) -> "CompositeDetector":
        """
        Create a CompositeDetector from configuration.

        Factory method that builds the full detection pipeline from
        the user's configured indicators.
        """
        detector = cls()

        # URL pattern detection (fastest, check first)
        if success_indicators.url_patterns or failure_indicators.url_patterns:
            detector.add(URLPatternDetector(
                success_patterns=success_indicators.url_patterns,
                failure_patterns=failure_indicators.url_patterns,
            ))

        # Title detection
        if success_indicators.page_titles or failure_indicators.page_titles:
            detector.add(TitleDetector(
                success_titles=success_indicators.page_titles,
                failure_titles=failure_indicators.page_titles,
            ))

        # Selector detection (DOM elements)
        if success_indicators.dom_selectors or failure_indicators.dom_selectors:
            detector.add(SelectorDetector(
                success_selectors=success_indicators.dom_selectors,
                failure_selectors=failure_indicators.dom_selectors,
            ))

        # Text pattern detection (slowest, check last)
        if success_indicators.text_patterns or failure_indicators.text_patterns:
            detector.add(TextPatternDetector(
                success_patterns=success_indicators.text_patterns,
                failure_patterns=failure_indicators.text_patterns,
            ))

        return detector
