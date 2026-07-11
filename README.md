# DeliveryStatus
Agent to provide Delivery Status of a work item by fetching information from Jira, Github and more...
 w
OBJETIVE: Program Managers, Product Owners, Scrum Masters can easily get the summarized version of project work item
Agent uses MCP clients to discover the tool and use the tool to connect to JIRA, Github to get information about project item and use LLM to summarize and next steps.
```
**Directory Structure**
{noformat}
storyStatus/
├── .env.example          ← copy to .env, fill credentials — never committed
├── .gitignore            ← excludes .env, __pycache__, .venv, dist
├── mcp.json              ← server URLs only, zero secrets
├── pyproject.toml        ← project metadata + hatchling build
├── story_status.py       ← CLI entry point
└── story_status/
    ├── __init__.py
    ├── mcp_client.py     ← MCPClient, load_env, load_mcp_config, SSE+init fix
    ├── jira_client.py    ← fetch_jira_story (injectable)
    ├── github_client.py  ← fetch_github_pr_status (tool discovery + injectable)
    └── summarizer.py     ← consolidate_and_summarize → Qwen LLM
```
Next Steps:
Currently support JIRA, Github and can be extended to confluence, test case management system, CI/CD system to provide overall summary of a epic, story...
