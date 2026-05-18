"""Tests for structured logging configuration (E10-S08)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
import structlog

import shared.logging as logging_module
from shared.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    get_logger,
)


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def test_importing_shared_logging_does_not_import_structlog() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import shared.logging; print('structlog' in sys.modules)",
        ],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    # Force reconfiguration each test by resetting the module flag.
    logging_module._configured = False  # pyright: ignore[reportPrivateUsage]
    yield
    structlog.reset_defaults()
    clear_correlation_id()
    logging_module._configured = False  # pyright: ignore[reportPrivateUsage]


def _last_log_line(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    combined = (captured.err + captured.out).strip()
    lines = [line for line in combined.splitlines() if line.strip()]
    assert lines, "Expected at least one log line"
    return lines[-1]


class TestJsonOutputStructure:
    def test_json_log_has_expected_keys(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(log_format="json", level=logging.INFO)
        logger = get_logger("chili.test.logging")
        logger.info("hello", knowledge_base_id="kb-1")
        line = _last_log_line(capsys)
        payload = cast(dict[str, object], json.loads(line))
        assert payload["event"] == "hello"
        assert payload["level"] == "info"
        assert payload["knowledge_base_id"] == "kb-1"
        assert "timestamp" in payload

    def test_console_format_does_not_emit_json(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(log_format="console", level=logging.INFO)
        logger = get_logger("chili.test.logging.console")
        logger.info("readable", foo="bar")
        line = _last_log_line(capsys)
        # JSON renderer would start with `{`; console renderer does not.
        assert not line.startswith("{")
        assert "readable" in line


class TestCorrelationIdPropagation:
    def test_bound_correlation_id_appears_in_log(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(log_format="json", level=logging.INFO)
        logger = get_logger("chili.test.correlation")
        bind_correlation_id("req-42")
        logger.info("event-with-corr")
        line = _last_log_line(capsys)
        payload = cast(dict[str, object], json.loads(line))
        assert payload["correlation_id"] == "req-42"

    def test_clear_correlation_id_removes_field(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(log_format="json", level=logging.INFO)
        logger = get_logger("chili.test.clear")
        bind_correlation_id("req-99")
        clear_correlation_id()
        logger.info("after-clear")
        line = _last_log_line(capsys)
        payload = cast(dict[str, object], json.loads(line))
        assert "correlation_id" not in payload

    def test_configure_logging_is_idempotent(self) -> None:
        configure_logging(log_format="json")
        # Second call must be a no-op (no exception, no reset).
        configure_logging(log_format="console")
        assert logging_module._configured is True  # pyright: ignore[reportPrivateUsage]

    def test_log_level_can_come_from_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        configure_logging(log_format="json")

        assert logging.getLogger().level == logging.WARNING
