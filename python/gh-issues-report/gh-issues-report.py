from github import Github

# TODO: get the values from CLI
token = 'your_token'  # Your personal access token
owner = 'owner'  # The owner of the repository
repo = 'repo'  # The name of the repository


class GithubWorker:
    def __init__(self, repo, api_key, log):
        self.api = Github(api_key)
        self.repo = self.api.get_repo(f"{owner}/{repo}")
        self.issues = self.repo.get_issues(state="all")
        self.milestones = self.repo.get_milestones()
        self.log = log

    def print_issues:
        for issue in issues:
            print(f"Issue ID: {issue.id}, Issue Title: {issue.title}")
            comments = issue.get_comments()
            for comment in comments:
                print(f"Comment ID: {comment.id}, Comment Body: {comment.body}")
        # TODO: Check and handle the rate limit of Github API - g.get_rate_limit().





