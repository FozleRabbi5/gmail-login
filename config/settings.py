"""
Application settings module using Pydantic for validation.

Loads configuration from config.yaml with environment variable overrides.
All settings are validated at startup to fail fast on misconfiguration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class IndicatorConfig(BaseModel):
    """Configuration for login outcome indicators."""

    url_patterns: list[str] = Field(default_factory=list)
    page_titles: list[str] = Field(default_factory=list)
    dom_selectors: list[str] = Field(default_factory=list)
    text_patterns: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    """
    Application settings with validation.

    Design decision: Using Pydantic BaseModel instead of BaseSettings
    because we load from YAML primarily, not environment variables.
    Environment variables can still override via the load() classmethod.
    """

    # --- Target Login Page ---
    login_url: str = Field(
        default="https://accounts.google.com/signin",
        description="URL of the login page to test",
    )
    username_selector: str = Field(
        default="input[type='email']",
        description="CSS selector for the username/email input field",
    )
    password_selector: str = Field(
        default="input[type='password']",
        description="CSS selector for the password input field",
    )
    submit_selector: str = Field(
        default="#identifierNext, #passwordNext",
        description="CSS selector for the submit button",
    )
    multi_step_login: bool = Field(
        default=True,
        description="Whether the login flow has multiple steps (e.g., email then password)",
    )

    # --- Login Detection ---
    success_indicators: IndicatorConfig = Field(default_factory=IndicatorConfig)
    failure_indicators: IndicatorConfig = Field(default_factory=IndicatorConfig)

    # --- Browser Settings ---
    browser_type: str = Field(
        default="chromium",
        description="Browser engine: chromium, firefox, or webkit",
    )
    headless: bool = Field(
        default=True,
        description="Run browsers in headless mode",
    )
    worker_count: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of concurrent login workers",
    )
    timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout in seconds per login attempt",
    )
    retry_count: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Number of retries per failed login attempt",
    )
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=720, ge=240, le=2160)

    # --- Performance ---
    queue_max_size: int = Field(
        default=1000,
        ge=10,
        le=100000,
        description="Maximum queue size to bound memory usage",
    )
    checkpoint_interval: int = Field(
        default=30,
        ge=5,
        le=600,
        description="Seconds between automatic checkpoint saves",
    )

    # --- Credentials ---
    credentials_file: str = Field(
        default="config/credentials.txt",
        description="Path to the credentials file (username:password per line)",
    )

    # --- Output ---
    output_directory: str = Field(default="results")
    result_categories: list[str] = Field(
        default_factory=lambda: [
            "success",
            "failure",
            "disabled",
            "changepassword",
            "error",
            "timeout",
            "captcha",
            "locked",
            "unknown",
            "codeverify",
            "numberverify",
            "phoneveryify",
            "valid_mail_to",
            "deleted",
            "otherwebsite",
        ],
    )

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_directory: str = Field(default="logs")
    log_max_size: str = Field(default="10 MB")
    log_rotation: int = Field(default=5, ge=1, le=50)

    # --- Resource Limits ---
    max_memory_mb: int = Field(
        default=2048,
        ge=256,
        le=16384,
        description="Maximum memory in MB before browser restart",
    )

    @field_validator("browser_type")
    @classmethod
    def validate_browser_type(cls, v: str) -> str:
        allowed = {"chromium", "firefox", "webkit"}
        if v.lower() not in allowed:
            raise ValueError(f"browser_type must be one of {allowed}, got '{v}'")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return v.upper()

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        """
        Load settings from YAML config file with environment variable overrides.

        Args:
            config_path: Path to YAML config file. Defaults to config/config.yaml.

        Returns:
            Validated Settings instance.
        """
        if config_path is None:
            # Look relative to the project root
            config_path = Path(__file__).parent / "config.yaml"
        else:
            config_path = Path(config_path)

        data: dict[str, Any] = {}

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
                if isinstance(raw, dict):
                    data = raw

        # Environment variable overrides (prefixed with LT_)
        env_mappings = {
            "LT_LOGIN_URL": "login_url",
            "LT_WORKER_COUNT": "worker_count",
            "LT_HEADLESS": "headless",
            "LT_TIMEOUT": "timeout",
            "LT_BROWSER_TYPE": "browser_type",
            "LT_LOG_LEVEL": "log_level",
        }
        for env_key, setting_key in env_mappings.items():
            env_val = os.environ.get(env_key)
            if env_val is not None:
                # Auto-convert types
                if setting_key in ("worker_count", "timeout"):
                    data[setting_key] = int(env_val)
                elif setting_key == "headless":
                    data[setting_key] = env_val.lower() in ("true", "1", "yes")
                else:
                    data[setting_key] = env_val

        return cls(**data)

    def save(self, config_path: str | Path) -> None:
        """Save current settings to a YAML file."""
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.model_dump()

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def to_display_dict(self) -> dict[str, Any]:
        """Return a flat dictionary suitable for GUI display."""
        data = self.model_dump()
        # Flatten nested indicator configs for display
        for key in ("success_indicators", "failure_indicators"):
            if key in data and isinstance(data[key], dict):
                for sub_key, sub_val in data[key].items():
                    data[f"{key}.{sub_key}"] = sub_val
                del data[key]
        return data
