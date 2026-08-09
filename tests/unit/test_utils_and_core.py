from datetime import timedelta
from types import SimpleNamespace

import pytest
from src.core.conflict_resolver import ConflictResolver
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState
from src.utils.helpers import chunked, generate_sync_id, utc_now
from src.utils.retry_decorator import build_retry_decorator
from src.utils.validators import validate_table_dependencies

def test_conflict_resolver_prefers_latest_timestamp():
    resolver = ConflictResolver()
    earlier = utc_now()
    later = earlier + timedelta(seconds=1)
    local = SyncOperation(
        table_name="saDocumentoVenta",
        record_id="1",
        operation_type=OperationType.UPDATE,
        change_version=1,
        timestamp=earlier,
    )
    remote = SyncOperation(
        table_name="saDocumentoVenta",
        record_id="1",
        operation_type=OperationType.UPDATE,
        change_version=2,
        timestamp=later,
    )

    result = resolver.resolve([local], [remote])

    assert result.local_to_remote == []
    assert result.remote_to_local == [remote]
    assert result.conflicts

def test_validate_table_dependencies_rejects_cycles():
    tables = [
        TableConfig(name="A", primary_key="Id", dependencies=["B"]),
        TableConfig(name="B", primary_key="Id", dependencies=["A"]),
    ]

    with pytest.raises(ValueError):
        validate_table_dependencies(tables)

def test_chunked_and_generate_sync_id_work():
    assert list(chunked([1, 2, 3], 2)) == [[1, 2], [3]]
    assert generate_sync_id().startswith("sync-")

def test_circuit_breaker_transitions_between_states():
    breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=0, half_open_timeout_seconds=0)

    assert breaker.allow_request() is True
    breaker.record_failure("first")
    assert breaker.state == CircuitBreakerState.CLOSED
    breaker.record_failure("second")
    assert breaker.state == CircuitBreakerState.OPEN
    assert breaker.allow_request() is True
    assert breaker.state == CircuitBreakerState.HALF_OPEN
    breaker.record_success()
    assert breaker.state == CircuitBreakerState.CLOSED

def test_circuit_breaker_allows_only_one_half_open_probe():
    breaker = CircuitBreaker(failure_threshold=1, timeout_seconds=0, half_open_timeout_seconds=60)

    breaker.record_failure("initial failure")

    assert breaker.allow_request() is True
    assert breaker.state == CircuitBreakerState.HALF_OPEN
    assert breaker.allow_request() is False

    breaker.record_failure("recovery probe failed")
    assert breaker.state == CircuitBreakerState.OPEN
    assert breaker.allow_request() is True

def test_retry_decorator_retries_until_success():
    calls = {"count": 0}

    @build_retry_decorator(max_retries=3, delay_seconds=0, multiplier=1)
    def flaky():
        calls["count"] += 1
        if calls["count"] < 2:
            raise ValueError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["count"] == 2