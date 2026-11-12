from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

ResumeSourceType = Literal["file", "text", "hh_url"]


@dataclass(frozen=True)
class ResumeRecord:
    text: str
    source_type: ResumeSourceType
    source_label: str
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryResumeStorage:
    """Thread/async-safe in-memory storage for user resumes keyed by Telegram user_id."""

    def __init__(self) -> None:
        self._resumes: dict[int, ResumeRecord] = {}
        self._lock = asyncio.Lock()

    async def has_resume(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._resumes

    async def get(self, user_id: int) -> ResumeRecord | None:
        async with self._lock:
            return self._resumes.get(user_id)

    async def save(
        self,
        user_id: int,
        text: str,
        source_type: ResumeSourceType,
        source_label: str,
    ) -> ResumeRecord:
        record = ResumeRecord(
            text=text.strip(),
            source_type=source_type,
            source_label=source_label,
        )
        async with self._lock:
            self._resumes[user_id] = record
        return record

    async def delete(self, user_id: int) -> bool:
        async with self._lock:
            return self._resumes.pop(user_id, None) is not None

    async def count(self) -> int:
        async with self._lock:
            return len(self._resumes)
