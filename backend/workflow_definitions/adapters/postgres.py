"""Postgres-backed workflow definition repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionPage,
    WorkflowDefinitionStatus,
    WorkflowStepDefinition,
)

__all__ = ["PostgresWorkflowDefinitionRepository"]

_COLUMNS = (
    "snapshot_id, knowledge_base_id, domain_name, definition_id, version, status, "
    "name, description, allowed_capability_refs, steps, created_by, approved_by, "
    "created_at, updated_at, approved_at, retired_at"
)

_INSERT = f"""
    INSERT INTO workflow_definition_snapshots (
        {_COLUMNS}
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (knowledge_base_id, definition_id, version) DO NOTHING
"""

_UPDATE = """
    UPDATE workflow_definition_snapshots
    SET domain_name = %s,
        status = %s,
        name = %s,
        description = %s,
        allowed_capability_refs = %s::jsonb,
        steps = %s::jsonb,
        created_by = %s,
        approved_by = %s,
        created_at = %s,
        updated_at = %s,
        approved_at = %s,
        retired_at = %s
    WHERE knowledge_base_id = %s AND definition_id = %s AND version = %s
"""

_SELECT_BY_KEY = f"""
    SELECT {_COLUMNS}
    FROM workflow_definition_snapshots
    WHERE knowledge_base_id = %s AND definition_id = %s AND version = %s
"""


class PostgresWorkflowDefinitionRepository:
    """Store versioned workflow definition snapshots in Postgres."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        with self._provider.connection() as conn:
            try:
                cursor = conn.execute(_INSERT, _insert_params(definition))
                if cursor.rowcount != 1:
                    conn.rollback()
                    raise ValueError(
                        "Workflow definition snapshot already exists."
                    )
                row = conn.execute(
                    _SELECT_BY_KEY,
                    (
                        definition.knowledge_base_id,
                        definition.definition_id,
                        definition.version,
                    ),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ValueError(
                        "Workflow definition snapshot was not stored."
                    )
                conn.commit()
                return _row_to_definition(row)
            except Exception:
                conn.rollback()
                raise

    def update_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        with self._provider.connection() as conn:
            try:
                cursor = conn.execute(_UPDATE, _update_params(definition))
                if cursor.rowcount != 1:
                    conn.rollback()
                    raise KeyError(
                        (
                            definition.knowledge_base_id,
                            definition.definition_id,
                            definition.version,
                        )
                    )
                row = conn.execute(
                    _SELECT_BY_KEY,
                    (
                        definition.knowledge_base_id,
                        definition.definition_id,
                        definition.version,
                    ),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise KeyError(
                        (
                            definition.knowledge_base_id,
                            definition.definition_id,
                            definition.version,
                        )
                    )
                conn.commit()
                return _row_to_definition(row)
            except Exception:
                conn.rollback()
                raise

    def get_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                _SELECT_BY_KEY,
                (knowledge_base_id, definition_id, version),
            ).fetchone()
        return None if row is None else _row_to_definition(row)

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage:
        if limit < 1:
            raise ValueError("limit must be positive.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")

        where_clause = ""
        params: tuple[object, ...] = ()
        if knowledge_base_id is not None:
            where_clause = "WHERE knowledge_base_id = %s"
            params = (knowledge_base_id,)

        with self._provider.connection() as conn:
            total_row = conn.execute(
                f"""
                SELECT count(*)
                FROM workflow_definition_snapshots
                {where_clause}
                """,
                params,
            ).fetchone()
            total_items = cast(int, total_row[0]) if total_row is not None else 0
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS}
                FROM workflow_definition_snapshots
                {where_clause}
                ORDER BY definition_id ASC, version ASC, knowledge_base_id ASC
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            ).fetchall()
        return WorkflowDefinitionPage(
            items=[_row_to_definition(row) for row in rows],
            total_items=total_items,
            limit=limit,
            offset=offset,
        )


def _insert_params(definition: WorkflowDefinition) -> tuple[object, ...]:
    return (
        definition.snapshot_id,
        definition.knowledge_base_id,
        definition.domain_name,
        definition.definition_id,
        definition.version,
        definition.status,
        definition.name,
        definition.description,
        json.dumps(definition.allowed_capability_refs),
        _steps_json(definition.steps),
        definition.created_by,
        definition.approved_by,
        definition.created_at,
        definition.updated_at,
        definition.approved_at,
        definition.retired_at,
    )


def _update_params(definition: WorkflowDefinition) -> tuple[object, ...]:
    return (
        definition.domain_name,
        definition.status,
        definition.name,
        definition.description,
        json.dumps(definition.allowed_capability_refs),
        _steps_json(definition.steps),
        definition.created_by,
        definition.approved_by,
        definition.created_at,
        definition.updated_at,
        definition.approved_at,
        definition.retired_at,
        definition.knowledge_base_id,
        definition.definition_id,
        definition.version,
    )


def _row_to_definition(row: Row) -> WorkflowDefinition:
    return WorkflowDefinition(
        knowledge_base_id=cast(str, row[1]),
        domain_name=cast(str | None, row[2]),
        definition_id=cast(str, row[3]),
        version=cast(str, row[4]),
        status=cast(WorkflowDefinitionStatus, row[5]),
        name=cast(str, row[6]),
        description=cast(str | None, row[7]),
        allowed_capability_refs=_decode_string_list(row[8]),
        steps=_decode_steps(row[9]),
        created_by=cast(str, row[10]),
        approved_by=cast(str | None, row[11]),
        created_at=cast(datetime, row[12]),
        updated_at=cast(datetime, row[13]),
        approved_at=cast(datetime | None, row[14]),
        retired_at=cast(datetime | None, row[15]),
    )


def _steps_json(steps: list[WorkflowStepDefinition]) -> str:
    return json.dumps([step.model_dump(mode="json") for step in steps])


def _decode_string_list(value: object) -> list[str]:
    raw: object = (
        json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    )
    if not isinstance(raw, list):
        raise ValueError("workflow_definition_snapshots JSON value is not a list.")
    return [str(item) for item in cast(list[object], raw)]


def _decode_steps(value: object) -> list[WorkflowStepDefinition]:
    raw: object = (
        json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    )
    if not isinstance(raw, list):
        raise ValueError("workflow_definition_snapshots.steps is not a list.")
    return [
        WorkflowStepDefinition.model_validate(item)
        for item in cast(list[object], raw)
    ]
