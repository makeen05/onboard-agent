# api/workflows/dummy.py
#
# This file defines our first Temporal workflow.
# It does nothing useful — it just proves Temporal is working.
#
# ── How Temporal works (the short version) ──────────────────────────────────
#
# Temporal has two concepts you need to know:
#
#   WORKFLOW  — the orchestrator. Defines the sequence of steps. Must be
#               deterministic (same inputs → same outputs, every replay).
#               You cannot do I/O (network, disk, random) directly here.
#
#   ACTIVITY  — a single unit of work. A plain Python async function.
#               Activities CAN do I/O. Temporal retries them automatically
#               if they fail. This is where file reads, API calls, etc. go.
#
# The workflow calls activities. Activities do the real work. Think of the
# workflow as a project manager and activities as individual team members.
#
# ── Why this separation? ─────────────────────────────────────────────────────
#
# Temporal makes workflows "durable" by replaying them from the beginning
# whenever the process restarts. To replay correctly, workflows must produce
# the same result every time they run. Randomness and I/O break that guarantee,
# so they're banned inside workflows. Activities are executed once, their results
# recorded — so the workflow can replay without re-executing them.

from datetime import timedelta
from temporalio import activity, workflow


# ── Activity ─────────────────────────────────────────────────────────────────
# @activity.defn registers this function with Temporal as an activity.
# It's just a normal async Python function — no magic inside.
@activity.defn
async def say_hello(name: str) -> str:
    # In real milestones, this is where we'd read files, call OpenAI, etc.
    print(f"[activity] say_hello called with: {name}")
    return f"Hello from Temporal! You asked: '{name}'"


# ── Workflow ──────────────────────────────────────────────────────────────────
# @workflow.defn registers this class as a Temporal workflow.
# The class name ("DummyWorkflow") is used to reference it when starting it.
@workflow.defn
class DummyWorkflow:

    # @workflow.run marks the method that Temporal calls when the workflow starts.
    # There must be exactly one per workflow class.
    @workflow.run
    async def run(self, question: str) -> str:
        # workflow.execute_activity schedules the activity on the task queue.
        # Temporal sends it to a worker, waits for the result, then continues here.
        #
        # start_to_close_timeout: how long the activity is allowed to run before
        # Temporal considers it failed and retries. Required — Temporal refuses
        # to schedule an activity without a timeout (prevents infinite hangs).
        result = await workflow.execute_activity(
            say_hello,
            question,
            start_to_close_timeout=timedelta(seconds=10),
        )
        return result
