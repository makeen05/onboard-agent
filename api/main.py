# api/main.py
#
# This is the FastAPI application — the HTTP layer of our system.
# It receives requests from the outside world and kicks off Temporal workflows.
#
# FastAPI is a Python web framework. You define "routes" (URL + method pairs)
# as Python functions. FastAPI automatically:
#   - Parses JSON request bodies into Python objects (using Pydantic)
#   - Validates types (if the field should be a string and you send a number, it errors)
#   - Generates interactive API docs at http://localhost:8000/docs (try it!)
#   - Serializes Python objects back to JSON for responses
#
# ── Request lifecycle for POST /query ────────────────────────────────────────
#
#   Browser/curl → FastAPI (this file) → Temporal → Worker → back to FastAPI → response
#
# FastAPI is async (uses Python's asyncio), which means it can handle many
# requests at once without blocking. While it's waiting for Temporal to finish
# a workflow, it can serve other requests.

import os
import uuid

from fastapi import FastAPI
from pydantic import BaseModel
from temporalio.client import Client

from api.workflows.dummy import DummyWorkflow

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "onboard-queue"

# FastAPI() creates the application object. title= shows up in the auto-generated docs.
app = FastAPI(title="Onboard Agent API", version="0.1.0")


# ── Request / Response models ─────────────────────────────────────────────────
# Pydantic BaseModel classes define the shape of JSON bodies.
# FastAPI reads the type annotations and validates automatically.

class QueryRequest(BaseModel):
    question: str   # the user's natural language question about a codebase


class QueryResponse(BaseModel):
    workflow_id: str   # unique ID for this run — use it to look up in Temporal UI
    result: str        # the answer


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    # Health check endpoint. Useful for Docker health checks and monitoring later.
    # Returns immediately without touching Temporal or Postgres.
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """
    Accepts a natural language question, runs it through a Temporal workflow,
    and returns the answer.

    In M1 this just echoes back a greeting — the real logic comes in M3+.
    """
    # Connect to Temporal. In production you'd reuse a single connection
    # (via FastAPI lifespan), but for M1 creating one per request is fine.
    client = await Client.connect(TEMPORAL_HOST)

    # Give each workflow run a unique ID. This lets you:
    #   - Look it up in the Temporal UI
    #   - Deduplicate if the same request is submitted twice (Temporal prevents
    #     two workflows with the same ID from running simultaneously)
    workflow_id = f"query-{uuid.uuid4()}"

    # execute_workflow does three things:
    #   1. Tells Temporal to start DummyWorkflow with input=req.question
    #   2. Waits (async) until the workflow completes
    #   3. Returns the workflow's return value
    #
    # If the worker crashes mid-execution, Temporal retries it automatically.
    # The HTTP request here will just wait longer — no data is lost.
    result: str = await client.execute_workflow(
        DummyWorkflow.run,
        req.question,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return QueryResponse(workflow_id=workflow_id, result=result)
