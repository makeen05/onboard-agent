# api/workflows/models.py
#
# All shared dataclasses and constants live here.
# This file uses only stdlib imports, so it's safe to import from
# Temporal-sandboxed workflow modules.

from dataclasses import dataclass


# ── Index Repo types ─────────────────────────────────────────────────────────

@dataclass
class Chunk:
    repo_url: str
    file_path: str
    start_line: int
    end_line: int
    content: str


@dataclass
class IndexRepoInput:
    repo_url: str


@dataclass
class IndexRepoResult:
    chunks_stored: int
    files_processed: int
    summaries_generated: int


@dataclass
class ProcessBatchInput:
    file_paths: list[str]
    repo_url: str
    repo_dir: str


@dataclass
class GenerateSummariesInput:
    repo_url: str
    repo_dir: str
    file_paths: list[str]


@dataclass
class SaveRepoInput:
    repo_url: str
    clone_path: str


# ── Answer Query types ───────────────────────────────────────────────────────

@dataclass
class AnswerQueryInput:
    question: str
    repo_url: str


@dataclass
class AnswerQueryResult:
    answer: str
    agent: str
    repo_url: str


@dataclass
class RepoInfo:
    repo_url: str
    clone_path: str


@dataclass
class SpecialistInput:
    question: str
    repo_url: str
    clone_path: str
    agent: str


# ── Constants ────────────────────────────────────────────────────────────────

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".r", ".m", ".sh", ".yaml", ".yml", ".toml", ".json",
    ".sql", ".md",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage", ".pytest_cache",
}

MAX_CHUNK_LINES = 100
EMBED_BATCH_SIZE = 50
FILES_PER_BATCH = 50
