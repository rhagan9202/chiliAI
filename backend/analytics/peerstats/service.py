"""Compute cross-sectional peer-group z-scores and persist them as signals."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import fmean, pstdev

from analytics.peerstats.adapters.protocols import (
    DerivedRiskSignalWriterProtocol,
    RecordColumnSourceProtocol,
)
from analytics.peerstats.aggregation import z_to_signal
from analytics.peerstats.exceptions import PeerStatsSourceError
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from analytics.peerstats.service_models import (
    PeerStatsComputeRequest,
    PeerStatsComputeResponse,
)

__all__ = ["PeerStatsService", "create_peerstats_service"]


class PeerStatsService:
    """Orchestrate aggregate → peer mean/std → z → signal persistence."""

    def __init__(
        self,
        column_source: RecordColumnSourceProtocol,
        *,
        writer: DerivedRiskSignalWriterProtocol,
    ) -> None:
        self._column_source = column_source
        self._writer = writer

    def compute(
        self, request: PeerStatsComputeRequest
    ) -> PeerStatsComputeResponse:
        """Compute z-scores for all entities in the request and persist signals."""
        spec = request.spec
        try:
            aggregates = self._column_source.load_interval_aggregates(
                knowledge_base_id=request.knowledge_base_id,
                spec=spec,
                interval_starts=request.interval_starts,
            )
        except PeerStatsSourceError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise PeerStatsSourceError("Failed to load interval aggregates.") from exc

        groups: dict[tuple[str, datetime], list[PeerAggregate]] = defaultdict(list)
        for aggregate in aggregates:
            groups[(aggregate.peer_group_key, aggregate.interval_start)].append(
                aggregate
            )

        signals: list[DerivedRiskSignal] = []
        affected: set[str] = set()
        for (group_key, interval_start), members in groups.items():
            if len(members) < spec.min_peers:
                continue
            values = [member.aggregate_value for member in members]
            mean = fmean(values)
            std = pstdev(values)
            for member in members:
                z_score = 0.0 if std == 0.0 else (member.aggregate_value - mean) / std
                signal_value = z_to_signal(
                    z_score, direction=spec.direction, z_cap=spec.z_cap
                )
                rationale = spec.rationale_template.format(
                    name=spec.name, z=z_score, peer_group=group_key
                )
                signals.append(
                    DerivedRiskSignal(
                        knowledge_base_id=request.knowledge_base_id,
                        entity_id=member.entity_id,
                        entity_type=member.entity_type,
                        metric_name=spec.name,
                        interval_start=interval_start,
                        peer_group_key=group_key,
                        aggregate_value=member.aggregate_value,
                        peer_mean=mean,
                        peer_std=std,
                        z_score=z_score,
                        signal_value=signal_value,
                        weight=spec.weight,
                        rationale=rationale,
                        correlation_id=request.correlation_id,
                    )
                )
                affected.add(member.entity_id)

        written = self._writer.write_signals(signals)
        return PeerStatsComputeResponse(
            metric_name=spec.name,
            signals_written=written,
            affected_entity_ids=sorted(affected),
        )


def create_peerstats_service(
    column_source: RecordColumnSourceProtocol,
    *,
    writer: DerivedRiskSignalWriterProtocol,
) -> PeerStatsService:
    """Construct a :class:`PeerStatsService`."""

    return PeerStatsService(column_source, writer=writer)
