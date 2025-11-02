"""Pytest configuration and fixtures for paper-poller tests."""

import json
import os
from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest


@pytest.fixture
def sample_build_info():
    """Sample build information for testing."""
    return {
        "number": "123",
        "channel": "STABLE",
        "download": {
            "name": "paper-1.21.1-123.jar",
            "size": 50000000,
            "url": "https://api.papermc.io/v2/projects/paper/versions/1.21.1/builds/123/downloads/paper-1.21.1-123.jar",
            "checksums": {"sha256": "abcdef1234567890"},
        },
        "commits": [
            {
                "sha": "abc123def456789",
                "message": "Fix #1234 - Update DataConverter constants",
            },
            {
                "sha": "def456abc123789",
                "message": "Improve performance for chunk loading",
            },
        ],
        "createdAt": "2025-10-12T12:00:00.000Z",
    }


@pytest.fixture
def sample_latest_build_response():
    """Sample GraphQL response for latest build query."""
    return {
        "project": {
            "key": "paper",
            "versions": {
                "edges": [
                    {
                        "node": {
                            "key": "1.21.1",
                            "builds": {
                                "edges": [
                                    {
                                        "node": {
                                            "number": "123",
                                            "channel": "STABLE",
                                            "download": {
                                                "name": "paper-1.21.1-123.jar",
                                                "size": 50000000,
                                                "url": "https://api.papermc.io/v2/projects/paper/versions/1.21.1/builds/123/downloads/paper-1.21.1-123.jar",
                                                "checksums": {"sha256": "abcdef1234567890"},
                                            },
                                            "commits": [
                                                {
                                                    "sha": "abc123def456789",
                                                    "message": "Fix #1234 - Update DataConverter",
                                                }
                                            ],
                                            "createdAt": "2025-10-12T12:00:00.000Z",
                                        }
                                    }
                                ]
                            },
                        }
                    }
                ]
            },
        }
    }


@pytest.fixture
def sample_all_versions_response():
    """Sample GraphQL response for all versions query."""
    return {
        "project": {
            "key": "paper",
            "versions": {
                "edges": [
                    {
                        "node": {
                            "key": "1.21.1",
                            "builds": {
                                "edges": [
                                    {
                                        "node": {
                                            "number": "123",
                                            "channel": "STABLE",
                                            "download": {
                                                "name": "paper-1.21.1-123.jar",
                                                "size": 50000000,
                                                "url": "https://api.papermc.io/v2/projects/paper/versions/1.21.1/builds/123/downloads/paper-1.21.1-123.jar",
                                                "checksums": {"sha256": "abcdef1234567890"},
                                            },
                                            "commits": [
                                                {
                                                    "sha": "abc123def456789",
                                                    "message": "Fix #1234 - Update DataConverter",
                                                }
                                            ],
                                            "createdAt": "2025-10-12T12:00:00.000Z",
                                        }
                                    }
                                ]
                            },
                        }
                    },
                    {
                        "node": {
                            "key": "1.21",
                            "builds": {
                                "edges": [
                                    {
                                        "node": {
                                            "number": "120",
                                            "channel": "RECOMMENDED",
                                            "download": {
                                                "name": "paper-1.21-120.jar",
                                                "size": 49000000,
                                                "url": "https://api.papermc.io/v2/projects/paper/versions/1.21/builds/120/downloads/paper-1.21-120.jar",
                                                "checksums": {"sha256": "123456abcdef"},
                                            },
                                            "commits": [
                                                {
                                                    "sha": "xyz789abc456",
                                                    "message": "Performance improvements",
                                                }
                                            ],
                                            "createdAt": "2025-10-11T12:00:00.000Z",
                                        }
                                    }
                                ]
                            },
                        }
                    },
                    {
                        "node": {
                            "key": "1.20.6",
                            "builds": {
                                "edges": []
                            },
                        }
                    },
                ]
            },
        }
    }


@pytest.fixture
def mock_gql_client(mocker):
    """Mock GQL client for testing."""
    mock_client = MagicMock()
    # Patch both the wrapper and the main module
    mocker.patch("paper_poller.client", mock_client)
    mocker.patch("paper-poller.client", mock_client, create=True)
    return mock_client


@pytest.fixture
def temp_json_file(tmp_path):
    """Create a temporary JSON file for testing file operations."""

    def _create_json_file(filename, data):
        filepath = tmp_path / filename
        with open(filepath, "w") as f:
            json.dump(data, f)
        return filepath

    return _create_json_file


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables for testing."""
    # Remove any environment variables that might affect tests
    monkeypatch.delenv("PAPER_POLLER_CHECK_ALL_VERSIONS", raising=False)
    monkeypatch.delenv("PAPER_POLLER_DRY_RUN", raising=False)
    monkeypatch.delenv("WEBHOOK_URL", raising=False)


@pytest.fixture
def mock_webhook_response(mocker):
    """Mock requests.post for webhook testing."""
    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 200
    return mock_post


@pytest.fixture
def sample_spigot_drama():
    """Sample spigot drama response."""
    return {"response": "There's no drama :("}
