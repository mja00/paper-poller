# Paper Poller

A Python script that monitors PaperMC projects (Paper, Folia, Velocity, Waterfall) for new builds and automatically announces them on Discord with rich embeds.

## Features

- **Multi-Project Support**: Monitors Paper, Folia, Velocity, and Waterfall builds
- **Rich Discord Embeds**: Beautiful embeds with project logos, build information, and download links
- **Change Tracking**: Displays commit changes and links to GitHub issues/PRs
- **Channel Detection**: Automatically detects and announces channel changes (e.g., from experimental to recommended)
- **Spigot Drama Integration**: Includes fun "drama" messages from the Spigot community
- **Rate Limiting**: Built-in protection against Discord API rate limits
- **File Locking**: Prevents multiple instances from running simultaneously
- **Flexible Configuration**: Support for environment variables, JSON files, and stdin input

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/paper-poller.git
cd paper-poller
```

2. Install dependencies with [uv](https://docs.astral.sh/uv/):
```bash
uv sync
```

## Configuration

### Method 1: Environment Variables
Set the `WEBHOOK_URL` environment variable with a JSON array of Discord webhook URLs:
```bash
export WEBHOOK_URL='["https://discord.com/api/webhooks/your-webhook-url"]'
```

### Method 2: JSON File
Create a `webhooks.json` file in the project directory:
```json
{
    "urls": [
        "https://discord.com/api/webhooks/your-webhook-url"
    ]
}
```

### Method 3: Stdin Input
Pass webhook URLs through stdin with the `--stdin` flag:
```bash
echo '{"urls": ["https://discord.com/api/webhooks/your-webhook-url"]}' | uv run paper-poller.py --stdin
```

## Usage

### Basic Usage
Run the script to check for updates on all supported projects:
```bash
uv run paper-poller.py
```

### With Stdin Input
```bash
echo '{"urls": ["your-webhook-url"]}' | uv run paper-poller.py --stdin
```

### Cron Job Setup
To run the script periodically, add it to your crontab:
```bash
# Check for updates every 10 minutes
*/10 * * * * cd /path/to/paper-poller && uv run paper-poller.py
```

### Exit Codes
The poller exits non-zero when no valid webhook URLs are configured and when a run fails with an unexpected error, so cron mail and systemd monitoring can catch problems. A run skipped because another instance holds the lock still exits 0. Note that a failure in one project aborts the remaining projects for that run; they are picked up again on the next run.

## What It Monitors

The script automatically monitors these PaperMC projects:
- **Paper**: The main Minecraft server software
- **Folia**: Multi-threaded Minecraft server software
- **Velocity**: Modern proxy for Minecraft servers
- **Waterfall**: BungeeCord fork for Minecraft servers

## Discord Output

The script sends rich Discord embeds containing:
- Project logo and branding
- Build version and number
- Release timestamp (relative and absolute)
- List of commit changes with GitHub links
- Download button linking to the build
- Fun "drama" messages from the Spigot community
- Channel change notifications when applicable

## File Structure

```
paper-poller/
├── paper-poller.py          # Main script
├── pyproject.toml            # Project metadata and dependencies
├── uv.lock                   # Pinned dependency lockfile
├── webhooks.example.json    # Example webhook configuration
├── {project}_poller.json    # State files for each project (auto-generated)
└── paper_poller.lock        # Lock file to prevent concurrent runs
```

## Testing

### Running Tests

The project includes a comprehensive test suite using pytest:

```bash
# Install dependencies (including the test stack) into the project venv
uv sync

# Run all tests
uv run pytest

# Run tests with coverage report
uv run pytest --cov=. --cov-report=html

# Run specific test categories
uv run pytest -m unit          # Run only unit tests
uv run pytest -m integration   # Run only integration tests

# Run tests in verbose mode
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_paper_api.py

# Run a specific test
uv run pytest tests/test_paper_api.py::TestPaperAPIInitialization::test_default_initialization
```

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures and test configuration
├── test_utils.py         # Unit tests for utility functions
├── test_paper_api.py     # Unit tests for PaperAPI class
└── test_integration.py   # Integration tests with mocked APIs
```

### Test Coverage

The tests cover:
- Utility functions (date conversion, hash shortening, etc.)
- PaperAPI initialization and configuration
- State management (JSON file reading/writing)
- Version tracking (single and multi-version modes)
- Webhook payload generation
- Dry run mode
- Error handling
- Integration flows with mocked GraphQL responses

### Continuous Integration

Tests run automatically on:
- Every push to main/develop branches
- Every pull request
- Multiple Python versions (3.10, 3.11, 3.12, 3.13)
- Multiple operating systems (Ubuntu, macOS, Windows)

## Dependencies

- `requests`: HTTP requests for API calls
- `python-dotenv`: Environment variable loading
- `gql[all]`: GraphQL client for PaperMC API
- `filelock`: File locking to prevent concurrent execution

### Testing Dependencies

- `pytest`: Testing framework
- `pytest-cov`: Coverage reporting
- `pytest-mock`: Mocking utilities
- `responses`: HTTP request mocking
- `freezegun`: Time mocking

## State Management

The script maintains state files for each project (`paper_poller.json`, `folia_poller.json`, etc.) to track:
- Latest version seen
- Latest build number
- Current channel (experimental, recommended, etc.)

This prevents duplicate notifications and enables channel change detection.

## Error Handling

- Graceful handling of API failures
- File locking prevents multiple instances
- Rate limiting protects against Discord API limits
- Comprehensive error logging

## Contributing

Feel free to submit issues and pull requests to improve the project!

## Discord Community

Join our Discord community for support and discussions:
[Paper Chan Discord](https://paper-chan.moe/discord)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

