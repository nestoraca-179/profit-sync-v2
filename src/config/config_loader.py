"""Configuration loading and validation utilities."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
from src.models.table_config import TableConfig
from src.utils.validators import validate_table_dependencies

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

class DatabaseSettings(BaseModel):
    """Database connection settings."""

    server: str
    database: str
    username: str
    password: str
    connection_timeout: int = 30
    pool_size: int = 5
    driver: str = "ODBC Driver 17 for SQL Server"

    @property
    def connection_string(self) -> str:
        """Build a SQL Server connection string."""
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={self.connection_timeout};"
        )


class CircuitBreakerSettings(BaseModel):
    """Circuit breaker thresholds."""

    failure_threshold: int = 5
    timeout_seconds: int = 300
    half_open_timeout_seconds: int = 60


class LoggingSettings(BaseModel):
    """Structured logging settings."""

    structured_format: bool = True
    log_rotation_days: int = 30
    max_log_size_mb: int = 100
    level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_directory: str = "logs"


class SynchronizationSettings(BaseModel):
    """Synchronization process settings."""

    batch_size: int = 500
    max_retries: int = 3
    retry_delay_seconds: int = 60
    retry_backoff_multiplier: int = 2
    circuit_breaker: CircuitBreakerSettings = Field(default_factory=CircuitBreakerSettings)
    conflict_resolution: str = "timestamp_priority"
    transactional: bool = True
    enable_metrics: bool = True
    enable_health_check: bool = True
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class ServiceSettings(BaseModel):
    """Top-level synchronizer settings."""

    name: str = "SQLSyncService"
    version: str = "1.0.0"
    run_interval_minutes: int = Field(default_factory=lambda: int(os.getenv("SYNC_INTERVAL_MINUTES", "5")))
    timezone: str = "America/Mexico_City"
    local_database: DatabaseSettings
    remote_database: DatabaseSettings
    synchronization: SynchronizationSettings = Field(default_factory=SynchronizationSettings)


class AppConfig(BaseModel):
    """Validated application configuration."""

    synchronizer: ServiceSettings
    tables: list[TableConfig]

    @property
    def logging(self) -> LoggingSettings:
        """Return the effective logging settings."""
        return self.synchronizer.synchronization.logging

    @model_validator(mode="after")
    def validate_tables(self) -> "AppConfig":
        """Validate dependency graph and batch sizes."""
        validate_table_dependencies(self.tables)
        return self


class ConfigLoader:
    """Load YAML and environment settings into validated models."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.config_dir = self.base_path / "config"

    def load(self) -> AppConfig:
        """Load application and table settings."""
        load_dotenv(self.base_path / ".env")
        config_payload = self._load_yaml(self.config_dir / "config.yaml")
        tables_payload = self._load_yaml(self.config_dir / "tables.yaml")
        merged = {
            "synchronizer": self._expand_env(config_payload.get("synchronizer", {})),
            "tables": self._build_tables(tables_payload.get("tables", [])),
        }
        return AppConfig.model_validate(merged)

    def _load_yaml(self, file_path: Path) -> dict[str, Any]:
        with file_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file {file_path} must contain a mapping")
        return data

    def _expand_env(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._expand_env(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._expand_env(item) for item in value]
        if isinstance(value, str):
            return _ENV_PATTERN.sub(lambda match: os.getenv(match.group(1), ""), value)
        return value

    def _build_tables(self, payload: list[dict[str, Any]]) -> list[TableConfig]:
        return [TableConfig.model_validate(item) for item in payload]