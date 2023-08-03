# PYTHON_ARGCOMPLETE_OK

import logging
import argparse
import argcomplete
import sys
import signal
from github import Github, GithubException

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


class GithubWorker:
    def __init__(self, owner, repo, api_key, log):
        self.api = Github(api_key)
        rate_limit = self.api.get_rate_limit().core.remaining
        # log.info(f"GitHub API rate limit: {rate_limit}")
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

    def print_issues(self):
        for issue in self.issues:
            print(f"Issue ID: {issue.id}, Issue Title: {issue.title}")
            comments = issue.get_comments()
            for comment in comments:
                print(f"Comment ID: {comment.id}, Comment Body: {comment.body}")
            print("")
        for milestone in self.milestones:
            print(f"Milestone ID: {milestone.id}, Milestone Title: {milestone.title}")



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
    gh.print_issues()


