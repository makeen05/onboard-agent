# api/workflows/index_repo.py
#
# Index Repo workflow — orchestrates the indexing pipeline.
#
# This file contains ONLY the workflow class. All activities and helpers
# live in activities/indexing.py. This separation is a Temporal best practice:
# workflow modules must not import I/O libraries (git, openai, shutil, etc.)
# because Temporal sandboxes them for deterministic replay.
#
# Pipeline steps visible in the Temporal UI timeline:
#   clone_repo -> walk_files -> clear_old_chunks -> process_batch (parallel)
#   -> generate_summaries -> save_repo

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from api.workflows.models import (
    FILES_PER_BATCH,
    GenerateSummariesInput,
    IndexRepoInput,
    IndexRepoResult,
    ProcessBatchInput,
    SaveRepoInput,
)

# Import activity references — these are just function references, not the
# actual I/O code, so they're safe inside the sandboxed workflow module.
with workflow.unsafe.imports_passed_through():
    from api.workflows.activities.indexing import (
        clone_repo,
        walk_files,
        clear_old_chunks,
        process_batch,
        generate_summaries,
        save_repo,
        delete_clone,
    )


@workflow.defn
class IndexRepoWorkflow:
    @workflow.run
    async def run(self, input: IndexRepoInput) -> IndexRepoResult:
        repo_url = input.repo_url
        retry = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))

        # Step 1: Clone
        repo_dir: str = await workflow.execute_activity(
            clone_repo, repo_url,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        try:
            # Step 2: Walk files
            file_paths: list[str] = await workflow.execute_activity(
                walk_files, repo_dir,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )

            # Step 3: Clear old data
            await workflow.execute_activity(
                clear_old_chunks, repo_url,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )

            # Step 4: Process batches in parallel
            batches = [
                file_paths[i : i + FILES_PER_BATCH]
                for i in range(0, len(file_paths), FILES_PER_BATCH)
            ]
            counts: list[int] = await asyncio.gather(*[
                workflow.execute_activity(
                    process_batch,
                    ProcessBatchInput(file_paths=batch, repo_url=repo_url, repo_dir=repo_dir),
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=retry,
                )
                for batch in batches
            ])

            # Step 5: Generate per-directory summaries
            summaries_count: int = await workflow.execute_activity(
                generate_summaries,
                GenerateSummariesInput(repo_url=repo_url, repo_dir=repo_dir, file_paths=file_paths),
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=retry,
            )

            # Step 6: Save clone path for query workflow
            await workflow.execute_activity(
                save_repo,
                SaveRepoInput(repo_url=repo_url, clone_path=repo_dir),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )

            return IndexRepoResult(
                chunks_stored=sum(counts),
                files_processed=len(file_paths),
                summaries_generated=summaries_count,
            )

        except Exception:
            await workflow.execute_activity(
                delete_clone, repo_dir,
                start_to_close_timeout=timedelta(minutes=1),
            )
            raise
