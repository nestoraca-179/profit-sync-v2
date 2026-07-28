"""Validation helpers for configuration and runtime inputs."""

from __future__ import annotations

from collections import defaultdict, deque

from src.models.table_config import TableConfig

def validate_identifier(identifier: str) -> str:
    """Validate a SQL identifier and return it unchanged."""
    if not identifier:
        raise ValueError("Identifier must not be empty")
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return identifier

def validate_table_dependencies(tables: list[TableConfig]) -> None:
    """Validate dependency references and ordering graph."""
    known_tables = {table.name for table in tables}
    for table in tables:
        if table.batch_size <= 0:
            raise ValueError(f"Batch size must be positive for table {table.name}")
        for dependency in table.dependencies:
            if dependency not in known_tables:
                raise ValueError(f"Unknown dependency {dependency} for table {table.name}")
    _validate_no_cycles(tables)

def _validate_no_cycles(tables: list[TableConfig]) -> None:
    graph: dict[str, set[str]] = defaultdict(set)
    indegree: dict[str, int] = {table.name: 0 for table in tables}
    for table in tables:
        for dependency in table.dependencies:
            graph[dependency].add(table.name)
            indegree[table.name] += 1
    queue: deque[str] = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for child in graph[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(tables):
        raise ValueError("Table dependency graph contains cycles")