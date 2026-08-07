"""Tests for the path-guarded filesystem connector source."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from connectors.exceptions import ConnectorSourceError
from connectors.sources.filesystem import FilesystemSourceAdapter


def _adapter(root: Path) -> FilesystemSourceAdapter:
    return FilesystemSourceAdapter(allowed_root=root)


def test_pages_a_csv_directory(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")

    page = _adapter(tmp_path).read_page(
        config={"path": str(tmp_path)}, cursor=None, limit=1
    )

    assert page.rows == [{"id": "1", "amount": "10"}]
    assert page.next_cursor is not None


def test_returns_a_none_cursor_at_the_end(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")

    page = _adapter(tmp_path).read_page(
        config={"path": str(tmp_path)}, cursor=None, limit=10
    )

    assert len(page.rows) == 1
    assert page.next_cursor is None


def test_resumes_from_a_cursor_without_repeating_rows(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id\n1\n2\n3\n", encoding="utf-8")
    adapter = _adapter(tmp_path)
    config = {"path": str(tmp_path)}

    first = adapter.read_page(config=config, cursor=None, limit=2)
    second = adapter.read_page(config=config, cursor=first.next_cursor, limit=2)

    assert [row["id"] for row in first.rows] == ["1", "2"]
    assert [row["id"] for row in second.rows] == ["3"]
    assert second.next_cursor is None


def test_pages_across_multiple_files_in_sorted_order(tmp_path: Path) -> None:
    """Sorted, not directory order: resumption must be deterministic."""
    (tmp_path / "b.csv").write_text("id\n3\n", encoding="utf-8")
    (tmp_path / "a.csv").write_text("id\n1\n2\n", encoding="utf-8")
    adapter = _adapter(tmp_path)
    config = {"path": str(tmp_path)}

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        page = adapter.read_page(config=config, cursor=cursor, limit=2)
        seen.extend(str(row["id"]) for row in page.rows)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == ["1", "2", "3"]


def test_rejects_a_path_outside_the_allowed_root(tmp_path: Path) -> None:
    """A connector path is operator-supplied.

    Without a root guard this reads arbitrary host files — including the
    credentials the connector is deliberately designed never to hold.
    """
    with pytest.raises(ConnectorSourceError, match="outside the allowed root"):
        _adapter(tmp_path).read_page(config={"path": "/etc"}, cursor=None, limit=1)


def test_rejects_a_traversal_path_that_climbs_out_of_the_root(tmp_path: Path) -> None:
    root = tmp_path / "imports"
    root.mkdir()
    (tmp_path / "secrets.csv").write_text("id\n1\n", encoding="utf-8")

    with pytest.raises(ConnectorSourceError, match="outside the allowed root"):
        _adapter(root).read_page(
            config={"path": str(root / ".." / "secrets.csv")}, cursor=None, limit=1
        )


def test_rejects_a_symlink_that_escapes_the_root(tmp_path: Path) -> None:
    """`Path.resolve()` follows symlinks, so the guard must run after resolving.

    A guard that checked the *literal* path would accept this: the link lives
    inside the root, and only its target is outside.
    """
    root = tmp_path / "imports"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secrets.csv").write_text("id\n1\n", encoding="utf-8")
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform guard
        pytest.skip("symlinks are not supported in this environment")

    with pytest.raises(ConnectorSourceError, match="outside the allowed root"):
        _adapter(root).read_page(config={"path": str(link)}, cursor=None, limit=1)


def test_rejects_a_config_with_no_path(tmp_path: Path) -> None:
    with pytest.raises(ConnectorSourceError, match="path"):
        _adapter(tmp_path).read_page(config={}, cursor=None, limit=1)


def test_rejects_a_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ConnectorSourceError, match="does not exist"):
        _adapter(tmp_path).read_page(
            config={"path": str(tmp_path / "nope")}, cursor=None, limit=1
        )


def test_reads_a_single_file_path(tmp_path: Path) -> None:
    target = tmp_path / "one.csv"
    target.write_text("id\n7\n", encoding="utf-8")

    page = _adapter(tmp_path).read_page(
        config={"path": str(target)}, cursor=None, limit=10
    )

    assert [row["id"] for row in page.rows] == ["7"]


def test_ignores_non_csv_files(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a feed", encoding="utf-8")

    page = _adapter(tmp_path).read_page(
        config={"path": str(tmp_path)}, cursor=None, limit=10
    )

    assert [row["id"] for row in page.rows] == ["1"]


def test_an_empty_directory_yields_no_rows_and_no_cursor(tmp_path: Path) -> None:
    page = _adapter(tmp_path).read_page(
        config={"path": str(tmp_path)}, cursor=None, limit=10
    )

    assert page.rows == []
    assert page.next_cursor is None


def test_rejects_a_cursor_naming_a_file_that_is_gone(tmp_path: Path) -> None:
    """Fail loudly rather than silently restarting the pull from the top.

    Silently resuming at row 0 of a different file would re-ingest data and
    make the run counters lie about what was pulled.
    """
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")

    with pytest.raises(ConnectorSourceError, match="cursor"):
        _adapter(tmp_path).read_page(
            config={"path": str(tmp_path)}, cursor="deleted.csv:0", limit=1
        )


def test_rejects_a_malformed_cursor(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")

    with pytest.raises(ConnectorSourceError, match="cursor"):
        _adapter(tmp_path).read_page(
            config={"path": str(tmp_path)}, cursor="garbage", limit=1
        )


def test_rejects_a_non_positive_limit(tmp_path: Path) -> None:
    with pytest.raises(ConnectorSourceError, match="limit"):
        _adapter(tmp_path).read_page(
            config={"path": str(tmp_path)}, cursor=None, limit=0
        )


def test_allowed_root_itself_is_resolved_before_comparison(tmp_path: Path) -> None:
    """A root given via a symlink must still accept paths inside it.

    Resolving only one side of the comparison makes every read fail on hosts
    where the import directory is itself a link (macOS /tmp, container mounts).
    """
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "a.csv").write_text("id\n1\n", encoding="utf-8")
    link_root = tmp_path / "link"
    try:
        link_root.symlink_to(real_root, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform guard
        pytest.skip("symlinks are not supported in this environment")

    page = FilesystemSourceAdapter(allowed_root=link_root).read_page(
        config={"path": str(link_root)}, cursor=None, limit=10
    )

    assert [row["id"] for row in page.rows] == ["1"]


def test_root_is_required_so_the_adapter_cannot_be_built_unbounded() -> None:
    """Fail closed: there is no constructor that reads the whole filesystem."""
    with pytest.raises(TypeError):
        FilesystemSourceAdapter()  # type: ignore[call-arg]


def test_rejects_a_path_that_escapes_via_an_env_style_relative_root(
    tmp_path: Path,
) -> None:
    """`os.sep`-joined relative input is resolved against cwd, not the root."""
    root = tmp_path / "imports"
    root.mkdir()

    with pytest.raises(ConnectorSourceError, match="outside the allowed root"):
        _adapter(root).read_page(
            config={"path": f"..{os.sep}etc"}, cursor=None, limit=1
        )
