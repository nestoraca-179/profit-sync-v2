"""Local SQL Server connector."""

from __future__ import annotations

from src.config.config_loader import DatabaseSettings
from src.connectors.base import SQLServerConnector

class LocalSQLConnector(SQLServerConnector):
    """Connector for the local SQL Server instance."""

    def __init__(self, settings: DatabaseSettings) -> None:
        super().__init__(settings=settings, source_name="local")