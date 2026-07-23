"""Feature attribution over the linear risk composite, via SHAP.

Computes per-feature SHAP attributions directly from an
`ExplanationContext`'s `scores` mapping against the additive model implied by
`analytics.risk.adapters.linear_strategy.LinearScoringStrategy` (a clipped sum
of per-feature contributions), with no pre-trained model or per-alert feature
registration required. Contrast with `ShapExplainabilityContextSource` in
`shap_adapter.py`, which explains an arbitrary externally trained model and
builds an `ExplanationContext` rather than consuming one.

`shap` and `numpy` are optional dependencies (`chili-backend[analytics]`).
Both are imported lazily — only when `ShapRiskAttributor.attribute` runs — so
importing this module never requires either package to be installed. Per
`FeatureAttributorProtocol`, the attributor never raises: a missing
dependency, an empty feature set, or any explainer failure degrades to an
empty attribution list with a WARNING log, since the attribution pipeline
step is best-effort.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from types import ModuleType
from typing import Protocol, cast

from analytics.explainability.models import ExplanationContext
from shared.types import FeatureAttribution

__all__ = ["NoopFeatureAttributor", "ShapRiskAttributor"]

logger = logging.getLogger(__name__)

ShapNumpyLoader = Callable[[], tuple[ModuleType, ModuleType]]


class _ShapExplanationProtocol(Protocol):
    """Structural contract for the object returned by calling a SHAP explainer."""

    values: Sequence[Sequence[float]]


class _ShapExplainerProtocol(Protocol):
    """Structural contract for a constructed SHAP explainer instance."""

    def __call__(self, matrix: object) -> _ShapExplanationProtocol: ...


class _ShapModuleProtocol(Protocol):
    """Structural contract for the parts of the `shap` module this adapter uses."""

    def Explainer(
        self, model: Callable[[object], object], background: object
    ) -> _ShapExplainerProtocol: ...


class _SupportsAxisSum(Protocol):
    """Structural contract for the feature matrix passed into `predict`."""

    def sum(self, *, axis: int) -> object: ...


class NoopFeatureAttributor:
    """Attributor that never produces feature attributions.

    Used when the domain/analytics configuration has attribution disabled or
    unconfigured; a safe, always-available default.
    """

    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]:
        return []


class ShapRiskAttributor:
    """Attribute the linear risk composite's score across its scored features.

    The composite is modeled as ``predict(X) = min(1.0, X.sum(axis=1))`` — the
    `LinearScoringStrategy` clipped weighted-sum, evaluated here purely in
    contribution space (each `context.scores` entry, excluding `"overall"`, is
    already one feature's contribution). SHAP explains that model against a
    single all-zero background row, so each attribution is the feature's
    marginal contribution to the clipped sum.
    """

    def __init__(self, *, loader: ShapNumpyLoader | None = None) -> None:
        self._loader = loader if loader is not None else _load_shap_and_numpy

    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]:
        features = sorted(
            (key, value) for key, value in context.scores.items() if key != "overall"
        )
        if not features:
            logger.warning(
                "ShapRiskAttributor: no non-overall scores for kb=%s alert=%s; "
                "returning no attributions.",
                context.knowledge_base_id,
                context.alert.id,
            )
            return []

        try:
            shap_module, numpy_module = self._loader()
        except Exception:
            logger.warning(
                "ShapRiskAttributor: shap/numpy unavailable for kb=%s alert=%s; "
                "returning no attributions.",
                context.knowledge_base_id,
                context.alert.id,
                exc_info=True,
            )
            return []

        try:
            return _compute_attributions(features, shap_module, numpy_module)
        except Exception:
            logger.warning(
                "ShapRiskAttributor: SHAP explainer failed for kb=%s alert=%s; "
                "returning no attributions.",
                context.knowledge_base_id,
                context.alert.id,
                exc_info=True,
            )
            return []


def _compute_attributions(
    features: Sequence[tuple[str, float]],
    shap_module: ModuleType,
    numpy_module: ModuleType,
) -> list[FeatureAttribution]:
    """Run the SHAP explainer over the linear composite and shape the output."""

    typed_shap_module = cast(_ShapModuleProtocol, shap_module)
    keys = [key for key, _ in features]
    values = [value for _, value in features]

    def predict(matrix: object) -> object:
        summed = cast(_SupportsAxisSum, matrix).sum(axis=1)
        return numpy_module.minimum(1.0, summed)

    x_row = numpy_module.array([values])
    background = numpy_module.zeros((1, len(values)))
    explainer = typed_shap_module.Explainer(predict, background)
    explanation = explainer(x_row)
    row = explanation.values[0]

    attributions = [
        FeatureAttribution(
            feature_name=key,
            contribution=float(contribution),
            rationale=f"SHAP attribution of the linear risk composite for {key}.",
        )
        for key, contribution in zip(keys, row, strict=True)
    ]
    attributions.sort(key=lambda attribution: abs(attribution.contribution), reverse=True)
    return attributions


def _load_shap_and_numpy() -> tuple[ModuleType, ModuleType]:
    """Import `shap` and `numpy` lazily; raise if either optional extra is missing."""

    import importlib

    shap_module = importlib.import_module("shap")
    numpy_module = importlib.import_module("numpy")
    return shap_module, numpy_module
