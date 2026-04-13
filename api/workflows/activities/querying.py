# api/workflows/activities/querying.py
#
# All activities for the Answer Query workflow.

import os

from temporalio import activity

from api.db.connection import ensure_pool, get_conn
from api.workflows.models import RepoInfo, SpecialistInput


@activity.defn
async def ensure_repo_indexed(repo_url: str) -> RepoInfo:
    """
    Check that the repo has been indexed and has a clone on disk.
    Returns the clone path so the specialist agent can use file tools.
    """
    await ensure_pool()

    async with get_conn() as conn:
        row = await conn.execute(
            "SELECT clone_path FROM repos WHERE repo_url = %s",
            (repo_url,),
        )
        repo = await row.fetchone()

    if not repo:
        raise ValueError(
            f"Repo '{repo_url}' has not been indexed yet. "
            "Call POST /index first."
        )

    clone_path = repo["clone_path"]
    if not os.path.isdir(clone_path):
        raise ValueError(
            f"Repo '{repo_url}' was indexed but the clone is missing. "
            "Re-index with POST /index."
        )

    activity.logger.info(f"Repo indexed, clone at {clone_path}")
    return RepoInfo(repo_url=repo_url, clone_path=clone_path)


@activity.defn
async def route_query(question: str) -> str:
    """
    Router: classifies the question and picks a specialist agent.
    Uses GPT-4o-mini for fast, cheap classification.

    - "where is X?" / "find X" → explorer
    - "explain X" / "how does X work?" → explainer
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify this question about a codebase. "
                    "Reply with exactly one word: explorer or explainer.\n\n"
                    "explorer = finding or locating things "
                    "(where, which file, find, locate, show me)\n"
                    "explainer = understanding or explaining things "
                    "(explain, how, what, why, describe, walk me through)"
                ),
            },
            {"role": "user", "content": question},
        ],
        max_tokens=10,
    )

    answer = (response.choices[0].message.content or "").strip().lower()

    # Parse — default to explainer if unclear
    if "explorer" in answer:
        agent = "explorer"
    else:
        agent = "explainer"

    activity.logger.info(f"Routed '{question[:60]}...' -> {agent}")
    return agent


@activity.defn
async def answer_with_specialist(input: SpecialistInput) -> str:
    """Run the specialist agent against the cloned repo."""
    if input.agent == "explorer":
        from api.agents.explorer import run_explorer
        return await run_explorer(
            question=input.question,
            repo_dir=input.clone_path,
            repo_url=input.repo_url,
        )

    if input.agent == "explainer":
        from api.agents.explainer import run_explainer
        return await run_explainer(
            question=input.question,
            repo_dir=input.clone_path,
            repo_url=input.repo_url,
        )

    raise ValueError(f"Unknown agent: {input.agent}")
