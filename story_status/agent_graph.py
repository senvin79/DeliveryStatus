"""LangGraph ReAct agent — decides which tools to call to answer a story-status request.

Unlike the fixed jira→github→summarize pipeline, this lets the LLM choose which
tools to invoke (and in what order/how many times) based on the request, and
keeps per-story conversational memory via a checkpointer.
"""

from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

_SYSTEM_PROMPT = (
    "You are a Scrum Master assistant. You have tools to fetch Jira stories and "
    "GitHub pull request status. Call whichever tools you need (a full story "
    "status question usually needs both) then produce a concise final summary "
    "covering: current lifecycle stage, assignee, any blockers, and recommended "
    "next action."
)


def build_agent(hf_token: str, tools: list[BaseTool]) -> Any:
    """Construct a checkpointed ReAct agent bound to the given tools.

    Args:
        hf_token: Hugging Face Inference API token.
        tools: LangChain tools the agent may call.

    Returns:
        A compiled LangGraph agent invoked as ``agent.invoke({"messages": [...]}, config=...)``.
    """
    llm = ChatHuggingFace(
        llm=HuggingFaceEndpoint(
            repo_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            huggingfacehub_api_token=hf_token,
            task="conversational",
        )
    )
    return create_react_agent(
        llm,
        tools,
        prompt=SystemMessage(content=_SYSTEM_PROMPT),
        checkpointer=MemorySaver(),
    )


def run_agent(jira_id: str, hf_token: str, tools: list[BaseTool]) -> str:
    """Run the agent end-to-end for a single Jira id and return the final summary text.

    Args:
        jira_id: Jira issue key or project key.
        hf_token: Hugging Face Inference API token.
        tools: LangChain tools the agent may call.

    Returns:
        Final assistant message content.
    """
    agent = build_agent(hf_token, tools)
    thread_config = {"configurable": {"thread_id": jira_id}}
    result = agent.invoke(
        {"messages": [("user", f"Give me the full story status for {jira_id}.")]},
        config=thread_config,
    )
    return result["messages"][-1].content
