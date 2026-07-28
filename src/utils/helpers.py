"""Generic helper utilities used across the project."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import islice
from typing import Iterable, Iterator, TypeVar
from uuid import uuid4

T = TypeVar("T")

def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)

def generate_sync_id() -> str:
    """Generate a human-readable synchronization identifier."""
    return f"sync-{utc_now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"

def chunked(items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield items in lists of a fixed maximum size."""
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk