"""
Paper Poller - A bot for monitoring PaperMC project builds.

This is a convenience module that imports from the main script.
"""

# Import the main script
import importlib.util
import os

# Import everything from the main script
import sys

spec = importlib.util.spec_from_file_location(
    "paper_poller_main", os.path.join(os.path.dirname(__file__), "paper-poller.py")
)
paper_poller_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper_poller_main)

# Export all public items
__all__ = [
    "PaperAPI",
    "convert_commit_hash_to_short",
    "convert_build_date",
    "get_spigot_drama",
    "Color",
    "CHANNEL_COLORS",
    "CHECK_ALL_VERSIONS",
    "DRY_RUN",
    "webhook_urls",
    "client",
    "main",
    "config",
]

# Make everything available at module level
PaperAPI = paper_poller_main.PaperAPI
convert_commit_hash_to_short = paper_poller_main.convert_commit_hash_to_short
convert_build_date = paper_poller_main.convert_build_date
get_spigot_drama = paper_poller_main.get_spigot_drama
Color = paper_poller_main.Color
CHANNEL_COLORS = paper_poller_main.CHANNEL_COLORS
config = paper_poller_main.config
# Backward compatibility exports
CHECK_ALL_VERSIONS = paper_poller_main.config.CHECK_ALL_VERSIONS
DRY_RUN = paper_poller_main.config.DRY_RUN
webhook_urls = paper_poller_main.config.webhook_urls
client = paper_poller_main.client
main = paper_poller_main.main
