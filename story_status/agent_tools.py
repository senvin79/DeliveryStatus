"""LangChain tool wrappers around the existing Jira and GitHub MCP fetchers.

These wrap the plain-function clients in ``jira_client.py`` / ``github_client.py``
so a LangGraph agent can decide which ones to call and with what arguments.
"""

from typing import Any

from langchain_core.tools import BaseTool, tool

from story_status.github_client import fetch_github_pr_status, get_github_server_info
from story_status.jira_client import fetch_jira_story, get_jira_server_info


def build_tools(
    config: dict[str, Any],
    env: dict[str, str],
    *,
    cloud_id: str,
    repo_owner: str,
    repo_name: str,
) -> list[BaseTool]:
    """Build the Jira and GitHub tools bound to resolved runtime config.

    Args:
        config: Parsed mcp.json dict.
        env: Loaded .env dict.
        cloud_id: Atlassian cloud id/base URL.
        repo_owner: GitHub org or user name.
        repo_name: GitHub repository name.

    Returns:
        List ``[jira_tool, github_pr_tool]`` ready for ``bind_tools``/``create_react_agent``.
    """
    jira_server = get_jira_server_info(config, env)
    github_server = get_github_server_info(config, env)

    @tool
    def jira_tool(jira_id: str) -> str:
        """Fetch a Jira story (or all open issues of a project) by key, e.g. 'SCRUM-9' or 'SCRUM'."""
        return fetch_jira_story(jira_id, cloud_id=cloud_id, server_info=jira_server)

    @tool
    def github_pr_tool(jira_id: str) -> str:
        """Fetch GitHub pull requests referencing the given Jira issue key in the configured repo."""
        return fetch_github_pr_status(
            jira_id, repo_owner=repo_owner, repo_name=repo_name, server_info=github_server
        )

    return [jira_tool, github_pr_tool]
