"""Circuit breaker implementation used to guard failing dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

from src.utils.helpers import utc_now

class CircuitBreakerState(str, Enum):
    """Possible circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

@dataclass(slots=True)
class CircuitBreaker:
    """Simple in-memory circuit breaker."""

    failure_threshold: int
    timeout_seconds: int
    half_open_timeout_seconds: int
    failure_count: int = 0
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    opened_at: object | None = None
    half_opened_at: object | None = None
    half_open_request_in_flight: bool = False
    last_failure_message: str | None = None

    def allow_request(self) -> bool:
        """Return whether a new request may proceed."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        now = utc_now()
        if self.state == CircuitBreakerState.OPEN and self.opened_at is not None:
            if now >= self.opened_at + timedelta(seconds=self.timeout_seconds):
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_opened_at = now
                self.half_open_request_in_flight = True
                return True
            return False
        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.half_opened_at is not None and now >= self.half_opened_at + timedelta(seconds=self.half_open_timeout_seconds):
                self.state = CircuitBreakerState.OPEN
                self.opened_at = now
                self.half_opened_at = None
                self.half_open_request_in_flight = False
            return False
        return False

    def record_success(self) -> None:
        """Close the breaker after a successful operation."""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.opened_at = None
        self.half_opened_at = None
        self.half_open_request_in_flight = False
        self.last_failure_message = None

    def record_failure(self, message: str) -> None:
        """Register a failure and open the breaker if needed."""
        self.failure_count += 1
        self.last_failure_message = message
        if self.state == CircuitBreakerState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.opened_at = utc_now()
            self.half_opened_at = None
            self.half_open_request_in_flight = False

    @property
    def snapshot(self) -> dict[str, str | int | None]:
        """Return serializable state details."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_message": self.last_failure_message,
        }