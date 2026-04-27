"""Linear weighted-sum risk scoring strategy."""

from __future__ import annotations

from analytics.risk.models import RiskFactor, RiskSignal


class LinearScoringStrategy:
    """Score signals via a normalized linear weighted-sum."""

    def score(self, signals: list[RiskSignal]) -> list[RiskFactor]:
        total_weight = sum(signal.weight for signal in signals)
        return [
            RiskFactor(
                factor_name=signal.signal_name,
                raw_value=signal.value,
                weight=signal.weight,
                contribution=min(1.0, (signal.value * signal.weight) / total_weight),
                rationale=signal.rationale,
            )
            for signal in signals
        ]


__all__ = ["LinearScoringStrategy"]
