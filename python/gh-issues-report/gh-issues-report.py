# PYTHON_ARGCOMPLETE_OK

import argparse
import argcomplete
import json
import logging
import re
import signal
import sys
import time
from github import Github, GithubException, RateLimitExceededException
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument(
    "-v",
    "--verbose",
    help="Display verbose operation tracing during command execution",
    action="store_true",
    default=False,
)
parser.add_argument(
    "-g",
    "--github-repo",
    type=str,
    help="GitHub repo in a format user/repo-name (example: droideck/389-ds-base)",
)
parser.add_argument(
    "-a",
    "--api-key",
    type=str,
    nargs="?",
    help="GitHub API key"
)

argcomplete.autocomplete(parser)

report_data = {}
root = logging.getLogger()
log = logging.getLogger("gh-issues-report")
log_handler = logging.StreamHandler(sys.stdout)

# Handle a control-c gracefully
def signal_handler(signal, frame):
    print("\nCTRL-C detected. Displaying the gathered report...\n")
    create_html_report(report_data, log)
    sys.exit(0)

def remove_meta_content(text):
    # Pattern for the "Comment from..." text
    comment_pattern = r'\*\*Comment from .+?\*\*\n\n'
    text = re.sub(comment_pattern, '', text, flags=re.DOTALL)

    # Pattern for the "Cloned from Pagure issue..." text
    cloned_pattern = r'Cloned from Pagure issue:.+?\n'
    text = re.sub(cloned_pattern, '', text, flags=re.DOTALL)

    # Pattern for the "Created at..." text
    cloned_pattern = r'- Created at .+?---\n\n'
    text = re.sub(cloned_pattern, '', text, flags=re.DOTALL)

    text = text.strip().replace('\\n', '\n').replace('\\r', '\r')
    return text


def create_html_report(data_dict, log):
    log.debug("Creating issues dataframes...")
    issues_data = []
    for issue in data_dict['issues']:
        # Process description once and then replace newlines for HTML
        description_text = remove_meta_content(issue['description'])
        # Normalize all newline types to \n, then convert to <br>
        description_html = description_text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')

        issues_data.append({
            'Title (URL)': f'<a href="{issue["url"]}">{issue["title"]}</a>',
            'Description': description_html,
            # The 'Comments' column for the main issue row also shows the issue's description
            'Comments': description_html,
        })
        for comment in issue['comments']:
            if "**Metadata Update from" in comment['body']:
                continue
            # Process comment body and then replace newlines for HTML
            comment_body_text = remove_meta_content(comment['body'])
            # Normalize all newline types to \n, then convert to <br>
            comment_body_html = comment_body_text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')
            issues_data.append({
                'Title (URL)': '',
                'Description': '',
                'Comments': comment_body_html
            })

    issues_df = pd.DataFrame(issues_data)

    log.debug("Adding Tailwind CSS classes to HTML tables...")
    def add_table_classes(html_string):
        html_string = html_string.replace(
            "<table>",
            # Added table-fixed for predictable column widths
            '<table class="min-w-full table-fixed divide-y divide-gray-200 border border-gray-300 shadow-md rounded-lg">'
        )
        html_string = html_string.replace(
            "<thead>",
            '<thead class="bg-gray-100">'
        )
        html_string = html_string.replace(
            "<th>",
            '<th class="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider border-b border-gray-300">'
        )
        html_string = html_string.replace(
            "<td>",
            # Removed max-w-xl, relying on CSS for column widths; kept break-words and align-top
            '<td class="px-6 py-4 text-sm text-gray-700 border-b border-gray-300 break-words align-top">'
        )
        return html_string

    log.debug("Generate HTML tables from dataframes...")
    issues_html = add_table_classes(issues_df.to_html(index=False, escape=False))

    log.debug("Combining HTML tables into one HTML file...")
    html_report = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <title>GitHub Issues Report</title>
        <style>
            /* For alternating row colors */
            tbody tr:nth-child(odd) {{
                background-color: #ffffff; /* white */
            }}
            tbody tr:nth-child(even) {{
                background-color: #f8f9fa; /* lighter gray */
            }}
            /* Ensure links within table cells are styled nicely */
            td a {{
                color: #007bff; /* Link color */
                text-decoration: none;
            }}
            td a:hover {{
                text-decoration: underline;
            }}
            /* Column widths - applied because 'table-fixed' is on the table */
            thead th:nth-child(1), tbody td:nth-child(1) {{ width: 30%; }} /* Title (URL) - wider */
            thead th:nth-child(2), tbody td:nth-child(2) {{ width: 35%; }} /* Description */
            thead th:nth-child(3), tbody td:nth-child(3) {{ width: 35%; }} /* Comments */
        </style>
    </head>
    <body class="bg-gray-50 p-8">
        <div class="container mx-auto bg-white shadow-lg rounded-lg p-6">
            <h1 class="text-4xl font-bold mb-6 text-center text-gray-800">GitHub Issues Report</h1>
            {issues_html}
        </div>
    </body>
    </html>
    """

    log.debug("Writing HTML report to file...")
    with open("github_report.html", "w") as f:
        f.write(html_report)


class GithubWorker:
    def __init__(self, owner, repo, api_key, log):
        self.log = log
        self.api = Github(api_key)
        self.log.debug("Initialising GithubWorker...")
        try:
            rate_limit = self.api.get_rate_limit().core.remaining
            self.log.debug(f"Rate limit remaining: {rate_limit}")
            if rate_limit <= 0:
                self.log.error("GitHub API rate limit has been reached. Exiting...")
                sys.exit(1)
            self.log.debug("Fetching repo and issues data from Github...")
            self.repo = self.api.get_repo(f"{owner}/{repo}")
            self.issues = self.repo.get_issues(state="open", sort="created", direction="asc")
            #self.milestones = self.repo.get_milestones()
        except GithubException as e:
            self.log.error(f"Error fetching data from Github: {str(e)}")
            sys.exit(1)

    def get_issues(self):
        self.log.debug("Creating issues and milestones JSON...")
        report_data['issues'] = []
        try:
            for issue in self.issues:
                issue_data = {
                    'title': issue.title,
                    'description': issue.body,
                    'url': issue.html_url,
                    'comments': [{'body': comment.body, 'created_at': comment.created_at.isoformat()} for comment in issue.get_comments()]
                }
                report_data['issues'].append(issue_data)
                self.log.debug(f"Issue fetched: {issue_data['title']}")
                rate_limit = self.api.get_rate_limit().core.remaining
                self.log.debug(f"Rate limit remaining: {rate_limit}")
        except RateLimitExceededException as e:
            self.log.error(f"Rate limit exceeded error: {str(e)}")
            time_to_reset = self.api.rate_limiting_resettime - int(time.time())
            if time_to_reset > 0:
                self.log.error(f"Waiting {time_to_reset} seconds before trying again...")
                time.sleep(time_to_reset)
        except GithubException as e:
            self.log.error(f"Error fetching issues or milestones: {str(e)}")
            sys.exit(1)

        self.log.debug("JSON completed.")


if __name__ == "__main__":
    args = parser.parse_args()
    if args.verbose:
        log.setLevel(logging.DEBUG)
        log_format = "%(levelname)s: %(message)s"
    else:
        log.setLevel(logging.INFO)
        log_format = "%(message)s"
    log_handler.setFormatter(logging.Formatter(log_format))
    root.addHandler(log_handler)

    log.debug("GitHub Issues Report tool")
    log.debug("Called with: %s" % args)

    signal.signal(signal.SIGINT, signal_handler)

    if args.github_repo:
        # Handle both full GitHub URLs and user/repo format
        repo_input = args.github_repo.strip()

        if repo_input.startswith('https://github.com/') or repo_input.startswith('http://github.com/'):
            # Extract owner/repo from full URL
            # Remove the protocol and domain
            path_part = repo_input.split('github.com/')[-1]
            # Remove any trailing slashes or .git extension
            path_part = path_part.rstrip('/').rstrip('.git')

            if "/" in path_part:
                owner, repo = path_part.split("/", 1)  # Split only on first '/'
            else:
                log.error("Invalid GitHub URL format. Expected: https://github.com/user/repo")
                sys.exit(1)
        elif "/" in repo_input:
            # Handle user/repo format
            parts = repo_input.split("/")
            if len(parts) == 2:
                owner, repo = parts
            else:
                log.error("Invalid GitHub repo format. Expected: user/repo or https://github.com/user/repo")
                sys.exit(1)
        else:
            log.error("Invalid GitHub repo format. Expected: user/repo or https://github.com/user/repo")
            sys.exit(1)

        log.debug("GitHub repo: %s/%s" % (owner, repo))
    else:
        log.error("Missing GitHub repo argument")
        sys.exit(1)

    if args.api_key:
        token = args.api_key
    else:
        log.error("Missing GitHub API key argument")
        sys.exit(1)

    gh = GithubWorker(owner, repo, token, log)
    gh.get_issues()
    create_html_report(report_data, log)


