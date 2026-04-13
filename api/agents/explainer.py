# api/agents/explainer.py
#
# Explainer agent — answers "explain X" and "how does X work?" questions
# using RAG (semantic search over embedded code) + file reading.
#
# Tools:
#   search_indexed — semantic search over pgvector (finds relevant code by meaning)
#   read_file      — read specific files (reused from explorer.py)
#
# Strategy: search_indexed finds the most relevant chunks first, then the
# agent reads those files to build a detailed explanation. This is different
# from the Explorer which uses grep-style keyword search.

import os

from agents import Agent, Runner, function_tool, RunContextWrapper

from api.agents.explorer import ExplorerContext, read_file
from api.db.connection import ensure_pool, get_conn


@function_tool
async def search_indexed(
    ctx: RunContextWrapper[ExplorerContext],
    query: str,
    limit: int = 5,
) -> str:
    """Search for code chunks by meaning using semantic similarity.

    Args:
        query: Natural language description of what you're looking for, e.g. "authentication logic" or "database connection setup".
        limit: Maximum number of results to return. Defaults to 5.
    """
    from openai import AsyncOpenAI

    await ensure_pool()

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Embed the query
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=[query],
    )
    query_embedding = response.data[0].embedding

    # Query pgvector for similar chunks
    async with get_conn() as conn:
        rows = await conn.execute(
            """
            SELECT
                file_path,
                start_line,
                end_line,
                content,
                1 - (embedding <=> %s::vector) AS similarity
            FROM chunks
            WHERE repo_url = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (str(query_embedding), ctx.context.repo_url, str(query_embedding), limit),
        )
        rows = await rows.fetchall()

    if not rows:
        return f"No indexed chunks found for '{query}'"

    # Format results for the agent
    results = []
    for row in rows:
        sim = round(row["similarity"], 3)
        results.append(
            f"[{sim}] {row['file_path']}:{row['start_line']}-{row['end_line']}\n"
            f"{row['content'][:500]}"
        )

    return "\n\n---\n\n".join(results)


# ── Agent definition ─────────────────────────────────────────────────────────

EXPLAINER_INSTRUCTIONS = """\
You are the Explainer agent — a specialist at understanding and explaining code.

Your job is to answer "explain X" and "how does X work?" questions. You have two tools:
- search_indexed: Semantic search — finds code chunks by meaning (not just keywords)
- read_file: Read specific files to understand their full context

Strategy:
1. Use search_indexed to find code related to the topic.
2. Read the most relevant files to understand how they connect.
3. Synthesize a clear explanation of how the system works.
4. Always cite specific file paths and line numbers.

Focus on HOW things work and WHY they're designed that way, not just WHERE
they are. Connect the pieces into a coherent narrative.
"""

explainer_agent = Agent(
    name="Explainer",
    instructions=EXPLAINER_INSTRUCTIONS,
    tools=[search_indexed, read_file],
    model="gpt-4o-mini",
)


async def run_explainer(question: str, repo_dir: str, repo_url: str) -> str:
    """
    Run the Explainer agent against an indexed repo.
    Returns the agent's final answer as a string.
    """
    context = ExplorerContext(repo_dir=repo_dir, repo_url=repo_url)
    result = await Runner.run(
        explainer_agent,
        input=question,
        context=context,
    )
    return result.final_output
