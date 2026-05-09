"""Tests for the SHAP-backed explainability context source.

These tests are gated on the optional `shap` and `scikit-learn` packages and
skip cleanly when either is missing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.explainability.exceptions import (
    ExplainabilityConfigurationError,
)
from analytics.explainability.models import ExplanationContext, ExplanationItem
from shared.types import Alert

shap = pytest.importorskip("shap")
sklearn = pytest.importorskip("sklearn")  # noqa: F841
np = pytest.importorskip("numpy")
linear_model = pytest.importorskip("sklearn.linear_model")

from analytics.explainability.adapters.shap_adapter import (  # noqa: E402
    ShapAlertInput,
    ShapExplainabilityContextSource,
)


def _build_alert(alert_id: str = "alert-1") -> Alert:
    return Alert(
        id=alert_id,
        entity_type="provider",
        entity_id="provider-7",
        severity="high",
        title="Outlier provider",
        reasoning="High SHAP attribution.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _train_logistic_model() -> (
    tuple[object, list[list[float]], list[str], list[list[float]]]
):
    rng = np.random.default_rng(seed=42)
    feature_names = ["claim_count", "avg_amount", "denial_rate", "tenure_days"]
    samples = 60
    feature_matrix = rng.normal(size=(samples, len(feature_names)))
    weights = np.array([2.0, -1.5, 0.5, 0.0])
    logits = feature_matrix @ weights
    labels = (logits > 0).astype(int)
    model = linear_model.LogisticRegression(random_state=42)
    model.fit(feature_matrix, labels)
    sample_features = [[0.7, -0.3, 0.4, 0.1]]
    background = feature_matrix.tolist()
    return model, sample_features, feature_names, background


def test_shap_context_source_produces_explanation_items() -> None:
    model, sample_features, feature_names, background = _train_logistic_model()
    alert = _build_alert()
    context_source = ShapExplainabilityContextSource(
        model=model,
        background=background,
        inputs=[
            ShapAlertInput(
                knowledge_base_id="kb-1",
                alert=alert,
                feature_names=feature_names,
                features=sample_features,
                subgraph_node_ids=["provider-7"],
                subgraph_edge_ids=[],
            )
        ],
    )

    context = context_source.load_context(knowledge_base_id="kb-1", alert_id="alert-1")

    assert isinstance(context, ExplanationContext)
    assert context.knowledge_base_id == "kb-1"
    assert context.alert.id == "alert-1"
    assert len(context.explanation_items) == len(feature_names)
    for item in context.explanation_items:
        assert isinstance(item, ExplanationItem)
        assert item.source_type == "shap_feature"
        assert item.source_id in feature_names
        assert 0.0 <= item.score <= 1.0
        assert item.quote.startswith("SHAP attribution for ")
        assert item.rationale.startswith("Feature ")
    assert set(context.scores.keys()) == set(feature_names)
    assert 0.0 <= context.confidence <= 1.0


def test_shap_context_source_register_input_after_construction() -> None:
    model, sample_features, feature_names, background = _train_logistic_model()
    context_source = ShapExplainabilityContextSource(
        model=model, background=background
    )
    alert = _build_alert(alert_id="alert-late")
    context_source.register_input(
        ShapAlertInput(
            knowledge_base_id="kb-2",
            alert=alert,
            feature_names=feature_names,
            features=sample_features,
        )
    )

    context = context_source.load_context(
        knowledge_base_id="kb-2", alert_id="alert-late"
    )

    assert context.alert.id == "alert-late"
    assert context.subgraph.node_ids == ["provider-7"]


def test_shap_context_source_raises_when_input_unregistered() -> None:
    model, _, _, background = _train_logistic_model()
    context_source = ShapExplainabilityContextSource(
        model=model, background=background
    )

    with pytest.raises(ValueError):
        context_source.load_context(knowledge_base_id="kb-1", alert_id="missing")


def test_shap_alert_input_validates_feature_shape() -> None:
    alert = _build_alert()

    with pytest.raises(ValueError):
        ShapAlertInput(
            knowledge_base_id="kb-1",
            alert=alert,
            feature_names=[],
            features=[[0.1]],
        )

    with pytest.raises(ValueError):
        ShapAlertInput(
            knowledge_base_id="kb-1",
            alert=alert,
            feature_names=["a"],
            features=[],
        )

    with pytest.raises(ValueError):
        ShapAlertInput(
            knowledge_base_id="kb-1",
            alert=alert,
            feature_names=["a", "b"],
            features=[[0.1]],
        )


def test_shap_context_source_raises_configuration_error_when_shap_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    original_import = importlib.import_module

    def _fake_import(name: str, package: str | None = None) -> object:
        if name == "shap":
            raise ImportError("shap not installed for this test")
        return original_import(name, package)

    monkeypatch.setattr(importlib, "import_module", _fake_import)

    model, _, _, background = _train_logistic_model()

    with pytest.raises(ExplainabilityConfigurationError):
        ShapExplainabilityContextSource(model=model, background=background)


def test_aggregate_shap_values_handles_2d_output() -> None:
    from analytics.explainability.adapters.shap_adapter import _aggregate_shap_values

    raw = np.array([[0.2, -0.4, 0.1], [-0.6, 0.3, 0.0]])
    out = _aggregate_shap_values(raw)
    assert out == pytest.approx([0.4, 0.35, 0.05])


def test_aggregate_shap_values_handles_1d_output() -> None:
    from analytics.explainability.adapters.shap_adapter import _aggregate_shap_values

    raw = np.array([-0.5, 0.5, -0.25])
    out = _aggregate_shap_values(raw)
    assert out == pytest.approx([0.5, 0.5, 0.25])


def test_aggregate_shap_values_rejects_unsupported_ndim() -> None:
    from analytics.explainability.adapters.shap_adapter import _aggregate_shap_values

    raw = np.zeros((2, 3, 4, 5))
    with pytest.raises(ExplainabilityConfigurationError):
        _aggregate_shap_values(raw)


def test_resolve_callable_target_falls_back_to_predict() -> None:
    from analytics.explainability.adapters.shap_adapter import _resolve_callable_target

    class _PredictOnlyModel:
        def predict(self, X: object) -> object:
            return X

    target = _resolve_callable_target(_PredictOnlyModel())
    assert callable(target)


def test_resolve_callable_target_raises_when_no_callable_method() -> None:
    from analytics.explainability.adapters.shap_adapter import _resolve_callable_target

    class _UncallableModel:
        predict = "not-callable"
        predict_proba = None

    with pytest.raises(ExplainabilityConfigurationError):
        _resolve_callable_target(_UncallableModel())


def test_invoke_explainer_falls_back_to_legacy_shap_values() -> None:
    from analytics.explainability.adapters.shap_adapter import _invoke_explainer

    class _LegacyExplainer:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def shap_values(self, X: object) -> object:
            self.calls.append(X)
            return np.array([[0.1, -0.2]])

    explainer = _LegacyExplainer()
    result = _invoke_explainer(explainer, [[0.1, 0.2]])
    arr = np.asarray(result, dtype=float)
    assert arr.shape == (1, 2)
    assert len(explainer.calls) == 1


def test_invoke_explainer_raises_when_neither_callable_nor_legacy() -> None:
    from analytics.explainability.adapters.shap_adapter import _invoke_explainer

    class _BrokenExplainer:
        pass

    with pytest.raises(ExplainabilityConfigurationError):
        _invoke_explainer(_BrokenExplainer(), [[0.1, 0.2]])  # type: ignore[arg-type]
