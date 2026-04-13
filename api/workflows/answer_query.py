# api/workflows/answer_query.py
#
# Answer Query workflow — the core user-facing pipeline.
#
# Temporal UI timeline:
#   ensure_repo_indexed -> route_query -> answer_with_specialist

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from api.workflows.models import (
    AnswerQueryInput,
    AnswerQueryResult,
    RepoInfo,
    SpecialistInput,
)

with workflow.unsafe.imports_passed_through():
    from api.workflows.activities.querying import (
        ensure_repo_indexed,
        route_query,
        answer_with_specialist,
    )


@workflow.defn
class AnswerQueryWorkflow:
    @workflow.run
    async def run(self, input: AnswerQueryInput) -> AnswerQueryResult:
        retry = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))

        # Step 1: Ensure the repo is indexed and get the clone path
        repo_info: RepoInfo = await workflow.execute_activity(
            ensure_repo_indexed, input.repo_url,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        # Step 2: Route the question to a specialist
        agent: str = await workflow.execute_activity(
            route_query, input.question,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        # Step 3: Run the specialist agent
        answer: str = await workflow.execute_activity(
            answer_with_specialist,
            SpecialistInput(
                question=input.question,
                repo_url=input.repo_url,
                clone_path=repo_info.clone_path,
                agent=agent,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        return AnswerQueryResult(
            answer=answer,
            agent=agent,
            repo_url=input.repo_url,
        )
