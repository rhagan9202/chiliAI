# Test discovery: run from repo root with `pytest tools/tests/ -v`
# No special pytest config needed — the tools/ package structure (with __init__.py
# files at each level) makes `tools.sample_data.build_tennessee_subset` importable
# as long as pytest is invoked from /home/rdhagan92/chiliAI (the repo root).

from __future__ import annotations

import pytest

from tools.sample_data.build_tennessee_subset import main


def test_help_runs(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--state-code" in out
    assert "--strategy" in out
