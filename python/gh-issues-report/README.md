# GitHub Issues Reporter

A Python tool that fetches GitHub issues and generates a clean HTML report for easy viewing and analysis. 📊

## Features

- Fetches all open issues from any public GitHub repository
- Includes issue comments and descriptions
- Handles GitHub API rate limiting gracefully
- Supports both GitHub URLs and simple repo format
- Ctrl+C safe - generates report with collected data if interrupted

## Installation

Install the required Python packages:

```bash
uv venv
source .venv/bin/activate
uv pip install argparse argcomplete PyGithub pandas
```

## Setup

### GitHub API Token

You'll need a GitHub Personal Access Token to use this tool:

1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Click "Generate new token"
3. Give it a descriptive name and select the `repo` scope for private repos, or `public_repo` for public repos only (read-only)
4. Copy the generated token

## Usage

```bash
python3 gh-issues-report.py -v -g <repository> -a <api-token>
```

### Command Line Arguments

| Flag | Description | Required |
|------|-------------|----------|
| `-v, --verbose` | Enable detailed logging output | No |
| `-g, --github-repo` | GitHub repository (see formats below) | Yes |
| `-a, --api-key` | Your GitHub Personal Access Token | Yes |

### Repository Format

The tool accepts repositories in two formats:

**Simple format:**
```bash
-g "username/repository-name"
```

**Full GitHub URL:**
```bash
-g "https://github.com/username/repository-name"
```

### Examples

```bash
# Using simple format
python3 gh-issues-report.py -v -g "389ds/389-ds-base" -a "github_YOUR_TOKEN_HERE"

# Using full URL
python3 gh-issues-report.py -v -g "https://github.com/389ds/389-ds-base" -a "github_YOUR_TOKEN_HERE"

# Without verbose output
python3 gh-issues-report.py -g "microsoft/vscode" -a "github_YOUR_TOKEN_HERE"
```

## Output

The tool generates `github_report.html` in the current directory containing:

- Issue titles (linked to GitHub)
- Issue descriptions and comments
- Filtered content (removes metadata and cloned issue references)

## Rate Limiting

The tool monitors GitHub API rate limits and will:
- Display remaining requests in verbose mode
- Wait automatically if rate limit is exceeded
- Exit gracefully if no requests remain

## Error Handling

- **Ctrl+C**: Generates report with data collected so far
- **Invalid repository format**: Clear error message with expected formats
- **Missing API key**: Prompts for required authentication
- **API errors**: Detailed error messages with suggested solutions

## Notes

- Only fetches **open** issues (sorted by creation date)
- Requires internet connection to access GitHub API
- Generated HTML file uses CDN-hosted Tailwind CSS
