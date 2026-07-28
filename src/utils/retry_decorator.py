"""Retry utilities backed by tenacity."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tenacity import (retry, retry_if_exception_type, stop_after_attempt, wait_exponential)

def build_retry_decorator(max_retries: int, delay_seconds: int, multiplier: int) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Build a retry decorator with exponential backoff."""

    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=multiplier, min=delay_seconds),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )