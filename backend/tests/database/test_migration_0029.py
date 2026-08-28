"""Integration test: alert_history gains an index the alert detail read uses.

``_ALERT_GET_SQL`` and ``_ALERT_ACK_SQL`` in ``monitoring/adapters/postgres.py``
match on ``alert_id`` alone, but every existing index on ``alert_history``
leads with ``knowledge_base_id``: the PK is ``(knowledge_base_id, alert_id)``,
``ix_alert_history_entity`` leads with it, and so does
``ix_alert_history_kb_assignee``. So the alert detail read and every triage
action sequentially scan the table.
"""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


def test_alert_detail_reads_are_index_backed(database_url: str) -> None:
    """_ALERT_GET_SQL and _ALERT_ACK_SQL match on alert_id alone, but every
    index on the table leads with knowledge_base_id: the PK is
    (knowledge_base_id, alert_id), ix_alert_history_entity leads with it, and
    so does ix_alert_history_kb_assignee. So the alert detail read and every
    triage action sequentially scan alert_history.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    with provider.connection() as conn:
        rows = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'alert_history'"
        ).fetchall()

    definitions = " ".join(str(row[0]).lower() for row in rows)
    assert "(alert_id)" in definitions, (
        f"no index leads with alert_id; indexes present: {definitions}"
    )
