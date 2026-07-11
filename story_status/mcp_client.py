"""Shared MCP HTTP JSON-RPC client and workspace configuration loaders.

Provides a synchronous HTTP/SSE-compatible client for JSON-RPC 2.0 MCP
servers plus helpers to load ``.env`` and ``mcp.json`` from the workspace root.
"""

import base64
import json
import os
from pathlib import Path
from typing import Any

import requests

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = WORKSPACE_DIR / "mcp.json"
ENV_PATH = WORKSPACE_DIR / ".env"


class MCPClient:
    """Synchronous HTTP JSON-RPC 2.0 client for a remote MCP endpoint.

    Handles both plain-JSON and SSE-wrapped (``data: {...}``) responses and
    automatically sends the required ``notifications/initialized`` handshake.
    """

    def __init__(self, endpoint: str, headers: dict[str, str] | None = None) -> None:
        """Initialize the client.

        Args:
            endpoint: Full MCP server URL.
            headers: Optional extra HTTP headers (e.g. Authorization).
        """
        self.endpoint = endpoint.rstrip("/")
        self.headers = headers or {}
        self._request_id = 1
        self.session_id: str | None = None

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return the parsed response dict.

        Transparently handles SSE-wrapped ``data: {...}`` responses.

        Args:
            payload: JSON-RPC request dict.

        Returns:
            Parsed response dict.

        Raises:
            RuntimeError: On HTTP 4xx/5xx responses.
        """
        request_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self.session_id:
            request_headers["mcp-session-id"] = self.session_id

        rpc_method = payload.get("method", "?")
        auth_value = request_headers.get("Authorization", "")
        auth_preview = (
            auth_value[:22] + "…[masked]" if len(auth_value) > 22 else "(none)"
        )
        print(f"[TRACE] → {rpc_method}  endpoint={self.endpoint}")
        print(f"[TRACE]   auth header : {auth_preview}")
        if self.session_id:
            print(f"[TRACE]   session-id  : {self.session_id}")
        print(f"[TRACE]   full request : {json.dumps(payload)[:3000]}")

        response = requests.post(
            self.endpoint,
            headers=request_headers,
            json=payload,
            timeout=60,
        )
        print(f"[TRACE] ← HTTP {response.status_code}  content-type={response.headers.get('content-type', 'n/a')}")
        print(f"[TRACE]   response body: {response.text[:5000]}")
        if response.status_code >= 400:
            print(f"[TRACE]   error body  : {response.text[:500]}")
            raise RuntimeError(
                f"MCP request failed HTTP {response.status_code}: {response.text[:500]}"
            )
        if response.headers.get("mcp-session-id"):
            self.session_id = response.headers["mcp-session-id"]
            print(f"[TRACE]   session-id  : {self.session_id} (assigned)")
        if not response.text:
            print("[TRACE]   body        : (empty)")
            return {}
        try:
            parsed = response.json()
            print(f"[TRACE]   parse-path  : plain JSON  keys={list(parsed.keys())}")
            return parsed
        except ValueError:
            # SSE format: extract JSON from the first valid "data: {...}" line
            print("[TRACE]   parse-path  : SSE — scanning data: lines")
            for line in response.text.splitlines():
                stripped = line.strip()
                if stripped.startswith("data:"):
                    candidate = stripped[5:].strip()
                    if candidate and candidate != "[DONE]":
                        try:
                            parsed = json.loads(candidate)
                            print(f"[TRACE]   SSE parsed   : keys={list(parsed.keys())}")
                            return parsed
                        except json.JSONDecodeError:
                            continue
            print(f"[TRACE]   SSE fallback: no valid data: line found — returning raw ({len(response.text)} chars)")
            return {"raw": response.text}

    def initialize(self) -> dict[str, Any]:
        """Perform the MCP initialization handshake.

        Returns:
            Server capabilities dict from the initialize response.
        """
        print(f"[TRACE] MCPClient.initialize  endpoint={self.endpoint}")
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "story-status", "version": "1.0"},
            },
        }
        self._request_id += 1
        result = self._post(message)
        server_info = result.get("result", {}).get("serverInfo", {})
        capabilities = list(result.get("result", {}).get("capabilities", {}).keys())
        print(f"[TRACE]   server      : {server_info.get('name', '?')} v{server_info.get('version', '?')}")
        print(f"[TRACE]   capabilities: {capabilities}")
        self._notify_initialized()
        return result

    def _notify_initialized(self) -> None:
        """Fire-and-forget the required MCP ``notifications/initialized`` message."""
        notification: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        request_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self.session_id:
            request_headers["mcp-session-id"] = self.session_id
        try:
            requests.post(self.endpoint, headers=request_headers, json=notification, timeout=30)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] notifications/initialized failed (non-fatal): {exc}")

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the tools advertised by the MCP server.

        Returns:
            List of tool definition dicts.
        """
        print("[TRACE] MCPClient.list_tools")
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/list",
            "params": {},
        }
        self._request_id += 1
        response = self._post(request)
        tools = response.get("result", {}).get("tools", [])
        tools = tools if isinstance(tools, list) else []
        names = [t.get("name") for t in tools if isinstance(t, dict)]
        print(f"[TRACE]   tools ({len(names)}): {names}")
        return tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a named MCP tool.

        Args:
            tool_name: Exact name as advertised by the server.
            arguments: Tool-specific argument dict.

        Returns:
            Raw JSON-RPC response dict.
        """
        print(f"[TRACE] MCPClient.call_tool  name={tool_name}")
        print(f"[TRACE]   arguments   : {list(arguments.keys())}")
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        self._request_id += 1
        return self._post(request)


# ---------------------------------------------------------------------------
# Configuration loaders
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load key=value pairs from the workspace ``.env`` file.

    Returns:
        Dict of variable names to values. Empty dict when file is absent.
    """
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_mcp_config() -> dict[str, Any]:
    """Load and parse ``mcp.json`` from the workspace root.

    Returns:
        Parsed mcp.json dict.

    Raises:
        FileNotFoundError: When mcp.json does not exist.
    """
    return json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def build_basic_auth_header(email: str, api_token: str) -> str:
    """Construct a Base64-encoded HTTP Basic authorization header value.

    Args:
        email: Atlassian account email.
        api_token: Atlassian API token.

    Returns:
        Header value of the form ``"Basic <base64(email:token)>"``.
    """
    encoded = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    return f"Basic {encoded}"


def resolve_value(key: str, *sources: dict[str, str]) -> str:
    """Return the first non-empty value for *key* across the provided dicts.

    Args:
        key: Variable name to look up.
        *sources: Dicts searched in priority order.

    Returns:
        First non-empty value found, or empty string.
    """
    for source in sources:
        value = source.get(key, "")
        if value:
            return value
    return os.getenv(key, "")


# ---------------------------------------------------------------------------
# Response parsing helper
# ---------------------------------------------------------------------------

def extract_content_text(context_result: dict[str, Any]) -> str:
    """Pull the first text block out of a JSON-RPC tool-call result.

    Args:
        context_result: Raw MCPClient.call_tool result dict.

    Returns:
        Inner text string, or empty string when not found.
    """
    result = context_result.get("result", context_result)
    content_blocks = result.get("content", [])
    if not isinstance(content_blocks, list):
        return ""
    for block in content_blocks:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            return block["text"]
    return ""
