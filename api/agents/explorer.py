# api/agents/explorer.py
#
# Explorer agent — answers "where is X?" questions by searching a cloned repo.
#
# This is the first real agent (M3). It uses the OpenAI Agents SDK with three
# file-based tools that operate on a local clone of the repo:
#
#   list_files  — list files in a directory, optionally filtered by glob pattern
#   search_code — search for text/regex across files (like grep)
#   read_file   — read the contents of a specific file (with optional line range)
#
# The agent does NOT use vector search (that's M4/RAG). It works entirely by
# navigating the filesystem, which is exactly how a human would explore an
# unfamiliar codebase — list directories, search for keywords, read files.

import fnmatch
import os
import re
from pathlib import Path

from agents import Agent, Runner, function_tool, RunContextWrapper

from api.workflows.models import SKIP_DIRS


class ExplorerContext:
    def __init__(self, repo_dir: str, repo_url: str):
        self.repo_dir = repo_dir
        self.repo_url = repo_url


@function_tool
def list_files(
    ctx: RunContextWrapper[ExplorerContext],
    path: str = ".",
    glob: str = "*",
) -> str:
    """List files in a directory within the repository.

    Args:
        path: Directory path relative to repo root. Defaults to root.
        glob: Glob pattern to filter files, e.g. "*.py" or "*.ts". Defaults to all files.
    """
    target = Path(ctx.context.repo_dir) / path
    if not target.exists():
        return f"Directory not found: {path}"
    if not target.is_dir():
        return f"Not a directory: {path}"

    results = []
    for item in sorted(target.iterdir()):
        rel = str(item.relative_to(ctx.context.repo_dir))
        # Skip hidden/noisy directories
        if item.is_dir() and item.name in SKIP_DIRS:
            continue
        if item.is_file() and not fnmatch.fnmatch(item.name, glob):
            continue
        suffix = "/" if item.is_dir() else ""
        results.append(f"{rel}{suffix}")

    if not results:
        return f"No files matching '{glob}' in {path}/"

    return "\n".join(results)


@function_tool
def search_code(
    ctx: RunContextWrapper[ExplorerContext],
    query: str,
    file_type: str = "",
) -> str:
    """Search for text or a regex pattern across all code files in the repository.

    Args:
        query: Text or regex pattern to search for.
        file_type: Optional file extension filter, e.g. ".py" or ".ts". Empty means all files.
    """
    repo = Path(ctx.context.repo_dir)
    matches = []
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        # If the query isn't valid regex, treat it as a literal string
        pattern = re.compile(re.escape(query), re.IGNORECASE)

    for root_dir, dirs, files in os.walk(repo):
        # Skip noisy directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in files:
            if file_type and not fname.endswith(file_type):
                continue
            fpath = Path(root_dir) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for line_num, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    rel = str(fpath.relative_to(repo))
                    matches.append(f"{rel}:{line_num}: {line.strip()}")

            # Cap results to prevent huge outputs
            if len(matches) >= 50:
                matches.append("... (results truncated at 50 matches)")
                return "\n".join(matches)

    if not matches:
        return f"No matches found for '{query}'"

    return "\n".join(matches)


@function_tool
def read_file(
    ctx: RunContextWrapper[ExplorerContext],
    path: str,
    start: int = 0,
    end: int = 0,
) -> str:
    """Read the contents of a file in the repository.

    Args:
        path: File path relative to repo root, e.g. "src/main.py".
        start: Start line number (1-based). 0 means from the beginning.
        end: End line number (1-based, inclusive). 0 means to the end of the file.
    """
    target = Path(ctx.context.repo_dir) / path
    if not target.exists():
        return f"File not found: {path}"
    if not target.is_file():
        return f"Not a file: {path}"

    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Error reading {path}: {e}"

    lines = text.splitlines()

    # Apply line range if specified
    if start > 0 or end > 0:
        s = max(start - 1, 0)  # convert to 0-based
        e = end if end > 0 else len(lines)
        lines = lines[s:e]
        # Add line numbers for context
        numbered = [f"{s + i + 1}: {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)

    # For full files, cap at 200 lines to avoid overwhelming the agent
    if len(lines) > 200:
        numbered = [f"{i + 1}: {line}" for i, line in enumerate(lines[:200])]
        numbered.append(f"\n... (file has {len(lines)} lines total, showing first 200)")
        return "\n".join(numbered)

    numbered = [f"{i + 1}: {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)


# ── Agent definition ─────────────────────────────────────────────────────────

EXPLORER_INSTRUCTIONS = """\
You are the Explorer agent — a specialist at finding things in codebases.

Your job is to answer "where is X?" questions. You have three tools:
- list_files: Browse directories to understand repo structure
- search_code: Search for text/patterns across all files (like grep)
- read_file: Read specific files to understand their contents

Strategy:
1. Start by listing the root directory to understand the project layout.
2. Use search_code to find relevant keywords, function names, or patterns.
3. Read the most relevant files to confirm your findings.
4. Always cite specific file paths and line numbers in your answer.

Be thorough but efficient. If a search returns too many results, narrow it
with a file_type filter. If you're not sure where something is, explore
the directory tree systematically.

Your answer MUST include specific file references like "src/auth/login.py:42".
"""

explorer_agent = Agent(
    name="Explorer",
    instructions=EXPLORER_INSTRUCTIONS,
    tools=[list_files, search_code, read_file],
    model="gpt-4o-mini",
)


async def run_explorer(question: str, repo_dir: str, repo_url: str) -> str:
    """
    Run the Explorer agent against a cloned repo.
    Returns the agent's final answer as a string.
    """
    context = ExplorerContext(repo_dir=repo_dir, repo_url=repo_url)
    result = await Runner.run(
        explorer_agent,
        input=question,
        context=context,
    )
    return result.final_output
