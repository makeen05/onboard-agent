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
    Router agent picks a specialist.
    M3: always returns "explorer".
    M4+: replace with LLM classification.
    """
    activity.logger.info(f"Routing: {question[:80]}...")
    return "explorer"


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

    raise ValueError(f"Unknown agent: {input.agent}")
