# api/worker.py
#
# The worker is a long-running Python process that connects to Temporal and
# says: "I'm ready to execute workflows and activities on the 'onboard-queue'."
#
# ── How the flow works ───────────────────────────────────────────────────────
#
#   1. FastAPI receives POST /query
#   2. FastAPI tells Temporal: "start DummyWorkflow on task queue 'onboard-queue'"
#   3. Temporal records the request in its database
#   4. THIS worker is polling "onboard-queue" — it picks up the task
#   5. Worker executes DummyWorkflow.run() locally
#   6. Workflow calls execute_activity(say_hello, ...)
#   7. Temporal schedules say_hello back on the task queue
#   8. Worker picks it up, runs say_hello(), returns the result to Temporal
#   9. Temporal records the result, marks the workflow complete
#  10. FastAPI gets the result back and returns it in the HTTP response
#
# The worker never opens a port. It only reaches OUT to Temporal (long-polling).
# This is why workers can be behind firewalls — Temporal always initiates.

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from api.workflows.dummy import DummyWorkflow, say_hello

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")

# The task queue name is how Temporal knows which worker should handle which
# workflow. When FastAPI starts a workflow on "onboard-queue", Temporal routes
# it to any worker that registered itself on "onboard-queue".
TASK_QUEUE = "onboard-queue"


async def main() -> None:
    print(f"[worker] Connecting to Temporal at {TEMPORAL_HOST}...")

    # Client.connect opens a gRPC connection to the Temporal server.
    # gRPC is a fast binary protocol — like HTTP but for internal service calls.
    client = await Client.connect(TEMPORAL_HOST)

    # Worker registers itself with two lists:
    #   workflows= : the workflow classes it can execute
    #   activities=: the activity functions it can execute
    # If you add a new workflow/activity, you MUST add it to these lists
    # or Temporal will queue the task forever waiting for a capable worker.
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DummyWorkflow],
        activities=[say_hello],
    )

    print(f"[worker] Listening on task queue '{TASK_QUEUE}'...")
    await worker.run()  # blocks forever, polling for tasks


if __name__ == "__main__":
    asyncio.run(main())
