"""Jira MCP client — fetch and format a story by Jira issue key.

Credentials are resolved (in priority order) from:
  1. mcp.json  → mcpServers.atlassian-mcp.env
  2. .env file → ATLASSIAN_EMAIL + ATLASSIAN_API_TOKEN
  3. OS environment variables
"""

import json
import re
from typing import Any

from .mcp_client import MCPClient, build_basic_auth_header, extract_content_text, resolve_value


_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$", re.IGNORECASE)


def _build_jql(jira_input: str) -> str:
    """Build a JQL query from a Jira issue key or project key.

    Args:
        jira_input: Either an issue key (``"AI-1"``, ``"SCRUM-42"``) or a
            project key / name (``"AI-Agent"``, ``"SCRUM"``).

    Returns:
        Valid JQL string.

    Examples:
        >>> _build_jql("AI-1")
        "key = 'AI-1'"
        >>> _build_jql("AI-Agent")
        "project = 'AI-Agent' AND status != Done ORDER BY updated DESC"
    """
    if _ISSUE_KEY_RE.match(jira_input.strip()):
        return f"key = '{jira_input.strip()}'"
    return f"project = '{jira_input.strip()}' AND status != Done ORDER BY updated DESC"


def get_jira_server_info(
    config: dict[str, Any],
    env: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """Extract the Jira MCP endpoint and build auth headers.

    Args:
        config: Parsed mcp.json dict.
        env: Loaded .env dict.

    Returns:
        Tuple of (endpoint_url, headers_dict).
    """
    server = config.get("mcpServers", {}).get("atlassian-mcp", {})
    endpoint = str(server.get("url") or server.get("endpoint") or "")
    server_env: dict[str, str] = {str(k): str(v) for k, v in server.get("env", {}).items()}

    print(f"[TRACE] Jira server_info  endpoint={endpoint or '(not set)'}")

    # Prefer a pre-built Authorization value (legacy mcp.json env support)
    auth_header = resolve_value("Authorization", server_env) or resolve_value(
        "ATLASSIAN_AUTHORIZATION", env
    )
    if auth_header:
        preview = auth_header[:22] + "…[masked]" if len(auth_header) > 22 else auth_header
        print(f"[TRACE]   auth source  : ATLASSIAN_AUTHORIZATION  value={preview}")
        return endpoint, {"Authorization": auth_header}

    # Build Basic auth from email + token
    email = resolve_value("ATLASSIAN_EMAIL", server_env, env)
    api_token = resolve_value("ATLASSIAN_API_TOKEN", server_env, env)
    if email and api_token:
        print(f"[TRACE]   auth source  : ATLASSIAN_EMAIL + ATLASSIAN_API_TOKEN  email={email}")
        return endpoint, {"Authorization": build_basic_auth_header(email, api_token)}

    print("[TRACE]   auth source  : MISSING — no credentials found in mcp.json or .env")
    return endpoint, {}


def _extract_issues(context_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the issues list from a raw Jira MCP tool-call result.

    Args:
        context_result: Raw MCPClient.call_tool result.

    Returns:
        List of Jira issue dicts, empty on parse failure.
    """
    inner_text = extract_content_text(context_result)
    if not inner_text:
        return []
    try:
        return json.loads(inner_text).get("issues", [])
    except json.JSONDecodeError:
        print("[WARN] Jira MCP response is not valid JSON — cannot parse issues.")
        return []


def _format_issue_comments(comments: list[dict[str, Any]]) -> list[str]:
    """Format the last three comments of an issue into text lines.

    Args:
        comments: List of Jira comment dicts.

    Returns:
        List of formatted text lines.
    """
    lines: list[str] = ["  Recent comments:"]
    for comment in comments[-3:]:
        author = (comment.get("author") or {}).get("displayName", "Unknown")
        body = re.sub(r"<[^>]+>", "", comment.get("body") or "").strip()
        if len(body) > 200:
            body = body[:200] + "..."
        date = comment.get("created", "")[:10]
        lines.append(f"    - {author} ({date}): {body}")
    return lines


def _format_single_issue(issue: dict[str, Any]) -> list[str]:
    """Render one Jira issue dict as a list of plain-text lines.

    Args:
        issue: Jira issue dict from the API response.

    Returns:
        List of formatted text lines.
    """
    fields = issue.get("fields", {})
    key = issue.get("key", "?")
    summary = fields.get("summary", "No summary")
    status = fields.get("status", {}).get("name", "Unknown")
    assignee_obj = fields.get("assignee")
    assignee = assignee_obj.get("displayName", "Unassigned") if assignee_obj else "Unassigned"

    raw_desc = fields.get("description") or ""
    description = re.sub(r"\*{1,2}[^*]+\*{1,2}", "", raw_desc).strip() or "No description"
    if len(description) > 400:
        description = description[:400] + "..."

    lines: list[str] = [
        f"[{key}] {summary}",
        f"  Status   : {status}",
        f"  Assignee : {assignee}",
        f"  Description: {description}",
    ]

    comments_data = fields.get("comment") or {}
    comments = comments_data.get("comments", []) if isinstance(comments_data, dict) else []
    if comments:
        lines.extend(_format_issue_comments(comments))

    lines.append("")
    return lines


def format_issues_for_llm(issues: list[dict[str, Any]]) -> str:
    """Convert Jira issue dicts to plain-text suitable for LLM input.

    Args:
        issues: List of Jira issue dicts.

    Returns:
        Formatted plain-text string.
    """
    if not issues:
        return "No Jira issues found."

    lines: list[str] = [f"Jira Issues — {len(issues)} total\n"]
    for issue in issues:
        lines.extend(_format_single_issue(issue))
    return "\n".join(lines)


def fetch_jira_story(
    jira_id: str,
    *,
    cloud_id: str,
    server_info: tuple[str, dict[str, str]],
    fields: list[str] | None = None,
) -> str:
    """Fetch a single Jira story via the MCP server and return a formatted report.

    Args:
        jira_id: Jira issue key (e.g. ``"AI-1"`` or ``"SCRUM-9"``).
        cloud_id: Atlassian cloud base URL (e.g. ``"https://org.atlassian.net/"``).
        server_info: ``(endpoint, headers)`` from ``get_jira_server_info``.
        fields: Optional list of Jira fields. Defaults to common sprint fields.

    Returns:
        Plain-text Jira story report.
    """
    endpoint, headers = server_info
    if not endpoint:
        return "No Jira MCP endpoint configured. Set atlassian-mcp.url in mcp.json."

    resolved_fields = fields or ["summary", "description", "status", "assignee", "comment"]
    jql = _build_jql(jira_id)
    print(f"[TRACE] fetch_jira_story  input={jira_id}  cloud_id={cloud_id}")
    print(f"[TRACE]   jql            : {jql}")
    print(f"[TRACE]   fields         : {resolved_fields}")
    print(f"[TRACE]   auth present   : {'Authorization' in headers}")
    client = MCPClient(endpoint=endpoint, headers=headers)

    try:
        client.initialize()
        result = client.call_tool(
            "searchJiraIssuesUsingJql",
            {
                "cloudId": cloud_id,
                "jql": jql,
                "maxResults": 10,
                "fields": resolved_fields,
            },
        )
        issues = _extract_issues(result)
        return format_issues_for_llm(issues)
    except Exception as exc:
        return f"Jira fetch failed: {exc}"
