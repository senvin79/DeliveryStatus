"""LLM summarizer — consolidate Jira and GitHub reports into a story status summary."""


def consolidate_and_summarize(
    jira_id: str,
    jira_report: str,
    github_report: str,
    hf_token: str,
) -> str:
    """Send combined Jira + GitHub data to an LLM and return a sprint summary.

    Falls back to a plain-text consolidation when the token is absent or
    the ``huggingface_hub`` package is not installed.

    Args:
        jira_id: Jira story key used in the LLM prompt context.
        jira_report: Formatted plain-text Jira story report.
        github_report: Formatted plain-text GitHub PR report.
        hf_token: Hugging Face Inference API token.

    Returns:
        LLM-generated summary string, or raw combined text on failure.
    """
    combined = (
        f"=== Jira Story: {jira_id} ===\n\n"
        f"{jira_report}\n\n"
        f"=== GitHub PR Status ===\n\n"
        f"{github_report}"
    )

    if not hf_token:
        print("[WARN] HF_TOKEN not set — returning raw consolidated report.")
        return combined

    try:
        from huggingface_hub import InferenceClient  # noqa: PLC0415
    except ImportError:
        print("[WARN] huggingface_hub not installed — returning raw consolidated report.")
        return combined

    client = InferenceClient(token=hf_token)

    try:
        completion = client.chat_completion(
            model="Qwen/Qwen2.5-Coder-7B-Instruct",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Scrum Master assistant. Given a Jira story and its "
                        "linked GitHub PR data, produce a concise story status summary "
                        "covering: current lifecycle stage, assignee, any blockers, "
                        "and recommended next action."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Summarize the full story status for {jira_id}:\n\n"
                        f"{combined[:8000]}"
                    ),
                },
            ],
            max_tokens=600,
        )
        return completion.choices[0].message.content
    except Exception as exc:
        print(f"[WARN] LLM call failed: {exc} — returning raw report.")
        return combined
