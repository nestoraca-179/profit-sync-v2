"""Custom exceptions for the synchronizer service."""

from __future__ import annotations

from enum import Enum

class ErrorCategory(str, Enum):
    """Standard error categories for structured logs and metrics."""

    LOCAL_DATABASE_UNAVAILABLE = "LOCAL_DATABASE_UNAVAILABLE"
    REMOTE_DATABASE_UNAVAILABLE = "REMOTE_DATABASE_UNAVAILABLE"
    LOCAL_SERVER_DOWN = "LOCAL_SERVER_DOWN"
    REMOTE_SERVER_DOWN = "REMOTE_SERVER_DOWN"
    NETWORK_CONNECTION_FAILED = "NETWORK_CONNECTION_FAILED"
    READ_OPERATION_FAILED = "READ_OPERATION_FAILED"
    WRITE_OPERATION_FAILED = "WRITE_OPERATION_FAILED"
    OPERATION_TIMEOUT = "OPERATION_TIMEOUT"
    DATA_CONFLICT = "DATA_CONFLICT_DETECTED"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CHANGE_TRACKING_ERROR = "CHANGE_TRACKING_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

class SynchronizerError(Exception):
    """Base exception for all synchronizer failures."""

    def __init__(self, message: str, category: ErrorCategory) -> None:
        super().__init__(message)
        self.category = category

class ConfigurationError(SynchronizerError):
    """Raised when configuration is invalid or missing."""

class ConnectionUnavailableError(SynchronizerError):
    """Raised when a database connection cannot be established."""

class ChangeDetectionError(SynchronizerError):
    """Raised when SQL Server change tracking cannot be read."""

class ProcessingError(SynchronizerError):
    """Raised when a synchronization batch cannot be applied."""

class CircuitBreakerOpenError(SynchronizerError):
    """Raised when operations are blocked by the circuit breaker."""