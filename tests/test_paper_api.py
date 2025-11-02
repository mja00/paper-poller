"""Unit tests for PaperAPI class."""

import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, Mock, call, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set env vars before import
os.environ.setdefault("WEBHOOK_URL", '["http://example.com"]')

from paper_poller import PaperAPI, get_spigot_drama


class TestPaperAPIInitialization:
    """Tests for PaperAPI initialization."""

    def test_default_initialization(self):
        """Test PaperAPI initializes with default values."""
        api = PaperAPI()
        assert api.base_url == "https://api.papermc.io/v2"
        assert api.project == "paper"
        assert api.image_url == "https://assets.papermc.io/brand/papermc_logo.512.png"

    def test_folia_project_initialization(self):
        """Test PaperAPI initializes correctly for Folia project."""
        api = PaperAPI(project="folia")
        assert api.project == "folia"
        assert api.image_url == "https://assets.papermc.io/brand/folia_logo.256x139.png"

    def test_velocity_project_initialization(self):
        """Test PaperAPI initializes correctly for Velocity project."""
        api = PaperAPI(project="velocity")
        assert api.project == "velocity"
        assert (
            api.image_url == "https://assets.papermc.io/brand/velocity_logo.256x128.png"
        )

    def test_custom_base_url(self):
        """Test PaperAPI can use custom base URL."""
        custom_url = "https://custom.api.example.com"
        api = PaperAPI(base_url=custom_url)
        assert api.base_url == custom_url


class TestPaperAPIUpToDate:
    """Tests for up_to_date and related methods."""

    def test_up_to_date_when_matching(self, tmp_path, monkeypatch):
        """Test up_to_date returns True when version and build match."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        data = {"version": "1.21.1", "build": "123", "channel": "STABLE"}
        with open("paper_poller.json", "w") as f:
            json.dump(data, f)

        assert api.up_to_date("1.21.1", "123") is True

    def test_up_to_date_when_different(self, tmp_path, monkeypatch):
        """Test up_to_date returns False when version or build differs."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        data = {"version": "1.21.1", "build": "123", "channel": "STABLE"}
        with open("paper_poller.json", "w") as f:
            json.dump(data, f)

        assert api.up_to_date("1.21.1", "124") is False
        assert api.up_to_date("1.21.2", "123") is False

    def test_up_to_date_when_file_not_exists(self, tmp_path, monkeypatch):
        """Test up_to_date returns False when file doesn't exist."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        assert api.up_to_date("1.21.1", "123") is False


class TestPaperAPIVersionSpecificMethods:
    """Tests for version-specific storage methods."""

    def test_up_to_date_for_version(self, tmp_path, monkeypatch):
        """Test up_to_date_for_version with multi-version structure."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        data = {
            "version": "1.21.1",
            "build": "123",
            "channel": "STABLE",
            "versions": {
                "1.21.1": {"build": "123", "channel": "STABLE"},
                "1.21": {"build": "120", "channel": "RECOMMENDED"},
            },
        }
        with open("paper_poller.json", "w") as f:
            json.dump(data, f)

        assert api.up_to_date_for_version("1.21.1", "123") is True
        assert api.up_to_date_for_version("1.21", "120") is True
        assert api.up_to_date_for_version("1.21.1", "124") is False
        assert api.up_to_date_for_version("1.20", "100") is False

    def test_get_stored_data_for_version(self, tmp_path, monkeypatch):
        """Test get_stored_data_for_version retrieves correct data."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        data = {
            "versions": {
                "1.21.1": {"build": "123", "channel": "STABLE"},
                "1.21": {"build": "120", "channel": "RECOMMENDED"},
            }
        }
        with open("paper_poller.json", "w") as f:
            json.dump(data, f)

        version_data = api.get_stored_data_for_version("1.21.1")
        assert version_data["build"] == "123"
        assert version_data["channel"] == "STABLE"

        version_data = api.get_stored_data_for_version("1.20")
        assert version_data["build"] == ""
        assert version_data["channel"] is None

    def test_write_version_to_json(self, tmp_path, monkeypatch):
        """Test write_version_to_json creates proper structure."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        api.write_version_to_json("1.21.1", "123", "STABLE")

        with open("paper_poller.json", "r") as f:
            data = json.load(f)

        assert data["versions"]["1.21.1"]["build"] == "123"
        assert data["versions"]["1.21.1"]["channel"] == "STABLE"
        # Should maintain backward compatibility
        assert data["version"] == "1.21.1"
        assert data["build"] == "123"
        assert data["channel"] == "STABLE"

    def test_write_version_to_json_multiple_versions(self, tmp_path, monkeypatch):
        """Test write_version_to_json handles multiple versions."""
        monkeypatch.chdir(tmp_path)

        api = PaperAPI()
        api.write_version_to_json("1.21.1", "123", "STABLE")
        api.write_version_to_json("1.21", "120", "RECOMMENDED")

        with open("paper_poller.json", "r") as f:
            data = json.load(f)

        assert len(data["versions"]) == 2
        assert data["versions"]["1.21.1"]["build"] == "123"
        assert data["versions"]["1.21"]["build"] == "120"


class TestPaperAPIGetChanges:
    """Tests for get_changes_for_build method."""

    def test_get_changes_for_build(self):
        """Test that commit changes are formatted correctly."""
        api = PaperAPI()
        build_data = {
            "commits": [
                {
                    "sha": "abc123def456789",
                    "message": "Fix #1234 - Update DataConverter constants",
                },
                {"sha": "xyz789abc123456", "message": "Improve performance"},
            ]
        }

        changes = api.get_changes_for_build(build_data)

        assert "abc123d" in changes  # Short hash
        assert "xyz789a" in changes
        assert "Fix" in changes
        assert "Improve performance" in changes
        assert "[#1234]" in changes  # Should be linked
        assert "diffs.dev" in changes  # Should use diffs.dev

    def test_get_changes_with_multiline_message(self):
        """Test that only first line of commit message is used."""
        api = PaperAPI()
        build_data = {
            "commits": [
                {
                    "sha": "abc123def456789",
                    "message": "Fix issue\n\nThis is a longer description\nthat spans multiple lines",
                }
            ]
        }

        changes = api.get_changes_for_build(build_data)
        assert "Fix issue" in changes
        assert "longer description" not in changes

    def test_get_changes_with_multiple_pr_references(self):
        """Test that multiple PR references are linked."""
        api = PaperAPI()
        build_data = {
            "commits": [
                {"sha": "abc123def456789", "message": "Fix #1234 and close #5678"}
            ]
        }

        changes = api.get_changes_for_build(build_data)
        assert "[#1234]" in changes
        assert "[#5678]" in changes
        assert "github.com/PaperMC/paper/issues/1234" in changes
        assert "github.com/PaperMC/paper/issues/5678" in changes


class TestPaperAPIProcessAndSendUpdate:
    """Tests for _process_and_send_update method."""

    @patch("paper_poller.get_spigot_drama")
    def test_process_and_send_update_normal_mode(
        self, mock_drama, sample_build_info, mocker
    ):
        """Test _process_and_send_update sends webhooks in normal mode."""
        mock_drama.return_value = {"response": "No drama today"}
        mock_send = mocker.patch.object(PaperAPI, "send_v2_webhook")
        # Mock webhook_urls in config
        mocker.patch("paper_poller.config.webhook_urls", ["http://test.webhook.com"])

        api = PaperAPI()
        api._process_and_send_update("1.21.1", sample_build_info, False)

        # Verify webhook was called
        assert mock_send.call_count == 1

    def test_process_and_send_update_dry_run_mode(self, sample_build_info, mocker):
        """Test _process_and_send_update doesn't send webhooks in dry run."""
        # Patch DRY_RUN at the config level
        mocker.patch("paper_poller.config.DRY_RUN", True)
        mock_send = mocker.patch.object(PaperAPI, "send_v2_webhook")

        api = PaperAPI()
        
        # Call the method - it should detect dry run and return early
        api._process_and_send_update("1.21.1", sample_build_info, False)
        
        # In dry run mode, webhook should not be called
        mock_send.assert_not_called()


class TestGetSpigotDrama:
    """Tests for get_spigot_drama function."""

    @patch("requests.get")
    def test_get_spigot_drama_success(self, mock_get):
        """Test successful drama API call."""
        mock_get.return_value.json.return_value = {"response": "Some drama!"}

        result = get_spigot_drama()

        assert result == {"response": "Some drama!"}
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_get_spigot_drama_failure(self, mock_get):
        """Test drama API failure returns default message."""
        mock_get.side_effect = Exception("API Error")

        result = get_spigot_drama()

        assert result == "There's no drama :("


class TestPaperAPIWebhookPayload:
    """Tests for webhook payload construction."""

    @patch("requests.post")
    def test_send_v2_webhook_payload_structure(self, mock_post):
        """Test that webhook payload has correct structure."""
        api = PaperAPI()
        drama = {"response": "No drama"}

        api.send_v2_webhook(
            hook_url="http://test.webhook.com",
            latest_build="123",
            latest_version="1.21.1",
            build_time=1697112000,
            image_url=api.image_url,
            changes="- abc123d Fix something\n",
            download_url="https://example.com/paper.jar",
            drama=drama,
            channel_name="Stable",
            channel_changed=False,
        )

        # Verify POST was called
        assert mock_post.call_count == 1

        # Check the payload structure
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]

        assert "components" in payload
        assert payload["flags"] == 1 << 15
        assert "allowed_mentions" in payload

    @patch("requests.post")
    def test_send_v2_webhook_with_channel_change(self, mock_post):
        """Test webhook payload includes channel change notification."""
        api = PaperAPI()
        drama = {"response": "No drama"}

        api.send_v2_webhook(
            hook_url="http://test.webhook.com",
            latest_build="123",
            latest_version="1.21.1",
            build_time=1697112000,
            image_url=api.image_url,
            changes="- abc123d Fix something\n",
            download_url="https://example.com/paper.jar",
            drama=drama,
            channel_name="Recommended",
            channel_changed=True,
        )

        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]

        # Should have an extra component for channel change
        # Count components of type 10 (content components)
        content_components = [c for c in payload["components"] if c.get("type") == 10]
        assert len(content_components) > 0
