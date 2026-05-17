"""Tests for shared runtime-checkable protocols."""

from __future__ import annotations

import importlib
import inspect
from typing import Protocol

import pytest

from shared.protocols import Configurable

# ---------------------------------------------------------------------------
# Existing Configurable protocol tests
# ---------------------------------------------------------------------------


class _ConfigurableExample:
    def configure(self, config: object) -> None:
        self.config = config


class _NonConfigurableExample:
    pass


def test_configurable_runtime_checkable_accepts_matching_instance() -> None:
    assert isinstance(_ConfigurableExample(), Configurable)


def test_configurable_runtime_checkable_rejects_non_matching_instance() -> None:
    assert not isinstance(_NonConfigurableExample(), Configurable)


# ---------------------------------------------------------------------------
# Regression guard: every Protocol subclass across the backend must carry
# @runtime_checkable so isinstance() checks work at module boundaries.
# Add new protocols.py modules here as they are created.
# ---------------------------------------------------------------------------

_PROTOCOL_MODULES = [
    "shared.protocols",
    "events.protocols",
    "database.protocols",
    "graph.protocols",
    "graph.adapters.protocols",
    "vectorstore.protocols",
    "vectorstore.adapters.protocols",
    "embeddings.protocols",
    "embeddings.adapters.protocols",
    "llm.protocols",
    "llm.adapters.protocols",
    "rag.protocols",
    "rag.adapters.protocols",
    "ingestion.protocols",
    "ingestion.parsers.protocols",
    "records.protocols",
    "records.adapters.protocols",
    "monitoring.protocols",
    "monitoring.adapters.protocols",
    "agent.protocols",
    "agent.adapters.protocols",
    "storage.protocols",
    "analytics.timeseries.protocols",
    "analytics.timeseries.adapters.protocols",
    "analytics.gnn.protocols",
    "analytics.gnn.adapters.protocols",
    "analytics.risk.protocols",
    "analytics.risk.adapters.protocols",
    "analytics.explainability.protocols",
    "analytics.explainability.adapters.protocols",
    "analytics.metrics.adapters.protocols",
]


def _protocol_classes_in(module_name: str) -> list[tuple[str, type]]:
    """Return all Protocol subclasses defined (not just imported) in module_name."""
    mod = importlib.import_module(module_name)
    results = []
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if (
            issubclass(obj, Protocol)  # type: ignore[arg-type]
            and obj is not Protocol
            and getattr(obj, "_is_protocol", False)
            and obj.__module__ == module_name
        ):
            results.append((f"{module_name}.{name}", obj))
    return results


@pytest.mark.parametrize("module_name", _PROTOCOL_MODULES)
def test_all_protocols_are_runtime_checkable(module_name: str) -> None:
    """Every Protocol subclass in every protocols.py must be @runtime_checkable."""
    classes = _protocol_classes_in(module_name)
    violations = [
        name
        for name, cls in classes
        if not getattr(cls, "_is_runtime_protocol", False)
    ]
    assert not violations, (
        f"Protocols missing @runtime_checkable in {module_name}: {violations}"
    )