from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qs, urlparse

import asyncpg

ResumeSourceType = Literal["file", "text", "hh_url"]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_resumes (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    resume_text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


@dataclass(frozen=True)
class ResumeRecord:
    user_id: int
    resume_text: str
    source_type: ResumeSourceType
    source_label: str
    username: str | None = None
    full_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def text(self) -> str:
        return self.resume_text


def normalize_database_url(database_url: str) -> str:
    url = database_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def resolve_ssl_mode(database_url: str) -> str | bool:
    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    sslmode = (query.get("sslmode") or [""])[0].lower()
    if sslmode == "disable":
        return False
    return "require"


class PostgresResumeStorage:
    """Supabase PostgreSQL storage for user resumes keyed by Telegram user_id."""

    def __init__(self, database_url: str) -> None:
        self._database_url = normalize_database_url(database_url)
        self._ssl = resolve_ssl_mode(self._database_url)
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._database_url,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
            command_timeout=30,
            ssl=self._ssl,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresResumeStorage is not initialized. Call await storage.init() first.")
        return self._pool

    async def has_resume(self, user_id: int) -> bool:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM user_resumes WHERE user_id = $1 LIMIT 1",
                user_id,
            )
            return row is not None

    async def get(self, user_id: int) -> ResumeRecord | None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, username, full_name, resume_text,
                       source_type, source_label, created_at, updated_at
                FROM user_resumes
                WHERE user_id = $1
                """,
                user_id,
            )
            if row is None:
                return None
            return ResumeRecord(
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                resume_text=row["resume_text"],
                source_type=row["source_type"],
                source_label=row["source_label"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def save(
        self,
        user_id: int,
        text: str,
        source_type: ResumeSourceType,
        source_label: str,
        username: str | None = None,
        full_name: str | None = None,
    ) -> ResumeRecord:
        pool = self._require_pool()
        clean_text = text.strip()
        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_resumes (
                    user_id, username, full_name, resume_text,
                    source_type, source_label, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    resume_text = EXCLUDED.resume_text,
                    source_type = EXCLUDED.source_type,
                    source_label = EXCLUDED.source_label,
                    updated_at = EXCLUDED.updated_at
                RETURNING user_id, username, full_name, resume_text,
                          source_type, source_label, created_at, updated_at
                """,
                user_id,
                username,
                full_name,
                clean_text,
                source_type,
                source_label,
                now,
            )
            assert row is not None
            return ResumeRecord(
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                resume_text=row["resume_text"],
                source_type=row["source_type"],
                source_label=row["source_label"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def delete(self, user_id: int) -> bool:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            status = await conn.execute(
                "DELETE FROM user_resumes WHERE user_id = $1",
                user_id,
            )
            return status.endswith("1")

    async def count(self) -> int:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT COUNT(*) FROM user_resumes")
            return int(val or 0)
