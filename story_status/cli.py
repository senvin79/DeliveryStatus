"""CLI entry point for the story_status package.

Contains the ``main()`` function invoked by:
  - ``python story_status.py <JIRA_ID>``
  - ``python -m story_status <JIRA_ID>``
  - ``story-status <JIRA_ID>``  (when installed via pyproject.toml scripts)
"""

import os
import sys

from story_status.mcp_client import load_env, load_mcp_config, resolve_value
from story_status.jira_client import get_jira_server_info, fetch_jira_story
from story_status.github_client import get_github_server_info, fetch_github_pr_status
from story_status.summarizer import consolidate_and_summarize

_SEP = "=" * 60


def _require(key: str, env: dict[str, str]) -> str:
    """Return the config value for *key* or exit with a clear error.

    Args:
        key: Environment variable name.
        env: Loaded .env dict.

    Returns:
        Non-empty value string.
    """
    value = resolve_value(key, env)
    if not value:
        print(f"[ERROR] Required config '{key}' is not set. Add it to your .env file.")
        sys.exit(1)
    return value


def main() -> None:
    """Resolve config, fetch Jira + GitHub data, and print the LLM summary."""
    jira_id = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if not jira_id:
        jira_id = input(
            "Enter Jira issue key or project key\n"
            "  Issue key  : AI-1, SCRUM-42  → fetches that specific story\n"
            "  Project key: AI-Agent, SCRUM  → fetches all open issues\n"
            "Input: "
        ).strip()
    if not jira_id:
        print("[ERROR] Jira ID is required.")
        sys.exit(1)

    env = load_env()
    config = load_mcp_config()

    # All runtime config is injected — nothing is hardcoded
    cloud_id = _require("ATLASSIAN_CLOUD_ID", env)
    repo_owner = _require("GITHUB_REPO_OWNER", env)
    repo_name = _require("GITHUB_REPO_NAME", env)
    hf_token = resolve_value("HF_TOKEN", env)

    jira_server = get_jira_server_info(config, env)
    github_server = get_github_server_info(config, env)

    print(f"\n{_SEP}")
    print(f"  Story Status: {jira_id}")
    print(_SEP)

    print(f"\n[1/3] Fetching Jira story {jira_id} ...")
    jira_report = fetch_jira_story(jira_id, cloud_id=cloud_id, server_info=jira_server)

    print(f"\n[2/3] Searching GitHub PRs referencing {jira_id} in {repo_owner}/{repo_name} ...")
    github_report = fetch_github_pr_status(
        jira_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        server_info=github_server,
    )

    print("\n[3/3] Summarizing with LLM ...")
    summary = consolidate_and_summarize(jira_id, jira_report, github_report, hf_token)

    print(f"\n{_SEP}")
    print(f"  SUMMARY: {jira_id}")
    print(_SEP)
    print(summary)
    print(_SEP)
