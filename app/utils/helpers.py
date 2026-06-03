from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return utcnow()
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
