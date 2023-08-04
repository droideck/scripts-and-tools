## GH Issues Reporter
Hello there! GH Issues Reporter transforms your GitHub issues into a nice table that you can process as you want! 🧙‍♂️

## Installation
Before running, you need to make sure the following packages are installed:

```bash
pip install argparse argcomplete PyGithub pandas
```

Now, on to the main event!

## Usage
It several command-line arguments:

```bash
python3 gh_issues_reporter.py -v -g [your-github-repo] -a [your-github-api-key]
```

Here's a brief overview of each flag:

-v or --verbose: If you want to know every tiny, meticulous detail of what's going on behind the scenes, this is the one for you. The "verbose" mode.
-g or --github-repo: Here's where you plug in your GitHub repository in the format "user/repo-name". For example, "droideck/389-ds-base". This is not optional, folks. We're not mind-readers.
-a or --api-key: Now, this is your GitHub API key.

You should see an HTML report created in your project directory. Enjoy! Or at least, as much as you can enjoy issue reports...
