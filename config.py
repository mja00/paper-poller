"""Configuration management for paper-poller."""

import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    """Parse an integer environment variable, falling back so a typo can't crash startup.

    Args:
        name: Environment variable name
        default: Value to use when the variable is unset or not an integer

    Returns:
        Parsed integer value or the default
    """
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer for {name}: {value!r}, using default {default}")
        return default


class Config:
    """Centralized configuration management for paper-poller."""

    # Constants
    DEFAULT_REQUEST_TIMEOUT = 10
    WEBHOOK_TIMEOUT = 30
    LOCK_TIMEOUT = 10
    GQL_BASE_URL = "https://fill.papermc.io/graphql"

    # Rate limiting delays (configurable via environment)
    RATE_LIMIT_DELAY = _int_env("PAPER_POLLER_RATE_LIMIT_DELAY", 2)
    VERSION_CHECK_DELAY = _int_env("PAPER_POLLER_VERSION_CHECK_DELAY", 1)

    # Project name constants
    PROJECT_PAPER = "paper"
    PROJECT_FOLIA = "folia"
    PROJECT_VELOCITY = "velocity"
    PROJECT_WATERFALL = "waterfall"

    PROJECTS = [PROJECT_PAPER, PROJECT_FOLIA, PROJECT_VELOCITY, PROJECT_WATERFALL]

    # Feature flags (from environment)
    CHECK_ALL_VERSIONS = os.getenv("PAPER_POLLER_CHECK_ALL_VERSIONS", "false").lower() == "true"
    DRY_RUN = os.getenv("PAPER_POLLER_DRY_RUN", "false").lower() == "true"

    def __init__(self):
        """Initialize configuration and load webhook URLs."""
        self.webhook_urls = self._load_webhook_urls()
        self.webhook_urls = self._validate_and_filter_urls(self.webhook_urls)

    @staticmethod
    def _validate_webhook_url(url: str) -> bool:
        """Validate webhook URL format.

        Args:
            url: URL string to validate

        Returns:
            True if URL is valid, False otherwise
        """
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and parsed.netloc
        except Exception:
            return False

    @staticmethod
    def _validate_and_filter_urls(urls: list[str]) -> list[str]:
        """Validate and filter webhook URLs.

        Args:
            urls: List of URL strings to validate

        Returns:
            List of valid URLs (possibly empty)
        """
        valid_urls = [url for url in urls if Config._validate_webhook_url(url)]
        invalid_count = len(urls) - len(valid_urls)
        if invalid_count > 0:
            logger.warning(f"Found {invalid_count} invalid webhook URL(s), skipping them")
        return valid_urls

    def _load_webhook_urls(self) -> list[str]:
        """Load webhook URLs from environment, file, or stdin.

        Returns:
            List of webhook URL strings (empty when nothing valid is configured)
        """

        # Check environment variable first
        if os.getenv("WEBHOOK_URL"):
            # Don't log the value itself; webhook URLs are bearer credentials
            logger.info("Using webhook URL(s) from WEBHOOK_URL environment variable")
            try:
                urls = json.loads(os.getenv("WEBHOOK_URL"))
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing WEBHOOK_URL from environment: {e}")
                logger.error("WEBHOOK_URL must be a JSON array of URLs, e.g. WEBHOOK_URL='[\"https://...\"]'")
                return []
            if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
                logger.error("WEBHOOK_URL must be a JSON array of URL strings, e.g. WEBHOOK_URL='[\"https://...\"]'")
                return []
            return urls

        # Check for webhooks.json file
        if Path("webhooks.json").exists():
            logger.info("Using webhook URL from webhooks.json")
            try:
                with open(Path("webhooks.json"), "r") as f:
                    return json.load(f)["urls"]
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error loading webhooks.json: {e}")
                return []

        # Check stdin if --stdin flag is present
        start_args = sys.argv[1:]
        if "--stdin" in start_args:
            try:
                data = json.loads(sys.stdin.read())
                return data["urls"]
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error parsing JSON from stdin: {e}")
                return []

        logger.warning("No webhook URLs configured")
        return []
