# DeliveryStatus
Agentic AI to provide Delivery Status of a work item by fetching information from Jira, Github and more...built using langchain and langgraph
 
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
    ├── agent_tools.py    ← build_tools → LangChain tools wrapping the fetchers
    ├── agent_graph.py    ← LangGraph ReAct agent (build_agent, run_agent)
    └── cli.py            ← main() — runs the agent end-to-end

Running the script
python .\story_status.py SCRUM-9

============================================================
  SUMMARY: SCRUM-9
============================================================
### Story Status Summary for SCRUM-9

**Lifecycle Stage:** In Progress  
**Assignee:** Senthil   
**Blockers:** None noted  
**Recommended Next Action:** Verify if Senthil has completed his testing as per his recent comment and address any issues before reopening the GitHub PR for merging.

### Details
- **Current Lifecycle Stage**: The story is currently being worked on but has not been completed yet.
- **Assignee**: Senthil is responsible for this story.
- **Comments & Updates**: Senthil mentioned that testing was in progress and would be done by the following day.
- **GitHub PR Stage**: The PR for this story was closed without being merged.
- **Body of PR**: The changes relate to integrating MCP into CLI interface.
```
Next Steps:
Currently support JIRA, Github and can be extended to confluence, test case management system, CI/CD system to provide overall summary of a epic, story...
