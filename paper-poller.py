import json
import logging
import re
import time
import urllib.parse
from datetime import datetime as dt
from enum import Enum
from pathlib import Path

import requests
from filelock import FileLock, Timeout
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Initialize configuration
config = Config()


class Color(Enum):
    BLUE = 0x2B7FFF
    GREEN = 0x4ECB8B
    PINK = 0xF06292
    ORANGE = 0xFFB74D
    PURPLE = 0x7E57C2
    RED = 0xEA5B6F
    YELLOW = 0xFFC859


CHANNEL_COLORS = {
    "ALPHA": Color.RED.value,
    "BETA": Color.YELLOW.value,
    "STABLE": Color.BLUE.value,
    "RECOMMENDED": Color.GREEN.value,
}

PROJECT_IMAGE_URLS = {
    Config.PROJECT_PAPER: "https://assets.papermc.io/brand/papermc_logo.512.png",
    Config.PROJECT_FOLIA: "https://assets.papermc.io/brand/folia_logo.256x139.png",
    Config.PROJECT_VELOCITY: "https://assets.papermc.io/brand/velocity_logo.256x128.png",
    Config.PROJECT_WATERFALL: "",  # No image URL found, will use empty string
}

headers = {
    "User-Agent": "PaperMC Version Poller",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

transport = RequestsHTTPTransport(url=Config.GQL_BASE_URL)
client = Client(transport=transport, fetch_schema_from_transport=True)

latest_query = gql(
    """
query getLatestBuild($project: String!) {
    project(key: $project) {
        key
        versions(first: 1, orderBy: { direction: DESC }) {
            edges {
                node {
                    key
                    builds(orderBy: { direction: DESC }, first: 1) {
                        edges {
                            node {
                                number
                                channel
                                download(key: "server:default") {
                                    name
                                    url
                                    checksums {
                                        sha256
                                    }
                                    size
                                }
                                commits {
                                    sha
                                    message
                                }
                                createdAt
                            }
                        }
                    }
                }
            }
        }
    }
}
"""
)

all_versions_query = gql(
    """
query getAllVersionsWithBuilds($project: String!) {
    project(key: $project) {
        key
        versions(first: 100, orderBy: {direction: DESC}) {
            edges {
                node {
                    key
                    builds(orderBy: { direction: DESC }, first: 1) {
                        edges {
                            node {
                                number
                                channel
                                download(key: "server:default") {
                                    name
                                    url
                                    checksums {
                                        sha256
                                    }
                                    size
                                }
                                commits {
                                    sha
                                    message
                                }
                                createdAt
                            }
                        }
                    }
                }
            }
        }
    }
}
"""
)


def convert_commit_hash_to_short(hash: str) -> str:
    """Convert a commit hash to its short 7-character form.
    
    Args:
        hash: Full commit hash string
        
    Returns:
        First 7 characters of the hash
    """
    return hash[:7]


def convert_build_date(date: str) -> dt:
    """Convert ISO format date string to datetime object.
    
    Args:
        date: ISO format date string (e.g., "2022-06-14T10:40:30.563Z")
        
    Returns:
        datetime object with timezone information
        
    Raises:
        ValueError: If date format is invalid
    """
    # format: 2022-06-14T10:40:30.563Z
    try:
        return dt.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        # Try without microseconds if parsing fails
        try:
            return dt.strptime(date, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            logger.error(f"Invalid date format: {date}")
            raise


def get_spigot_drama() -> str | dict:
    """Fetch Spigot drama API response.
    
    Returns:
        Dictionary with drama response, or fallback string on error
    """
    try:
        response = requests.get("https://drama.mart.fyi/api", headers=headers, timeout=Config.DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()  # Raise exception for bad status codes
        data = response.json()
        return data
    except requests.RequestException as e:
        logger.error(f"Error getting spigot drama: {e}")
        return "There's no drama :("
    except Exception as e:
        logger.error(f"Error getting spigot drama: {e}")
        return "There's no drama :("


class PaperAPI:
    def __init__(self, base_url: str = "https://api.papermc.io/v2", project: str = "paper") -> None:
        self.headers = {
            "User-Agent": "PaperMC Version Poller",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        self.base_url = base_url
        self.project = project
        self.image_url = PROJECT_IMAGE_URLS.get(self.project, "")

    def _read_state_file(self) -> dict:
        """Read state file with default structure if not found.
        
        Returns:
            Dictionary containing state data
        """
        state_file = Path(f"{self.project}_poller.json")
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"versions": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {state_file}: {e}")
            return {"versions": {}}

    def _validate_graphql_response(self, response: dict, expected_path: list[str]) -> bool:
        """Validate that GraphQL response has the expected structure.
        
        Args:
            response: GraphQL response dictionary
            expected_path: List of keys representing the expected nested path
            
        Returns:
            True if structure is valid, False otherwise
        """
        current = response
        for key in expected_path:
            if not isinstance(current, dict) or key not in current:
                logger.error(f"GraphQL response missing expected key '{key}' at path {expected_path[:expected_path.index(key)+1]}")
                return False
            current = current[key]
        return True

    def _atomic_write_json(self, data: dict, filepath: Path) -> None:
        """Write JSON data to file atomically using a temp file.
        
        Args:
            data: Dictionary to write as JSON
            filepath: Path to the target JSON file
            
        Raises:
            OSError: If file operations fail
        """
        temp_file = filepath.with_suffix(filepath.suffix + ".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(filepath)
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise

    def up_to_date(self, version: str, build: str) -> bool:
        """Check if the specified version and build are up to date.
        
        Args:
            version: Minecraft version string
            build: Build number string
            
        Returns:
            True if version and build match stored values, False otherwise
        """
        data = self._read_state_file()
        # Ensure legacy format keys exist
        if "version" not in data:
            data["version"] = ""
        if "build" not in data:
            data["build"] = ""
        # Check if the version is up to date
        return data["version"] == version and data["build"] == build

    def up_to_date_for_version(self, version: str, build: str) -> bool:
        """Check if a specific version's build is up to date.
        
        Args:
            version: Minecraft version string
            build: Build number string
            
        Returns:
            True if version and build match stored values, False otherwise
        """
        data = self._read_state_file()

        # Check if we have versions structure
        if "versions" not in data:
            # Legacy format, convert it
            if "version" in data and "build" in data:
                return data["version"] == version and data["build"] == build
            return False

        version_data = data["versions"].get(version, {})
        return version_data.get("build") == build

    def get_stored_data(self) -> dict:
        """Get stored data in legacy format.
        
        Returns:
            Dictionary with version, build, and channel keys
        """
        data = self._read_state_file()
        # Ensure legacy format keys exist
        if "version" not in data:
            data["version"] = ""
        if "build" not in data:
            data["build"] = ""
        if "channel" not in data:
            data["channel"] = ""
        return data

    def get_stored_data_for_version(self, version: str) -> dict:
        """Get stored data for a specific version.
        
        Args:
            version: Minecraft version string
            
        Returns:
            Dictionary with build and channel for the version
        """
        data = self._read_state_file()

        # Check if we have versions structure
        if "versions" not in data:
            # Legacy format
            if "version" in data and data["version"] == version:
                return {
                    "build": data.get("build", ""),
                    "channel": data.get("channel", None),
                }
            return {"build": "", "channel": None}

        return data["versions"].get(version, {"build": "", "channel": None})

    def write_to_json(self, version: str, build: str, channel_name: str) -> None:
        """Write legacy format data to JSON file.
        
        Args:
            version: Minecraft version string
            build: Build number string
            channel_name: Channel name (e.g., STABLE, BETA)
        """
        data = {"version": version, "build": build, "channel": channel_name}
        state_file = Path(f"{self.project}_poller.json")
        self._atomic_write_json(data, state_file)

    def write_version_to_json(self, version: str, build: str, channel_name: str) -> None:
        """Write version-specific data to JSON file.
        
        Args:
            version: Minecraft version string
            build: Build number string
            channel_name: Channel name (e.g., STABLE, BETA)
        """
        # Read existing data
        data = self._read_state_file()
        state_file = Path(f"{self.project}_poller.json")

        # Ensure versions structure exists
        if "versions" not in data:
            data = {"versions": {}}

        # Update the specific version
        data["versions"][version] = {"build": build, "channel": channel_name}

        # Keep legacy format for latest version for backward compatibility
        data["version"] = version
        data["build"] = build
        data["channel"] = channel_name

        self._atomic_write_json(data, state_file)

    def get_changes_for_build(self, data: dict) -> str:
        """Format commit changes for display in webhook.
        
        Args:
            data: Build info dictionary containing commits list
            
        Returns:
            Formatted string with commit changes, one per line
        """
        change_lines = []
        for change in data["commits"]:
            commit_hash = convert_commit_hash_to_short(change["sha"])
            full_hash = change["sha"]
            summary = change["message"]
            summary = summary.strip()
            # summary = "Update DataConverter constants for 1.21.7\n\nhttps://github.com/PaperMC/DataConverter/commit/04b08a102a3d2473420edceed05420b5ccb3b771\n"
            # Replace the first \n\n with \n\t, then all others with \n
            summary = summary.split("\n")[0]
            # Find all unique PR/issue numbers referenced in the summary
            pr_numbers = set(re.findall(r"#(\d+)", summary))

            # Replace each occurrence exactly once so we don't wrap already-linked numbers
            for pr_number in pr_numbers:
                summary = summary.replace(
                    f"#{pr_number}",
                    f"[#{pr_number}](https://github.com/PaperMC/{self.project}/issues/{pr_number})",
                )
            github_url = f"https://github.com/PaperMC/{self.project}/commit/{full_hash}"
            # URL encode only the github_url parameter value, not the entire URL
            encoded_github_url = urllib.parse.quote(github_url, safe="")
            change_lines.append(f"- [{commit_hash}](https://diffs.dev/?github_url={encoded_github_url}) {summary}")
        return "\n".join(change_lines) + "\n" if change_lines else ""

    def get_latest_build(self) -> dict:
        """Get the latest build for the project.
        
        Returns:
            GraphQL response dictionary with latest build information
        """
        query = latest_query
        variables = {"project": self.project}
        result = client.execute(query, variable_values=variables)
        return result

    def get_all_versions(self) -> dict:
        """Get all versions with their latest builds.
        
        Returns:
            GraphQL response dictionary with all versions and builds
        """
        query = all_versions_query
        variables = {"project": self.project}
        result = client.execute(query, variable_values=variables)
        return result

    def _send_webhook_with_retry(self, hook_url: str, payload: dict, max_retries: int = 3) -> bool:
        """Send webhook with exponential backoff retry logic.
        
        Args:
            hook_url: Webhook URL to send to
            payload: Webhook payload dictionary
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    hook_url, json=payload, params={"with_components": "true"}, timeout=Config.WEBHOOK_TIMEOUT
                )
                response.raise_for_status()
                return True
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    delay = 2 ** attempt
                    logger.warning(f"Webhook attempt {attempt + 1} failed for {hook_url}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Failed to send webhook to {hook_url} after {max_retries} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error sending webhook to {hook_url}: {e}")
                return False
        return False

    def send_v2_webhook(
        self,
        hook_url: str,
        latest_build: str,
        latest_version: str,
        build_time: int,
        image_url: str,
        changes: str,
        download_url: str,
        drama: str | dict,
        channel_name: str,
        channel_changed: bool,
    ) -> None:
        """Send Discord webhook notification with build update information.
        
        Args:
            hook_url: Discord webhook URL
            latest_build: Latest build number string
            latest_version: Latest Minecraft version string
            build_time: Unix timestamp of build creation
            image_url: URL to project logo image
            changes: Formatted string of commit changes
            download_url: URL to download the build
            drama: Spigot drama response (string or dict)
            channel_name: Build channel name
            channel_changed: Whether the channel has changed from previous build
        """
        payload = {
            "components": [
                {
                    "type": 17,
                    "accent_color": CHANNEL_COLORS[channel_name.upper()],
                    "components": [
                        {
                            "type": 9,
                            "components": [
                                {
                                    "type": 10,
                                    "content": f"# {self.project.capitalize()} Update",
                                },
                                {
                                    "type": 10,
                                    "content": f"{channel_name} Build {latest_build} for {latest_version} is now available!\nReleased <t:{build_time}:R> (<t:{build_time}:f>)",
                                },
                            ],
                            "accessory": {"type": 11, "media": {"url": image_url}},
                        },
                        {"type": 14, "divider": True},
                        {"type": 10, "content": changes},
                        {"type": 14, "divider": True},
                        {
                            "type": 10,
                            "content": f"-# {drama.get('response', 'There\'s no drama :(') if isinstance(drama, dict) else str(drama)}",
                        },
                    ],
                },
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "label": "Download",
                            "style": 5,
                            "url": download_url,
                        }
                    ],
                },
            ],
            "flags": 1 << 15,
            "allowed_mentions": {"parse": []},
        }
        # If the channel changed, add another container to the components
        if channel_changed:
            changed_container = {
                "type": 10,
                "content": f"# {self.project.capitalize()} is now {channel_name}!",
            }
            payload["components"].append(changed_container)
        # Send webhook with retry logic
        self._send_webhook_with_retry(hook_url, payload)

    def _process_and_send_update(self, version_id: str, build_info: dict, channel_changed: bool) -> None:
        """Process a build and send webhook updates for it"""
        build_id = build_info["number"]
        channel_name = build_info["channel"]

        if config.DRY_RUN:
            logger.info(
                f"[DRY RUN] New build for {self.project} {version_id}. Would send update (Build {build_id})."
            )
            return

        logger.info(f"New build for {self.project} {version_id}. Sending update.")

        # Process build information
        changes = self.get_changes_for_build(build_info)
        # Safely access download URL with error handling
        download_info = build_info.get("download")
        if not download_info or "url" not in download_info:
            logger.warning(f"No download URL found for {self.project} {version_id} build {build_id}")
            return
        download_url = download_info["url"]
        try:
            build_time = int(convert_build_date(build_info["createdAt"]).timestamp())
        except ValueError as e:
            logger.error(f"Invalid build date format for {self.project} {version_id} build {build_id}: {e}")
            return

        # Get drama once for all webhooks
        drama = get_spigot_drama()

        # Send webhook to all configured URLs
        for hook in config.webhook_urls:
            self.send_v2_webhook(
                hook_url=hook,
                latest_build=build_id,
                latest_version=version_id,
                build_time=build_time,
                image_url=self.image_url,
                changes=changes,
                download_url=download_url,
                drama=drama,
                channel_name=channel_name.capitalize(),
                channel_changed=channel_changed,
            )

    def _check_version_for_update(
        self, version_id: str, build_info: dict, use_legacy_storage: bool = False
    ) -> bool:
        """Check if a version needs an update and process it if so.
        
        Args:
            version_id: Minecraft version string
            build_info: Build information dictionary from GraphQL
            use_legacy_storage: Whether to use legacy single-version storage format
            
        Returns:
            True if update was sent, False otherwise
        """
        build_id = build_info["number"]
        channel_name = build_info["channel"]

        if use_legacy_storage:
            # Use original storage methods for single version mode
            updated = self.up_to_date(version_id, build_id)
            stored_data = self.get_stored_data()
            channel_changed = (
                stored_data.get("channel", None) is not None
                and stored_data.get("channel", "") != channel_name
            )

            if not updated:
                self.write_to_json(version_id, build_id, channel_name)
                self._process_and_send_update(version_id, build_info, channel_changed)
                return True
        else:
            # Use version-specific storage methods for multi version mode
            updated = self.up_to_date_for_version(version_id, build_id)
            stored_version_data = self.get_stored_data_for_version(version_id)
            channel_changed = (
                stored_version_data.get("channel", None) is not None
                and stored_version_data.get("channel", "") != channel_name
            )

            if not updated:
                self.write_version_to_json(version_id, build_id, channel_name)
                self._process_and_send_update(version_id, build_info, channel_changed)
                return True

        return False

    def run(self) -> None:
        """Run the poller for this project, checking for updates."""
        logger.info(f"Checking {self.project}")

        if config.CHECK_ALL_VERSIONS:
            self._run_multi_version_mode()
        else:
            self._run_single_version_mode()

    def _run_single_version_mode(self) -> None:
        """Original behavior: check only the latest version"""
        try:
            gql_latest_build = self.get_latest_build()
            # Validate response structure
            if not self._validate_graphql_response(gql_latest_build, ["project", "versions", "edges"]):
                return
            if not gql_latest_build["project"]["versions"]["edges"]:
                logger.warning(f"No versions found for {self.project}")
                return
            if not self._validate_graphql_response(gql_latest_build["project"]["versions"]["edges"][0], ["node", "builds", "edges"]):
                return
            if not gql_latest_build["project"]["versions"]["edges"][0]["node"]["builds"]["edges"]:
                logger.warning(f"No builds found for {self.project}")
                return
            latest_version = gql_latest_build["project"]["versions"]["edges"][0]["node"]["key"]
            latest_build_info = gql_latest_build["project"]["versions"]["edges"][0]["node"]["builds"]["edges"][0]["node"]

            # Check and process update using extracted function
            update_sent = self._check_version_for_update(
                latest_version, latest_build_info, use_legacy_storage=True
            )

            if not update_sent:
                logger.info(f"Up to date for {self.project}")

        except KeyError as e:
            logger.error(f"Error getting latest build: {e}")
            return
        finally:
            # Wait to not hit discord API rate limits
            time.sleep(Config.RATE_LIMIT_DELAY)

    def _run_multi_version_mode(self) -> None:
        """New behavior: check all versions for updates"""
        try:
            # Get all versions to check for updates
            gql_all_versions = self.get_all_versions()
            # Validate response structure
            if not self._validate_graphql_response(gql_all_versions, ["project", "versions", "edges"]):
                return
            all_versions = gql_all_versions["project"]["versions"]["edges"]

            updates_sent = 0

            # Check each version for updates
            for version_edge in all_versions:
                version_data = version_edge["node"]
                version_id = version_data["key"]
                builds = version_data.get("builds", {}).get("edges", [])

                # Skip versions with no builds
                if not builds:
                    continue

                build_info = builds[0]["node"]

                # Check and process update using extracted function
                if self._check_version_for_update(
                    version_id, build_info, use_legacy_storage=False
                ):
                    updates_sent += 1
                    # Add small delay between versions to avoid rate limits
                    time.sleep(Config.VERSION_CHECK_DELAY)

            if updates_sent == 0:
                logger.info(f"Up to date for all {self.project} versions")
            else:
                logger.info(f"Sent {updates_sent} updates for {self.project}")

        except KeyError as e:
            logger.error(f"Error getting versions: {e}")
            return
        finally:
            # Wait to not hit discord API rate limits
            time.sleep(Config.RATE_LIMIT_DELAY)


def main():
    lock_file = Path("paper_poller.lock")
    lock = FileLock(str(lock_file), timeout=Config.LOCK_TIMEOUT)

    # Show configuration status
    if config.DRY_RUN:
        logger.info("Running in DRY RUN mode - no webhooks will be sent")
    if config.CHECK_ALL_VERSIONS:
        logger.info("Multi-version checking enabled - will check all Minecraft versions")
    else:
        logger.info("Single-version checking enabled - will check only the latest version")

    try:
        with lock:
            for project_name in config.PROJECTS:
                api = PaperAPI(project=project_name)
                api.run()
    except Timeout:
        logger.warning("Lock file is locked, exiting")
    except Exception as e:
        logger.error(f"Error during execution: {e}")


if __name__ == "__main__":
    main()
