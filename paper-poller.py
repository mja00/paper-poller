import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime as dt
from enum import Enum

import requests
from dotenv import load_dotenv
from filelock import FileLock, Timeout
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

load_dotenv()

# Configuration: Check all versions or just the latest
# Set PAPER_POLLER_CHECK_ALL_VERSIONS=true to enable multi-version checking
CHECK_ALL_VERSIONS = (
    os.getenv("PAPER_POLLER_CHECK_ALL_VERSIONS", "false").lower() == "true"
)

# Configuration: Dry run mode - process updates but don't send webhooks
# Set PAPER_POLLER_DRY_RUN=true to enable dry run mode
DRY_RUN = os.getenv("PAPER_POLLER_DRY_RUN", "false").lower() == "true"


class Color(Enum):
    BLUE = 0x2B7FFF
    GREEN = 0x4ECB8B
    PINK = 0xF06292
    ORANGE = 0xFFB74D
    PURPLE = 0x7E57C2
    RED = 0xEA5B6F
    YELLOW = 0xFFC859


COLORS = {color.name.lower(): color.value for color in Color}

CHANNEL_COLORS = {
    "ALPHA": Color.RED.value,
    "BETA": Color.YELLOW.value,
    "STABLE": Color.BLUE.value,
    "RECOMMENDED": Color.GREEN.value,
}

headers = {
    "User-Agent": "PaperMC Version Poller",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Check the ENV for a webhook URL
if os.getenv("WEBHOOK_URL"):
    print(f"Using webhook URL from ENV: {os.getenv('WEBHOOK_URL')}")
    try:
        webhook_urls = json.loads(os.getenv("WEBHOOK_URL"))
    except json.JSONDecodeError as e:
        print(f"Error parsing WEBHOOK_URL from environment: {e}")
        print("Falling back to default webhook URL")
        webhook_urls = ["https://httpbin.org/post"]
elif os.path.exists("webhooks.json"):
    print("Using webhook URL from webhooks.json")
    with open("webhooks.json", "r") as f:
        webhook_urls = json.load(f)["urls"]
else:
    print("No webhook URL found, using default")
    webhook_urls = ["https://httpbin.org/post"]

# Get start args
start_args = sys.argv[1:]
# If it includes --stdin, we'll read from stdin

# Check if there's anything coming in through STDIN
if "--stdin" in start_args:
    # If there is, read it as a json object
    try:
        data = json.loads(sys.stdin.read())
        # Grab the urls element from the json object
        webhook_urls = data["urls"]
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from stdin: {e}")
        print("Exiting - invalid JSON input")
        sys.exit(1)


gql_base = "https://fill.papermc.io/graphql"

transport = RequestsHTTPTransport(url=gql_base)
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


def convert_commit_hash_to_short(hash):
    return hash[:7]


def convert_build_date(date):
    # format: 2022-06-14T10:40:30.563Z
    return dt.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z")


def get_spigot_drama() -> str | dict:
    try:
        response = requests.get("https://drama.mart.fyi/api", headers=headers, timeout=10)
        response.raise_for_status()  # Raise exception for bad status codes
        data = response.json()
        return data
    except requests.RequestException as e:
        print(f"Error getting spigot drama: {e}")
        return "There's no drama :("
    except Exception as e:
        print(f"Error getting spigot drama: {e}")
        return "There's no drama :("


class PaperAPI:
    def __init__(self, base_url="https://api.papermc.io/v2", project="paper"):
        self.headers = {
            "User-Agent": "PaperMC Version Poller",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        self.base_url = base_url
        self.project = project
        self.image_url = ""
        if self.project == "paper":
            self.image_url = "https://assets.papermc.io/brand/papermc_logo.512.png"
        elif self.project == "folia":
            self.image_url = "https://assets.papermc.io/brand/folia_logo.256x139.png"
        elif self.project == "velocity":
            self.image_url = "https://assets.papermc.io/brand/velocity_logo.256x128.png"

    def up_to_date(self, version, build) -> bool:
        # Read out {project}_poller.json file
        try:
            with open(f"{self.project}_poller.json", "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"version": "", "build": ""}
        # Check if the version is up to date
        if data["version"] == version and data["build"] == build:
            return True
        else:
            return False

    def up_to_date_for_version(self, version, build) -> bool:
        # Read out {project}_poller.json file to check specific version
        try:
            with open(f"{self.project}_poller.json", "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"versions": {}}

        # Check if we have versions structure
        if "versions" not in data:
            # Legacy format, convert it
            if "version" in data and "build" in data:
                return data["version"] == version and data["build"] == build
            return False

        version_data = data["versions"].get(version, {})
        return version_data.get("build") == build

    def get_stored_data(self):
        try:
            with open(f"{self.project}_poller.json", "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"version": "", "build": "", "channel": ""}
        return data

    def get_stored_data_for_version(self, version):
        try:
            with open(f"{self.project}_poller.json", "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"versions": {}}

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

    def write_to_json(self, version, build, channel_name):
        data = {"version": version, "build": build, "channel": channel_name}
        with open(f"{self.project}_poller.json", "w") as f:
            json.dump(data, f)

    def write_version_to_json(self, version, build, channel_name):
        # Read existing data
        try:
            with open(f"{self.project}_poller.json", "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"versions": {}}

        # Ensure versions structure exists
        if "versions" not in data:
            data = {"versions": {}}

        # Update the specific version
        data["versions"][version] = {"build": build, "channel": channel_name}

        # Keep legacy format for latest version for backward compatibility
        data["version"] = version
        data["build"] = build
        data["channel"] = channel_name

        with open(f"{self.project}_poller.json", "w") as f:
            json.dump(data, f)

    def get_changes_for_build(self, data) -> str:
        return_string = ""
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
            return_string += f"- [{commit_hash}](https://diffs.dev/?github_url={encoded_github_url}) {summary}\n"
        return return_string

    def get_latest_build(self):
        query = latest_query
        variables = {"project": self.project}
        result = client.execute(query, variable_values=variables)
        return result

    def get_all_versions(self):
        query = all_versions_query
        variables = {"project": self.project}
        result = client.execute(query, variable_values=variables)
        return result

    def send_v2_webhook(
        self,
        hook_url,
        latest_build,
        latest_version,
        build_time,
        image_url,
        changes,
        download_url,
        drama,
        channel_name,
        channel_changed,
    ):
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
        # Then do a post to the webhook with ?with_components=true
        try:
            response = requests.post(
                hook_url, json=payload, params={"with_components": "true"}, timeout=30
            )
            response.raise_for_status()  # Raise exception for bad status codes
        except requests.RequestException as e:
            print(f"Error sending webhook to {hook_url}: {e}")
        except Exception as e:
            print(f"Unexpected error sending webhook to {hook_url}: {e}")

    def _process_and_send_update(self, version_id, build_info, channel_changed):
        """Process a build and send webhook updates for it"""
        build_id = build_info["number"]
        channel_name = build_info["channel"]

        if DRY_RUN:
            print(
                f"[DRY RUN] New build for {self.project} {version_id}. Would send update (Build {build_id})."
            )
            return

        print(f"New build for {self.project} {version_id}. Sending update.")

        # Process build information
        changes = self.get_changes_for_build(build_info)
        # Safely access download URL with error handling
        download_info = build_info.get("download")
        if not download_info or "url" not in download_info:
            print(f"Warning: No download URL found for {self.project} {version_id} build {build_id}")
            return
        download_url = download_info["url"]
        build_time = int(convert_build_date(build_info["createdAt"]).timestamp())

        # Send webhook to all configured URLs
        for hook in webhook_urls:
            drama = get_spigot_drama()
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
        self, version_id, build_info, use_legacy_storage=False
    ):
        """Check if a version needs an update and process it if so"""
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

    def run(self):
        current_time = dt.now()
        print(f"[{current_time}] ", end="")

        if CHECK_ALL_VERSIONS:
            self._run_multi_version_mode()
        else:
            self._run_single_version_mode()

    def _run_single_version_mode(self):
        """Original behavior: check only the latest version"""
        try:
            gql_latest_build = self.get_latest_build()
            latest_version = gql_latest_build["project"]["versions"]["edges"][0]["node"]["key"]
            latest_build_info = gql_latest_build["project"]["versions"]["edges"][0]["node"]["builds"]["edges"][0]["node"]

            # Check and process update using extracted function
            update_sent = self._check_version_for_update(
                latest_version, latest_build_info, use_legacy_storage=True
            )

            if not update_sent:
                print(f"Up to date for {self.project}")

        except KeyError as e:
            print(f"Error getting latest build: {e}")
            return
        finally:
            # Wait 2 seconds to not hit discord API rate limits
            time.sleep(2)

    def _run_multi_version_mode(self):
        """New behavior: check all versions for updates"""
        try:
            # Get all versions to check for updates
            gql_all_versions = self.get_all_versions()
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
                    time.sleep(1)

            if updates_sent == 0:
                print(f"Up to date for all {self.project} versions")
            else:
                print(f"Sent {updates_sent} updates for {self.project}")

        except KeyError as e:
            print(f"Error getting versions: {e}")
            return
        finally:
            # Wait 2 seconds to not hit discord API rate limits
            time.sleep(2)


def main():
    lock_file = "paper_poller.lock"
    lock = FileLock(lock_file, timeout=10)

    # Show configuration status
    if DRY_RUN:
        print("Running in DRY RUN mode - no webhooks will be sent")
    if CHECK_ALL_VERSIONS:
        print("Multi-version checking enabled - will check all Minecraft versions")
    else:
        print("Single-version checking enabled - will check only the latest version")

    try:
        with lock:
            paper = PaperAPI()
            paper.run()
            folia = PaperAPI(project="folia")
            folia.run()
            velocity = PaperAPI(project="velocity")
            velocity.run()
            waterfall = PaperAPI(project="waterfall")
            waterfall.run()
    except Timeout:
        print("Lock file is locked, exiting")
    except Exception as e:
        print(f"Error during execution: {e}")


if __name__ == "__main__":
    main()
