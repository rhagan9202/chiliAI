"""Tests for shared runtime-checkable protocols."""

from __future__ import annotations

from shared.protocols import Configurable


class _ConfigurableExample:
    def configure(self, config: object) -> None:
        self.config = config


class _NonConfigurableExample:
    pass


def test_configurable_runtime_checkable_accepts_matching_instance() -> None:
    assert isinstance(_ConfigurableExample(), Configurable)


def test_configurable_runtime_checkable_rejects_non_matching_instance() -> None:
    assert not isinstance(_NonConfigurableExample(), Configurable)