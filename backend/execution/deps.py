"""Dependencies executor handlers receive.

Deliberately narrow. ``WorkerDependencies`` has 45 fields and ``handle_event``
takes ~40 hand-forwarded keyword arguments; the point of this seam is that
executors do not extend that. A handler needing something not listed here adds
one explicit field rather than being handed the whole worker container.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from analytics.risk.service import RiskService
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from config.schema import DomainConfig, RecordsConfig
from connectors.repository import ConnectorRepositoryProtocol
from connectors.sources.protocols import ConnectorSourceAdapter
from events.protocols import EventBus
from graph.adapters.protocols import GraphRepository
from records.protocols import RecordsServiceProtocol

__all__ = ["ExecutionDeps"]


@dataclass(frozen=True, slots=True)
class ExecutionDeps:
    """The subset of worker dependencies executors are allowed to use.

    Every field is optional so a partially-configured worker still starts; each
    handler is responsible for returning 0 when a dependency it needs is absent
    rather than raising, so a missing optional adapter degrades to "no work
    done" instead of dead-lettering every event.
    """

    event_bus: EventBus | None
    risk_service: RiskService | None
    score_run_repository: ScoreRunRepositoryProtocol | None
    graph_repository: GraphRepository | None
    domain_config: DomainConfig | None
    connector_repository: ConnectorRepositoryProtocol | None = None
    records_service: RecordsServiceProtocol | None = None
    # The feed definitions the records service validates against. The connector
    # executor needs the feed itself, not just the service, so it can partition
    # rows it knows the service would reject outright.
    records_config: RecordsConfig | None = None
    # Keyed by ConnectorSourceType. The connector executor refuses a source
    # type with no adapter rather than falling back to one, so an unimplemented
    # source fails its run loudly instead of pulling from the wrong place.
    source_adapters: Mapping[str, ConnectorSourceAdapter] | None = None
