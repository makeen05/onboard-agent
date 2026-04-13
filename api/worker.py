# api/worker.py
#
# Registers all workflows and activities with Temporal.

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from api.db.connection import init_pool
from api.workflows.dummy import DummyWorkflow, say_hello
from api.workflows.index_repo import IndexRepoWorkflow
from api.workflows.answer_query import AnswerQueryWorkflow
from api.workflows.activities import (
    clone_repo,
    walk_files,
    clear_old_chunks,
    process_batch,
    generate_summaries,
    save_repo,
    delete_clone,
    ensure_repo_indexed,
    route_query,
    answer_with_specialist,
)

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "onboard-queue"


async def main() -> None:
    print(f"[worker] Connecting to Temporal at {TEMPORAL_HOST}...")
    await init_pool()

    client = await Client.connect(TEMPORAL_HOST)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            DummyWorkflow,
            IndexRepoWorkflow,
            AnswerQueryWorkflow,
        ],
        activities=[
            say_hello,
            clone_repo,
            walk_files,
            clear_old_chunks,
            process_batch,
            generate_summaries,
            save_repo,
            delete_clone,
            ensure_repo_indexed,
            route_query,
            answer_with_specialist,
        ],
    )

    print(f"[worker] Listening on task queue '{TASK_QUEUE}'...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
