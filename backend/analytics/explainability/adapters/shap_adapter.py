"""SHAP-backed explainability context source.

Computes per-feature SHAP attributions for a trained model and maps each
contribution to an `ExplanationItem`. Inputs are keyed by alert id so the
service can resolve feature attributions for a specific alert/context.

The `shap` package is an optional dependency. The import is performed lazily
inside the adapter so importing this module never requires `shap` at install
time. If `shap` is missing when the adapter is constructed, an
`ExplainabilityConfigurationError` is raised with installation guidance.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Protocol, cast

from analytics.explainability.exceptions import (
    ExplainabilityConfigurationError,
    ExplainabilityInsufficientEvidenceError,
)
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from shared.types import Alert

__all__ = [
    "ShapAlertInput",
    "ShapExplainabilityContextSource",
    "ShapExplainerProtocol",
    "ShapModelProtocol",
]


class ShapModelProtocol(Protocol):
    """Structural boundary for the trained model passed to SHAP."""

    def predict(self, X: Sequence[Sequence[float]]) -> object: ...


class ShapExplainerProtocol(Protocol):
    """Structural boundary for a SHAP explainer.

    Modern SHAP exposes the `shap.Explainer` instance as a callable that
    returns an `Explanation` object; older releases also expose
    `shap_values()`. The adapter accepts either shape.
    """

    def __call__(self, X: Sequence[Sequence[float]]) -> object: ...


class ShapAlertInput:
    """A bundle of inputs scoped to a single alert.

    Stored in the adapter's registry and consumed at `load_context` time to
    compute SHAP attributions. Feature names line up with feature columns and
    must be the same length as each row in `features`.
    """

    __slots__ = (
        "alert",
        "feature_names",
        "features",
        "knowledge_base_id",
        "subgraph_edge_ids",
        "subgraph_node_ids",
    )

    def __init__(
        self,
        *,
        knowledge_base_id: str,
        alert: Alert,
        feature_names: Sequence[str],
        features: Sequence[Sequence[float]],
        subgraph_node_ids: Sequence[str] | None = None,
        subgraph_edge_ids: Sequence[str] | None = None,
    ) -> None:
        if not feature_names:
            raise ValueError("ShapAlertInput requires at least one feature name.")
        if not features:
            raise ValueError("ShapAlertInput requires at least one feature row.")
        for row in features:
            if len(row) != len(feature_names):
                raise ValueError("Each feature row must match the length of feature_names.")
        self.knowledge_base_id = knowledge_base_id
        self.alert = alert
        self.feature_names: list[str] = list(feature_names)
        self.features: list[list[float]] = [list(row) for row in features]
        self.subgraph_node_ids: list[str] = list(subgraph_node_ids or [alert.entity_id])
        self.subgraph_edge_ids: list[str] = list(subgraph_edge_ids or [])


class ShapExplainabilityContextSource:
    """Build explanation contexts from SHAP feature attributions."""

    def __init__(
        self,
        *,
        model: ShapModelProtocol,
        inputs: Sequence[ShapAlertInput] | None = None,
        background: Sequence[Sequence[float]] | None = None,
    ) -> None:
        explainer_factory = _load_shap_explainer_factory()
        callable_target = _resolve_callable_target(model)
        masker = _resolve_background(background)
        if masker is None:
            self._explainer = cast(
                ShapExplainerProtocol, explainer_factory(callable_target)
            )
        else:
            self._explainer = cast(
                ShapExplainerProtocol, explainer_factory(callable_target, masker)
            )
        self._inputs: dict[tuple[str, str], ShapAlertInput] = {}
        for entry in inputs or []:
            self.register_input(entry)

    def register_input(self, entry: ShapAlertInput) -> None:
        self._inputs[(entry.knowledge_base_id, entry.alert.id)] = entry

    def load_context(self, *, knowledge_base_id: str, alert_id: str) -> ExplanationContext:
        entry = self._inputs.get((knowledge_base_id, alert_id))
        if entry is None:
            raise ValueError(
                "No SHAP input registered for "
                f"knowledge_base_id='{knowledge_base_id}' and alert_id='{alert_id}'."
            )

        raw_values = _invoke_explainer(self._explainer, entry.features)
        attributions = _aggregate_shap_values(raw_values)
        if len(attributions) != len(entry.feature_names):
            raise ExplainabilityConfigurationError(
                "SHAP attribution length does not match the configured feature count."
            )

        items = _build_items_from_attributions(entry.feature_names, attributions)
        if not items:
            raise ExplainabilityInsufficientEvidenceError(
                "SHAP attributions produced no usable explanation items."
            )

        max_abs = max(abs(value) for value in attributions)
        confidence = max_abs if 0.0 <= max_abs <= 1.0 else 1.0
        return ExplanationContext(
            knowledge_base_id=entry.knowledge_base_id,
            alert=entry.alert,
            explanation_items=items,
            subgraph=ExplanationSubgraph(
                node_ids=entry.subgraph_node_ids,
                edge_ids=entry.subgraph_edge_ids,
            ),
            confidence=confidence,
            scores={name: value for name, value in zip(entry.feature_names, attributions, strict=True)},
        )


def _resolve_callable_target(model: ShapModelProtocol) -> object:
    """Return a callable suitable for SHAP from a trained sklearn-style model.

    Modern SHAP requires either a callable that accepts a feature matrix and
    returns predictions, or a model whose `predict_proba`/`predict` method
    fits that signature. We prefer `predict_proba` when available because it
    yields smoother attributions for classifiers.
    """

    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        return predict_proba
    predict = getattr(model, "predict", None)
    if callable(predict):
        return predict
    raise ExplainabilityConfigurationError(
        "Provided model has no callable `predict` or `predict_proba` for SHAP.",
    )


def _resolve_background(
    background: Sequence[Sequence[float]] | None,
) -> object | None:
    """Convert an optional background dataset to a numpy array masker."""

    if background is None:
        return None
    try:
        numpy_module = importlib.import_module("numpy")
    except ImportError as exc:  # pragma: no cover - numpy ships with shap
        raise ExplainabilityConfigurationError(
            "numpy is required to construct a SHAP background masker."
        ) from exc
    return numpy_module.asarray(background, dtype=float)


def _invoke_explainer(
    explainer: ShapExplainerProtocol,
    features: Sequence[Sequence[float]],
) -> object:
    """Invoke a SHAP explainer using the new callable interface or legacy API."""

    try:
        numpy_module = importlib.import_module("numpy")
    except ImportError as exc:  # pragma: no cover - numpy ships with shap
        raise ExplainabilityConfigurationError(
            "numpy is required to invoke a SHAP explainer."
        ) from exc
    matrix = numpy_module.asarray(features, dtype=float)
    if callable(explainer):
        return explainer(matrix)
    legacy = getattr(explainer, "shap_values", None)
    if callable(legacy):
        return legacy(matrix)
    raise ExplainabilityConfigurationError(
        "SHAP explainer is neither callable nor exposes `shap_values`."
    )


def _load_shap_explainer_factory() -> object:
    try:
        shap_module = importlib.import_module("shap")
    except ImportError as exc:
        raise ExplainabilityConfigurationError(
            "The 'shap' package is required for ShapExplainabilityContextSource. "
            "Install with: pip install -e \".[analytics]\"",
        ) from exc
    explainer = getattr(shap_module, "Explainer", None)
    if explainer is None:
        raise ExplainabilityConfigurationError(
            "Installed 'shap' package does not expose `Explainer`; upgrade SHAP."
        )
    if not callable(explainer):
        raise ExplainabilityConfigurationError("`shap.Explainer` is not callable.")
    return explainer


def _aggregate_shap_values(raw: object) -> list[float]:
    """Collapse SHAP outputs to a per-feature attribution vector.

    SHAP returns either a 2D array (samples x features) for a single output,
    a 3D array (samples x features x classes) for multi-output explainers, or
    an `Explanation` object with `.values`. For all shapes we average absolute
    contributions across samples (and across classes when present) to produce
    one importance score per feature.
    """

    array = _coerce_to_array(raw)
    if array.ndim == 3:
        # axis 0 = samples, axis 1 = features, axis 2 = classes
        feature_importance = array.__abs__().mean(axis=(0, 2))
    elif array.ndim == 2:
        feature_importance = array.__abs__().mean(axis=0)
    elif array.ndim == 1:
        feature_importance = array.__abs__()
    else:
        raise ExplainabilityConfigurationError(
            f"Unsupported SHAP output dimensionality: ndim={array.ndim}."
        )

    return [float(value) for value in feature_importance.tolist()]


def _coerce_to_array(raw: object):  # type: ignore[no-untyped-def]
    values = getattr(raw, "values", None)
    if values is not None and not callable(values):
        raw = values
    try:
        numpy_module = importlib.import_module("numpy")
    except ImportError as exc:  # pragma: no cover - numpy ships with shap
        raise ExplainabilityConfigurationError(
            "numpy is required to interpret SHAP outputs."
        ) from exc
    return numpy_module.asarray(raw, dtype=float)


def _build_items_from_attributions(
    feature_names: Sequence[str],
    attributions: Sequence[float],
) -> list[ExplanationItem]:
    paired = list(zip(feature_names, attributions, strict=True))
    max_abs = max((abs(value) for _, value in paired), default=0.0)
    if max_abs == 0.0:
        return []

    ranked = sorted(paired, key=lambda pair: abs(pair[1]), reverse=True)
    items: list[ExplanationItem] = []
    for name, value in ranked:
        normalized = abs(value) / max_abs
        score = max(0.0, min(1.0, normalized))
        items.append(
            ExplanationItem(
                source_id=name,
                source_type="shap_feature",
                quote=f"SHAP attribution for '{name}': {value:.4f}",
                rationale=(
                    f"Feature '{name}' contributed {value:+.4f} to the model output."
                ),
                score=score,
            )
        )
    return items
