# api/db/connection.py
#
# This file manages the connection to Postgres.
#
# Rather than opening a new connection for every query (expensive — connections
# take time to establish), we use a "connection pool": a set of pre-opened
# connections that get reused. When code needs the DB, it borrows a connection
# from the pool, uses it, and returns it.
#
# psycopg is the Python library for talking to Postgres.
# psycopg_pool manages the pool of connections.

import os
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg_pool
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/onboard")

# The pool is a module-level variable — created once when the app starts,
# shared across all requests.
_pool: psycopg_pool.AsyncConnectionPool | None = None


async def init_pool() -> None:
    """
    Create the connection pool and run the schema migrations.
    Call this once when the app starts up (in FastAPI's lifespan).
    """
    global _pool
    _pool = psycopg_pool.AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=2,   # keep at least 2 connections open at all times
        max_size=10,  # never open more than 10 simultaneous connections
        open=False,   # don't connect yet — we call .open() below
    )
    await _pool.open()

    # Run schema.sql to create tables if they don't exist yet.
    # Path(__file__).parent = the directory this file is in (api/db/)
    schema = (Path(__file__).parent / "schema.sql").read_text()
    async with _pool.connection() as conn:
        await conn.execute(schema)
        await conn.commit()


async def close_pool() -> None:
    """Close all connections. Called when the app shuts down."""
    if _pool:
        await _pool.close()


async def ensure_pool() -> None:
    """
    Make sure the DB connection pool is initialised.
    Activities may run in a fresh process where init_pool() hasn't been
    called yet. This is safe to call multiple times — it's a no-op if the
    pool already exists.
    """
    global _pool
    if _pool is None:
        await init_pool()


@asynccontextmanager
async def get_conn():
    """
    Async context manager that borrows a connection from the pool.

    Usage:
        async with get_conn() as conn:
            await conn.execute("SELECT ...")

    The connection is automatically returned to the pool when the
    'async with' block exits, even if an exception is raised.
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() first.")
    async with _pool.connection() as conn:
        # dict_row makes query results come back as dicts ({column: value})
        # instead of plain tuples, which is easier to work with.
        conn.row_factory = dict_row
        yield conn
