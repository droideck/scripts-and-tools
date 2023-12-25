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
    #json_data = json.dumps(report_data)
    #data_dict = json.loads(json_data)

    log.debug("Creating issues and milestones dataframes...")
    issues_data = []
    for issue in data_dict['issues']:
        description = remove_meta_content(issue['description'])
        issues_data.append({
            'Title (URL)': f'<a href="{issue["url"]}">{issue["title"]}</a>',
            'Description': remove_meta_content(description),
            #'created_at': issue['created_at'],
            #'updated_at': issue['updated_at'],
            'Comments': remove_meta_content(description),
        })
        for comment in issue['comments']:
            if "**Metadata Update from" in comment['body']:
                continue
            issues_data.append({
                'Title (URL)': '',
                'Description': '',
            #    'created_at': comment['created_at'],
            #    'updated_at': '',
                'Comments': remove_meta_content(comment['body'])
            })

    #milestones_data = []
    #for milestone in data_dict['milestones']:
    #    milestones_data.append({
    #        'title': f'<a href="{milestone["url"]}">{milestone["title"]}</a>',
    #    #    'created_at': milestone['created_at'],
    #    #    'updated_at': milestone['updated_at']
    #    })

    issues_df = pd.DataFrame(issues_data)
    #milestones_df = pd.DataFrame(milestones_data)

    log.debug("Adding Tailwind CSS classes to HTML tables...")
    def add_table_classes(html_string):
        html_string = html_string.replace("<table>", '<table class="table-auto w-full">')
        html_string = html_string.replace("<th>", '<th class="px-4 py-2">')
        html_string = html_string.replace("<td>", '<td class="border px-4 py-2">')
        return html_string

    log.debug("Generate HTML tables from dataframes...")
    issues_html = add_table_classes(issues_df.to_html(index=False, escape=False))
    #milestones_html = add_table_classes(milestones_df.to_html(index=False))

    log.debug("Combining HTML tables into one HTML file...")
    html_report = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body>
        <h1 class="text-3xl font-bold mb-4 text-center">GitHub Issues</h1>
        {issues_html}
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
        #report_data['milestones'] = []
        try:
            #for milestone in self.milestones:
            #    milestone_data = {
            #        'title': milestone.title,
            #        'url': milestone.html_url,
            #        'created_at': milestone.created_at.isoformat(),
            #        'updated_at': milestone.updated_at.isoformat()
            #    }
            #    report_data['milestones'].append(milestone_data)
            #    self.log.debug(f"Milestone fetched: {milestone_data['title']}")

            for issue in self.issues:
                issue_data = {
                    'title': issue.title,
                    'description': issue.body,
            #        'created_at': issue.created_at.isoformat(),
            #        'updated_at': issue.updated_at.isoformat(),
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
    gh.get_issues()
    create_html_report(report_data, log)


