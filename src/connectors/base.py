"""Database connector abstractions and SQL Server base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

try:
    import pyodbc
except ImportError:  # pragma: no cover
    pyodbc = None

from src.config.config_loader import DatabaseSettings
from src.core.exceptions import ConnectionUnavailableError, ErrorCategory
from src.utils.validators import validate_identifier

class AbstractConnector(ABC):
    """Abstract base class for database connectors."""

    @abstractmethod
    def connect(self) -> None:
        """Establish the database connection."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""

    @abstractmethod
    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return result rows."""

    @abstractmethod
    def execute_non_query(self, query: str, params: dict[str, Any] | None = None) -> int:
        """Execute a non-query statement and return affected rows."""

    @contextmanager
    @abstractmethod
    def transaction(self) -> Iterator[None]:
        """Context manager for transactional execution."""
        yield

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify that the database connection is healthy."""

class SQLServerConnector(AbstractConnector):
    """Shared pyodbc-based SQL Server connector implementation."""

    def __init__(self, settings: DatabaseSettings, source_name: str) -> None:
        self.settings = settings
        self.source_name = source_name
        self._connection: Any | None = None

    def connect(self) -> None:
        if pyodbc is None:
            raise ConnectionUnavailableError(
                "pyodbc no esta instalado",
                ErrorCategory.LOCAL_DATABASE_UNAVAILABLE,
            )
        if self._connection is not None:
            return
        try:
            self._connection = pyodbc.connect(self.settings.connection_string, autocommit=False)
        except Exception as exc:  # pragma: no cover
            category = (
                ErrorCategory.LOCAL_DATABASE_UNAVAILABLE
                if self.source_name == "local"
                else ErrorCategory.REMOTE_DATABASE_UNAVAILABLE
            )
            raise ConnectionUnavailableError(str(exc), category) from exc

    def disconnect(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        connection = self._require_connection()
        cursor = connection.cursor()
        cursor.execute(query, self._ordered_values(params))
        columns = [column[0] for column in cursor.description] if cursor.description else []
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def execute_non_query(self, query: str, params: dict[str, Any] | None = None) -> int:
        connection = self._require_connection()
        cursor = connection.cursor()
        cursor.execute(query, self._ordered_values(params))
        return cursor.rowcount if cursor.rowcount >= 0 else 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        connection = self._require_connection()
        try:
            yield
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def test_connection(self) -> bool:
        try:
            self.connect()
            self.execute_query("SELECT 1 AS status")
            return True
        except Exception:
            return False

    def get_row_by_primary_key(self, table_name: str, primary_key: str, record_id: str) -> dict[str, Any] | None:
        safe_table = validate_identifier(table_name)
        safe_pk = validate_identifier(primary_key)
        rows = self.execute_query(
            f"SELECT * FROM {safe_table} WHERE {safe_pk} = ?",
            {"record_id": record_id},
        )
        return rows[0] if rows else None

    def _require_connection(self) -> Any:
        if self._connection is None:
            self.connect()
        return self._connection

    def _ordered_values(self, params: dict[str, Any] | None) -> list[Any]:
        if not params:
            return []
        return list(params.values())