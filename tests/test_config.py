"""Unit tests for config.py webhook loading and env parsing."""

import json
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config, _int_env


class TestWebhookUrlLoading:
    """Tests for webhook URL loading with no silent fallbacks."""

    def test_no_config_yields_empty_list(self, tmp_path, monkeypatch):
        """No env var and no webhooks.json means zero URLs, not a fallback."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("WEBHOOK_URL", raising=False)

        assert Config().webhook_urls == []

    def test_env_json_array(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WEBHOOK_URL", '["https://example.com/hook"]')

        assert Config().webhook_urls == ["https://example.com/hook"]

    def test_env_bare_url_rejected_with_hint(self, tmp_path, monkeypatch, caplog):
        """A bare URL (not JSON) is the likely operator mistake; the error must explain the format."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WEBHOOK_URL", "https://example.com/hook")

        with caplog.at_level(logging.ERROR):
            config = Config()

        assert config.webhook_urls == []
        assert "JSON array" in caplog.text

    def test_env_json_string_rejected_with_hint(self, tmp_path, monkeypatch, caplog):
        """Valid JSON that isn't a list of strings is rejected."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WEBHOOK_URL", '"https://example.com/hook"')

        with caplog.at_level(logging.ERROR):
            config = Config()

        assert config.webhook_urls == []
        assert "JSON array" in caplog.text

    def test_env_url_value_not_logged(self, tmp_path, monkeypatch, caplog):
        """Webhook URLs are bearer credentials and must never appear in logs."""
        monkeypatch.chdir(tmp_path)
        secret = "https://discord.com/api/webhooks/123/secrettoken"
        monkeypatch.setenv("WEBHOOK_URL", f'["{secret}"]')

        with caplog.at_level(logging.DEBUG):
            Config()

        assert secret not in caplog.text

    def test_webhooks_json_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("WEBHOOK_URL", raising=False)
        with open(tmp_path / "webhooks.json", "w") as f:
            json.dump({"urls": ["https://example.com/hook"]}, f)

        assert Config().webhook_urls == ["https://example.com/hook"]

    def test_invalid_urls_filtered_without_fallback(self, tmp_path, monkeypatch):
        """Invalid URLs are dropped and nothing is substituted in their place."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WEBHOOK_URL", '["not-a-url", "ftp://nope.example.com"]')

        assert Config().webhook_urls == []


class TestIntEnv:
    """Tests for the _int_env parsing helper."""

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("PP_TEST_INT", raising=False)
        assert _int_env("PP_TEST_INT", 5) == 5

    def test_parses_value(self, monkeypatch):
        monkeypatch.setenv("PP_TEST_INT", "9")
        assert _int_env("PP_TEST_INT", 5) == 9

    def test_invalid_value_falls_back_with_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("PP_TEST_INT", "banana")

        with caplog.at_level(logging.WARNING):
            assert _int_env("PP_TEST_INT", 5) == 5

        assert "PP_TEST_INT" in caplog.text
