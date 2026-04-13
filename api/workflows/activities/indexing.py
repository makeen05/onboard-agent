# api/workflows/activities/indexing.py
#
# All activities for the Index Repo workflow.
# Activities CAN do I/O (git, openai, filesystem, database) — they're not
# sandboxed like workflows.

import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from temporalio import activity

from api.db.connection import ensure_pool, get_conn
from api.workflows.models import (
    Chunk,
    GenerateSummariesInput,
    ProcessBatchInput,
    SaveRepoInput,
    CODE_EXTENSIONS,
    SKIP_DIRS,
    MAX_CHUNK_LINES,
    EMBED_BATCH_SIZE,
)


# ── Activities ───────────────────────────────────────────────────────────────

@activity.defn
async def clone_repo(repo_url: str) -> str:
    """Clone the repo to a temp dir. Returns the path."""
    import git

    tmp_dir = tempfile.mkdtemp(prefix="onboard_")
    activity.logger.info(f"Cloning {repo_url} into {tmp_dir}")
    git.Repo.clone_from(repo_url, tmp_dir, depth=1)
    return tmp_dir


@activity.defn
async def walk_files(repo_dir: str) -> list[str]:
    """Find all code files in the repo, skipping non-code dirs/files."""
    code_files = []
    root = Path(repo_dir)

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in CODE_EXTENSIONS:
            code_files.append(str(path))

    activity.logger.info(f"Found {len(code_files)} code files")
    return code_files


@activity.defn
async def clear_old_chunks(repo_url: str) -> None:
    """Delete existing chunks and summaries for this repo before re-indexing."""
    await ensure_pool()

    async with get_conn() as conn:
        await conn.execute("DELETE FROM chunks WHERE repo_url = %s", (repo_url,))
        await conn.execute("DELETE FROM directory_summaries WHERE repo_url = %s", (repo_url,))
        await conn.commit()

    activity.logger.info(f"Cleared old data for {repo_url}")


@activity.defn
async def process_batch(input: ProcessBatchInput) -> int:
    """
    Chunk files, embed them, and store in Postgres — all in one activity.

    Why combined? Passing megabytes of chunk data back through the workflow
    hits Temporal's task size limits. Keeping the heavy data inside a single
    activity means the workflow only sees a count (int) come back.
    """
    from openai import AsyncOpenAI

    await ensure_pool()

    # Step 1: Chunk all files in this batch
    all_chunks: list[Chunk] = []
    for file_path in input.file_paths:
        all_chunks.extend(_chunk_single_file(file_path, input.repo_url, input.repo_dir))

    if not all_chunks:
        return 0

    activity.logger.info(f"Chunked {len(input.file_paths)} files -> {len(all_chunks)} chunks")

    # Step 2: Embed all chunks
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    embeddings: list[list[float]] = []

    for i in range(0, len(all_chunks), EMBED_BATCH_SIZE):
        batch = all_chunks[i : i + EMBED_BATCH_SIZE]
        texts = [c.content for c in batch]
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        for emb_obj in response.data:
            embeddings.append(emb_obj.embedding)

    activity.logger.info(f"Embedded {len(embeddings)} chunks")

    # Step 3: Store in Postgres
    async with get_conn() as conn:
        cur = conn.cursor()
        for chunk, embedding in zip(all_chunks, embeddings):
            await cur.execute(
                """
                INSERT INTO chunks (repo_url, file_path, start_line, end_line, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    chunk.repo_url,
                    chunk.file_path,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.content,
                    str(embedding),
                ),
            )
        await conn.commit()

    activity.logger.info(f"Stored {len(all_chunks)} chunks")
    return len(all_chunks)


@activity.defn
async def generate_summaries(input: GenerateSummariesInput) -> int:
    """Generate a short LLM summary for each directory in the repo."""
    from openai import AsyncOpenAI

    await ensure_pool()

    # Group files by directory
    dir_files: dict[str, list[str]] = defaultdict(list)
    for fp in input.file_paths:
        rel = os.path.relpath(fp, input.repo_dir)
        parent = str(Path(rel).parent)
        if parent == ".":
            parent = "."
        dir_files[parent].append(Path(rel).name)

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    count = 0

    for dir_path, files in dir_files.items():
        # Read a sample of file contents for context
        samples = []
        for fname in files[:10]:
            full_path = Path(input.repo_dir) / dir_path / fname
            try:
                text = full_path.read_text(encoding="utf-8", errors="ignore")
                sample = "\n".join(text.splitlines()[:50])
                samples.append(f"--- {fname} ---\n{sample}")
            except Exception:
                continue

        file_listing = ", ".join(files)
        sample_text = "\n\n".join(samples) if samples else "(no readable files)"

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You summarise source code directories. Be concise (2-3 sentences). "
                               "Focus on what the directory's code DOES, not how it's structured.",
                },
                {
                    "role": "user",
                    "content": f"Directory: {dir_path}/\nFiles: {file_listing}\n\n"
                               f"Sample contents:\n{sample_text}",
                },
            ],
            max_tokens=200,
        )
        summary = response.choices[0].message.content or ""

        async with get_conn() as conn:
            await conn.execute(
                """
                INSERT INTO directory_summaries (repo_url, dir_path, summary, file_list)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (repo_url, dir_path)
                DO UPDATE SET summary = EXCLUDED.summary,
                              file_list = EXCLUDED.file_list,
                              created_at = NOW()
                """,
                (input.repo_url, dir_path, summary, files),
            )
            await conn.commit()
        count += 1

    activity.logger.info(f"Generated {count} directory summaries")
    return count


@activity.defn
async def save_repo(input: SaveRepoInput) -> None:
    """
    Record the clone path in the repos table so the Answer Query workflow
    can find it later. If re-indexing, the old clone is cleaned up.
    """
    await ensure_pool()

    async with get_conn() as conn:
        row = await conn.execute(
            "SELECT clone_path FROM repos WHERE repo_url = %s",
            (input.repo_url,),
        )
        existing = await row.fetchone()
        if existing and existing["clone_path"] != input.clone_path:
            shutil.rmtree(existing["clone_path"], ignore_errors=True)
            activity.logger.info(f"Removed old clone at {existing['clone_path']}")

        await conn.execute(
            """
            INSERT INTO repos (repo_url, clone_path, indexed_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (repo_url)
            DO UPDATE SET clone_path = EXCLUDED.clone_path, indexed_at = NOW()
            """,
            (input.repo_url, input.clone_path),
        )
        await conn.commit()

    activity.logger.info(f"Saved clone path for {input.repo_url}")


@activity.defn
async def delete_clone(repo_dir: str) -> None:
    """Clean up a cloned repo from disk. Used when indexing fails."""
    shutil.rmtree(repo_dir, ignore_errors=True)
    activity.logger.info(f"Cleaned up {repo_dir}")


# ── Chunking helpers (called inside process_batch) ───────────────────────────

def _chunk_single_file(file_path: str, repo_url: str, repo_dir: str) -> list[Chunk]:
    """Split one file into chunks — tree-sitter first, fixed-size fallback."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    lines = source.splitlines()
    if not lines:
        return []

    rel_path = str(path.relative_to(repo_dir))
    chunks = _chunk_with_treesitter(source, lines, rel_path, repo_url, path.suffix)
    if not chunks:
        chunks = _chunk_fixed(lines, rel_path, repo_url)

    return chunks


def _chunk_with_treesitter(
    source: str, lines: list[str], rel_path: str, repo_url: str, suffix: str
) -> list[Chunk]:
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser

        lang_map = {".py": tspython}
        lang_module = lang_map.get(suffix)
        if lang_module is None:
            return []

        language = Language(lang_module.language())
        parser = Parser(language)
        tree = parser.parse(source.encode())

        chunks = []
        for node in tree.root_node.children:
            if node.type not in ("function_definition", "class_definition",
                                  "decorated_definition"):
                continue

            start = node.start_point[0]
            end = node.end_point[0]
            content = "\n".join(lines[start : end + 1])

            if (end - start + 1) > MAX_CHUNK_LINES:
                sub_lines = lines[start : end + 1]
                chunks.extend(_chunk_fixed(sub_lines, rel_path, repo_url, offset=start))
            else:
                chunks.append(Chunk(
                    repo_url=repo_url,
                    file_path=rel_path,
                    start_line=start + 1,
                    end_line=end + 1,
                    content=content,
                ))

        return chunks

    except Exception as e:
        activity.logger.warning(f"tree-sitter failed for {rel_path}: {e}")
        return []


def _chunk_fixed(
    lines: list[str], rel_path: str, repo_url: str, offset: int = 0
) -> list[Chunk]:
    chunks = []
    for i in range(0, len(lines), MAX_CHUNK_LINES):
        window = lines[i : i + MAX_CHUNK_LINES]
        chunks.append(Chunk(
            repo_url=repo_url,
            file_path=rel_path,
            start_line=offset + i + 1,
            end_line=offset + i + len(window),
            content="\n".join(window),
        ))
    return chunks
