# PYTHON_ARGCOMPLETE_OK

import argparse
import argcomplete
import json
import logging
import signal
import sys
from github import Github, GithubException
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


# Handle a control-c gracefully
def signal_handler(signal, frame):
    print("\n\nExiting...")
    sys.exit(0)


def create_html_report(json_data):
    data_dict = json.loads(json_data)

    issues_data = []
    for issue in data_dict['issues']:
        issues_data.append({'title': issue['title'], 'description': issue['description'], 'comments': ''})
        for comment in issue['comments']:
            issues_data.append({'title': issue['title'], 'description': '', 'comments': comment['body']})

    milestones_data = [milestone['title'] for milestone in data_dict['milestones']]

    # Create dataframe for issues and milestones
    issues_df = pd.DataFrame(issues_data)
    milestones_df = pd.DataFrame(milestones_data, columns=['title'])

    # Generate HTML tables from dataframes
    issues_html = issues_df.to_html(index=False)
    milestones_html = milestones_df.to_html(index=False)

    # Combine issues and milestones tables into one HTML file
    html_report = f"""
    <h1>GitHub Issues</h1>
    {issues_html}
    <h1>GitHub Milestones</h1>
    {milestones_html}
    """

    # Write HTML report to a file
    with open("github_report.html", "w") as f:
        f.write(html_report)

class GithubWorker:
    def __init__(self, owner, repo, api_key, log):
        self.api = Github(api_key)
        rate_limit = self.api.get_rate_limit().core.remaining
        if rate_limit <= 0:
            log.error("GitHub API rate limit has been reached. Exiting...")
            sys.exit(1)
        try:
            self.repo = self.api.get_repo(f"{owner}/{repo}")
            self.issues = self.repo.get_issues(state="all")
            self.milestones = self.repo.get_milestones()
        except GithubException as e:
            log.error(f"Error fetching data from Github: {str(e)}")
            sys.exit(1)
        self.log = log

    # TODO: Add dates to issues and milestones
    def get_issues(self):
        data = {}
        data['issues'] = []
        data['milestones'] = []
        for issue in self.issues:
            issue_data = {
                'title': issue.title,
                'description': issue.body,
                'comments': [{'body': comment.body} for comment in issue.get_comments()]
            }
            data['issues'].append(issue_data)

        for milestone in self.milestones:
            milestone_data = {
                'title': milestone.title
            }
            data['milestones'].append(milestone_data)

        return json.dumps(data)


if __name__ == "__main__":
    root = logging.getLogger()
    log = logging.getLogger("gh-issues-report")
    log_handler = logging.StreamHandler(sys.stdout)

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

    if args.github_repo and "/" in args.github_repo:
        owner, repo = args.github_repo.split("/")
        log.debug("GitHub repo: %s/%s" % (owner, repo))
    else:
        log.error("Missing or incorrect GitHub repo argument. It should be in the format user/repo")
        sys.exit(1)

    if args.api_key:
        token = args.api_key
    else:
        log.error("Missing GitHub API key argument")
        sys.exit(1)

    gh = GithubWorker(owner, repo, token, log)
    report_data = gh.get_issues()
    create_html_report(report_data)


