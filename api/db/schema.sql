-- schema.sql
--
-- This file defines our database tables.
-- SQL (Structured Query Language) is how you tell Postgres what structure to create.
-- "CREATE TABLE" defines a table — think of it like defining columns in a spreadsheet.
-- We run this once at startup to make sure the tables exist.

-- Enable the pgvector extension.
-- Extensions add new features to Postgres. pgvector adds the "vector" column type
-- which lets us store and search embeddings (arrays of numbers).
-- "IF NOT EXISTS" means: only install it if it isn't already — safe to run repeatedly.
CREATE EXTENSION IF NOT EXISTS vector;

-- The chunks table stores every piece of code we've indexed.
-- Each row = one chunk of code from one file in one repo.
CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    -- SERIAL = auto-incrementing integer. PRIMARY KEY = uniquely identifies each row.

    repo_url    TEXT NOT NULL,
    -- Which repo this chunk came from. TEXT = any length string.

    file_path   TEXT NOT NULL,
    -- Path to the file inside the repo, e.g. "src/auth/login.py"

    start_line  INT NOT NULL,
    end_line    INT NOT NULL,
    -- Which lines of the file this chunk covers.

    content     TEXT NOT NULL,
    -- The actual source code text of this chunk.

    embedding   vector(1536),
    -- The OpenAI embedding for this chunk — 1536 numbers.
    -- This is what pgvector searches over. NULL until we embed it.

    created_at  TIMESTAMPTZ DEFAULT NOW()
    -- When this row was inserted. TIMESTAMPTZ = timestamp with timezone.
);

-- Create an index on the embedding column for fast similarity search.
-- Without this index, a similarity search scans every row (slow for large repos).
-- "ivfflat" is a vector index type that trades a little accuracy for a lot of speed.
-- lists=100 means it divides vectors into 100 clusters — a good default for dev.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index on repo_url so we can quickly find/delete all chunks for a given repo.
CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks (repo_url);


-- ── Directory summaries ─────────────────────────────────────────────────────
-- Step 6 of the indexing pipeline: after storing chunks, we generate a short
-- natural-language summary for each directory. These help the agent quickly
-- understand the structure of a repo without reading every file.
CREATE TABLE IF NOT EXISTS directory_summaries (
    id          SERIAL PRIMARY KEY,
    repo_url    TEXT NOT NULL,
    dir_path    TEXT NOT NULL,              -- e.g. "src/auth" or "." for root
    summary     TEXT NOT NULL,              -- LLM-generated summary of this directory
    file_list   TEXT[] NOT NULL DEFAULT '{}', -- files in this directory
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS dirsummary_repo_idx ON directory_summaries (repo_url);

-- Unique constraint so re-indexing replaces old summaries cleanly.
CREATE UNIQUE INDEX IF NOT EXISTS dirsummary_repo_dir_idx
    ON directory_summaries (repo_url, dir_path);


-- ── Repos ───────────────────────────────────────────────────────────────────
-- Tracks indexed repositories and where their clone lives on disk.
-- The clone is kept after indexing so the agent's file tools (list_files,
-- search_code, read_file) can browse the actual source code without
-- re-cloning on every query.
CREATE TABLE IF NOT EXISTS repos (
    id          SERIAL PRIMARY KEY,
    repo_url    TEXT NOT NULL UNIQUE,        -- e.g. "https://github.com/some/repo"
    clone_path  TEXT NOT NULL,               -- absolute path to the cloned directory
    indexed_at  TIMESTAMPTZ DEFAULT NOW()
);
