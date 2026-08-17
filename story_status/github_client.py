"""GitHub MCP client — fetch PR status referencing a Jira story key.

Credentials are resolved (in priority order) from:
  1. mcp.json  → mcpServers.github-mcp.env.GITHUB_PERSONAL_ACCESS_TOKEN
  2. .env file → GITHUB_PERSONAL_ACCESS_TOKEN or GITHUB_TOKEN
  3. OS environment variables
"""

import json
import re
from typing import Any

from .mcp_client import MCPClient, extract_content_text, resolve_value


def get_github_server_info(
    config: dict[str, Any],
    env: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """Extract the GitHub MCP endpoint and build auth headers.

    Args:
        config: Parsed mcp.json dict.
        env: Loaded .env dict.

    Returns:
        Tuple of (endpoint_url, headers_dict).

    Raises:
        ValueError: When no GitHub PAT is found in any source.
    """
    server = config.get("mcpServers", {}).get("github-mcp", {})
    endpoint = str(server.get("url") or server.get("endpoint") or "")
    server_env: dict[str, str] = {str(k): str(v) for k, v in server.get("env", {}).items()}

    print(f"[TRACE] GitHub server_info  endpoint={endpoint or '(not set)'}")

    token = resolve_value("GITHUB_PERSONAL_ACCESS_TOKEN", server_env, env) or resolve_value(
        "GITHUB_TOKEN", server_env, env
    )
    if not token:
        raise ValueError(
            "No GitHub PAT found. Set GITHUB_PERSONAL_ACCESS_TOKEN in .env."
        )
    source = "mcp.json env" if resolve_value("GITHUB_PERSONAL_ACCESS_TOKEN", server_env) else ".env"
    preview = f"Bearer {token[:12]}…[masked]"
    print(f"[TRACE]   auth source  : {source}  value={preview}")
    return endpoint, {"Authorization": f"Bearer {token}"}


def _discover_search_tool(client: MCPClient) -> str | None:
    """Discover which PR/issue search tool the server exposes.

    Calls ``tools/list``, logs all available tools, and returns the first
    matching search tool name from a priority list.

    Args:
        client: An already-initialized MCPClient.

    Returns:
        Tool name string, or None when no match found.
    """
    tools = client.list_tools()
    tool_names = {t.get("name") for t in tools if isinstance(t, dict)}
    print(f"[INFO] GitHub MCP tools: {', '.join(sorted(tool_names))}")

    candidates = [
        "search_issues",
        "search_issues_and_pull_requests",
        "search_pull_requests",
    ]
    return next((name for name in candidates if name in tool_names), None)


def _extract_prs(context_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract a PR list from a raw MCP tool-call result.

    Handles both ``list_pull_requests`` (returns a list) and
    ``search_issues`` (returns ``{"items": [...]}``) response shapes.

    Args:
        context_result: Raw MCPClient.call_tool result dict.

    Returns:
        List of PR dicts, empty on parse failure.
    """
    inner_text = extract_content_text(context_result)
    if not inner_text:
        print("[WARN] extract_content_text returned empty string")
        return []
    try:
        data = json.loads(inner_text)
        if isinstance(data, list):
            return data
        return data.get("items", data.get("pull_requests", []))
    except json.JSONDecodeError as exc:
        print("[WARN] GitHub MCP response is not valid JSON -- cannot parse PRs.")
        print(f"[WARN]   JSONDecodeError : {exc}")
        return []


def _derive_stage(pr: dict[str, Any]) -> str:
    """Map raw PR fields to a human-readable lifecycle stage label.

    Args:
        pr: GitHub PR dict.

    Returns:
        Stage label string.
    """
    if pr.get("merged") or pr.get("merged_at"):
        return "MERGED"
    state = pr.get("state", "open")
    if state == "closed":
        return "CLOSED (not merged)"
    if pr.get("draft"):
        return "DRAFT / IN PROGRESS"
    review_decision = pr.get("review_decision", "")
    if review_decision == "APPROVED":
        return "APPROVED / READY TO MERGE"
    if review_decision == "CHANGES_REQUESTED":
        return "CHANGES REQUESTED"
    return "OPEN / IN REVIEW"


def _format_single_pr(pr: dict[str, Any]) -> list[str]:
    """Render one GitHub PR dict as a list of plain-text lines.

    Args:
        pr: GitHub PR dict from the API response.

    Returns:
        List of formatted text lines.
    """
    number = pr.get("number", "?")
    title = pr.get("title", "No title")
    author = (pr.get("user") or pr.get("author") or {}).get("login", "unknown")
    base_ref = (pr.get("base") or {}).get("ref", "?")
    head_ref = (pr.get("head") or {}).get("ref", "?")
    stage = _derive_stage(pr)

    body = re.sub(r"<[^>]+>", "", (pr.get("body") or "")).strip()
    if len(body) > 300:
        body = body[:300] + "..."

    labels = [lbl.get("name", "") for lbl in (pr.get("labels") or []) if isinstance(lbl, dict)]

    lines: list[str] = [
        f"PR #{number}: {title}",
        f"  Stage  : {stage}",
        f"  Author : {author}",
        f"  Branch : {head_ref} → {base_ref}",
    ]
    if body:
        lines.append(f"  Body   : {body}")
    if labels:
        lines.append(f"  Labels : {', '.join(labels)}")
    lines.append("")
    return lines


def format_prs_for_llm(
    prs: list[dict[str, Any]],
    repo_owner: str,
    repo_name: str,
) -> str:
    """Convert GitHub PR dicts to plain-text suitable for LLM input.

    Args:
        prs: List of GitHub PR dicts.
        repo_owner: GitHub org or user name.
        repo_name: Repository name.

    Returns:
        Formatted plain-text string.
    """
    if not prs:
        return f"No pull requests found in {repo_owner}/{repo_name}."

    lines: list[str] = [f"GitHub PRs — {repo_owner}/{repo_name} — {len(prs)} total\n"]
    for pr in prs:
        lines.extend(_format_single_pr(pr))
    return "\n".join(lines)


def fetch_github_pr_status(
    jira_id: str,
    *,
    repo_owner: str,
    repo_name: str,
    server_info: tuple[str, dict[str, str]],
    max_results: int = 20,
) -> str:
    """Fetch GitHub PR status for all PRs referencing a Jira story key.

    Args:
        jira_id: Jira issue key used as the search term (e.g. ``"SCRUM-9"``).
        repo_owner: GitHub org or user name.
        repo_name: Repository name without owner prefix.
        server_info: ``(endpoint, headers)`` from ``get_github_server_info``.
        max_results: Maximum number of PRs to retrieve.

    Returns:
        Plain-text formatted PR status report.
    """
    endpoint, headers = server_info
    if not endpoint:
        return "No GitHub MCP endpoint configured. Set github-mcp.url in mcp.json."

    print(f"[TRACE] fetch_github_pr_status  jira_id={jira_id}  repo={repo_owner}/{repo_name}")
    print(f"[TRACE]   max_results    : {max_results}")
    print(f"[TRACE]   auth present   : {'Authorization' in headers}")
    client = MCPClient(endpoint=endpoint, headers=headers)

    try:
        client.initialize()
        search_tool = _discover_search_tool(client)

        if not search_tool:
            return "No PR search tool found on the GitHub MCP server."

        search_query = f"repo:{repo_owner}/{repo_name} type:pr {jira_id}"
        print(f"[INFO] GitHub search: '{search_tool}' query='{search_query}'")

        result = client.call_tool(search_tool, {"query": search_query, "per_page": max_results})
        prs = _extract_prs(result)
        print(f"[INFO] Found {len(prs)} matching PR(s)")
        return format_prs_for_llm(prs, repo_owner, repo_name)

    except Exception as exc:
        return f"GitHub fetch failed: {exc}"
