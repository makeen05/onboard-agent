# api/main.py
#
# FastAPI application — the HTTP layer.
# Receives requests, starts Temporal workflows, queries the DB.
#
# New in M2:
#   POST /index  — start the indexing pipeline for a GitHub repo
#   GET  /index/{workflow_id} — check if indexing is done
#   POST /search — semantic search over indexed code chunks

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client

from api.db.connection import close_pool, get_conn, init_pool
from api.workflows.models import AnswerQueryInput, IndexRepoInput
from api.workflows.index_repo import IndexRepoWorkflow
from api.workflows.answer_query import AnswerQueryWorkflow

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "onboard-queue"


# ── Lifespan ──────────────────────────────────────────────────────────────────
# FastAPI's "lifespan" runs setup code when the app starts and teardown code
# when it shuts down. It replaces the old @app.on_event("startup") pattern.
# We use it to create the DB connection pool once at startup.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()   # create DB pool + run schema.sql
    yield               # app runs here
    await close_pool()  # clean up on shutdown


app = FastAPI(title="Onboard Agent API", version="0.3.0", lifespan=lifespan)

# Allow the Next.js frontend to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev; lock down in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    repo_url: str       # which indexed repo to query against

class QueryResponse(BaseModel):
    workflow_id: str
    answer: str
    agent: str          # which specialist agent answered

class IndexRequest(BaseModel):
    repo_url: str   # e.g. "https://github.com/some/repo"

class IndexResponse(BaseModel):
    workflow_id: str   # use this to poll GET /index/{workflow_id}
    status: str        # "started"

class IndexStatusResponse(BaseModel):
    workflow_id: str
    status: str        # "running" | "completed" | "failed"
    result: dict | None = None

class SearchRequest(BaseModel):
    query: str         # natural language, e.g. "how does authentication work"
    repo_url: str      # which repo to search (you can have multiple indexed)
    limit: int = 5     # how many chunks to return

class SearchResult(BaseModel):
    file_path:  str
    start_line: int
    end_line:   int
    content:    str
    similarity: float  # 0–1, higher = more relevant

class SearchResponse(BaseModel):
    results: list[SearchResult]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/repos")
async def list_repos() -> list[dict]:
    """Return all indexed repos (for the sidebar)."""
    async with get_conn() as conn:
        rows = await conn.execute(
            "SELECT id, repo_url, indexed_at FROM repos ORDER BY indexed_at DESC"
        )
        rows = await rows.fetchall()
    return [
        {"id": row["id"], "repo_url": row["repo_url"], "indexed_at": str(row["indexed_at"])}
        for row in rows
    ]


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """
    Ask a question about an indexed repository.

    Uses the Answer Query workflow (Temporal) which:
      1. ensure_repo_indexed — checks the repo is indexed + gets clone path
      2. route_query         — Router picks a specialist (M3: always Explorer)
      3. answer_with_specialist — the agent uses file tools on the saved clone

    For M3, all questions go to the Explorer agent. In M4+ a Router will
    classify the question and hand off to the right specialist.
    """
    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"query-{uuid.uuid4().hex[:8]}"

    result = await client.execute_workflow(
        AnswerQueryWorkflow.run,
        AnswerQueryInput(question=req.question, repo_url=req.repo_url),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return QueryResponse(
        workflow_id=workflow_id,
        answer=result.answer,
        agent=result.agent,
    )


@app.post("/index", response_model=IndexResponse)
async def start_index(req: IndexRequest) -> IndexResponse:
    """
    Start the indexing pipeline for a GitHub repo.
    Returns immediately with a workflow_id — indexing happens in the background.
    Poll GET /index/{workflow_id} to check when it's done.
    """
    client = await Client.connect(TEMPORAL_HOST)

    # Use the repo URL in the workflow ID so re-indexing the same repo
    # is easy to track in the Temporal UI.
    safe_url = req.repo_url.replace("https://", "").replace("/", "-")
    workflow_id = f"index-{safe_url}-{uuid.uuid4().hex[:8]}"

    # start_workflow (not execute_workflow) returns immediately without waiting.
    # The workflow runs in the background. We return the ID so the client can poll.
    await client.start_workflow(
        IndexRepoWorkflow.run,
        IndexRepoInput(repo_url=req.repo_url),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return IndexResponse(workflow_id=workflow_id, status="started")


@app.get("/index/{workflow_id}", response_model=IndexStatusResponse)
async def get_index_status(workflow_id: str) -> IndexStatusResponse:
    """
    Check the status of an indexing workflow.
    Temporal stores the status of every workflow — running, completed, or failed.
    """
    client = await Client.connect(TEMPORAL_HOST)

    # get_workflow_handle gives us a handle to query a workflow by ID
    handle = client.get_workflow_handle(workflow_id)

    try:
        desc = await handle.describe()
        status = desc.status.name.lower()  # "running", "completed", "failed", etc.
        result = None

        if status == "completed":
            result_obj = await handle.result()
            # result_obj may be a dataclass or a plain dict depending on
            # whether Temporal can resolve the type at deserialization time.
            if isinstance(result_obj, dict):
                result = result_obj
            else:
                result = {
                    "chunks_stored": result_obj.chunks_stored,
                    "files_processed": result_obj.files_processed,
                    "summaries_generated": result_obj.summaries_generated,
                }

        return IndexStatusResponse(
            workflow_id=workflow_id,
            status=status,
            result=result,
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """
    Semantic search over indexed code chunks.

    How it works:
    1. Embed the query using OpenAI (same model used during indexing)
    2. Ask pgvector: "find the N chunks whose embedding is closest to this query embedding"
    3. Return those chunks with their similarity scores

    "Closest" is measured by cosine similarity — a mathematical measure of how
    similar two vectors are. 1.0 = identical meaning, 0.0 = completely unrelated.
    """
    from openai import AsyncOpenAI

    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Embed the query
    response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=[req.query],
    )
    query_embedding = response.data[0].embedding  # list of 1536 floats

    # Query pgvector for similar chunks.
    # <=> is the pgvector cosine distance operator.
    # We do 1 - distance to get similarity (distance 0 = similarity 1).
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
            (str(query_embedding), req.repo_url, str(query_embedding), req.limit),
        )
        rows = await rows.fetchall()

    return SearchResponse(results=[
        SearchResult(
            file_path=row["file_path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            content=row["content"],
            similarity=round(row["similarity"], 4),
        )
        for row in rows
    ])
