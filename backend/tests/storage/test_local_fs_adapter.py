"""Tests for the local filesystem object store adapter."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

import storage
import storage.adapters
from config.schema import ObjectStoreConfig
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.protocols import ObjectStore


def _config(**overrides: object) -> ObjectStoreConfig:
    data: dict[str, object] = {"backend": "local"}
    data.update(overrides)
    return ObjectStoreConfig.model_validate(data)


def _sidecar_path(base_directory: Path, key: str) -> Path:
    object_path = base_directory.joinpath(*key.split("/"))
    return object_path.with_name(f"{object_path.name}.meta.json")


def test_local_fs_object_store_satisfies_protocol(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    assert isinstance(store, ObjectStore)


def test_local_fs_object_store_round_trip(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    written = store.put_bytes(
        "documents/doc-1.txt",
        b"hello local fs",
        media_type="text/plain",
        metadata={"source": "unit-test", "attempt": 2, "nested": {"ok": True}},
    )
    stored = store.get_bytes("documents/doc-1.txt")

    assert written.key == "documents/doc-1.txt"
    assert written.size_bytes == len(b"hello local fs")
    assert written.media_type == "text/plain"
    assert written.metadata == {
        "source": "unit-test",
        "attempt": 2,
        "nested": {"ok": True},
    }
    assert stored.content == b"hello local fs"
    assert stored.media_type == "text/plain"
    assert stored.metadata == written.metadata


def test_local_fs_object_store_uses_configured_base_path(tmp_path: Path) -> None:
    configured_root = tmp_path / "configured" / "objects"
    store = LocalFsObjectStore(_config(base_path=str(configured_root)))

    store.put_bytes("documents/doc-1.txt", b"configured")

    assert store.base_directory == configured_root.resolve()
    assert (configured_root / "documents" / "doc-1.txt").read_bytes() == b"configured"


def test_local_fs_object_store_explicit_base_directory_overrides_config(
    tmp_path: Path,
) -> None:
    explicit_root = tmp_path / "explicit"
    configured_root = tmp_path / "configured"
    store = LocalFsObjectStore(
        _config(base_path=str(configured_root)),
        base_directory=explicit_root,
    )

    store.put_bytes("documents/doc-1.txt", b"explicit")

    assert store.base_directory == explicit_root.resolve()
    assert (explicit_root / "documents" / "doc-1.txt").is_file()
    assert not configured_root.exists()


def test_local_fs_object_store_defaults_to_data_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    store = LocalFsObjectStore()
    store.put_bytes("documents/doc-1.txt", b"default")

    expected_root = (tmp_path / "data" / "objects").resolve()
    assert store.base_directory == expected_root
    assert (expected_root / "documents" / "doc-1.txt").read_bytes() == b"default"


def test_local_fs_object_store_writes_metadata_sidecar_shape(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    store.put_bytes(
        "documents/doc-1.txt",
        b"metadata",
        media_type="text/plain",
        metadata={"source": "unit-test", "score": 0.75},
    )

    sidecar = json.loads(
        _sidecar_path(tmp_path, "documents/doc-1.txt").read_text(encoding="utf-8")
    )

    assert sidecar == {
        "key": "documents/doc-1.txt",
        "size_bytes": 8,
        "media_type": "text/plain",
        "metadata": {"source": "unit-test", "score": 0.75},
    }


def test_local_fs_object_store_get_missing_raises_key_error(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    with pytest.raises(KeyError, match="Stored object not found"):
        store.get_bytes("missing.txt")


def test_local_fs_object_store_missing_sidecar_surfaces_corruption(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    object_path = tmp_path / "documents" / "doc-1.txt"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"orphan")

    with pytest.raises(ValueError, match="sidecar is missing"):
        store.get_bytes("documents/doc-1.txt")


def test_local_fs_object_store_malformed_sidecar_surfaces_corruption(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    store.put_bytes("documents/doc-1.txt", b"content")
    _sidecar_path(tmp_path, "documents/doc-1.txt").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSON"):
        store.get_bytes("documents/doc-1.txt")


def test_local_fs_object_store_delete_removes_file_and_sidecar(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    store.put_bytes("documents/doc-1.txt", b"delete me")

    store.delete("documents/doc-1.txt")

    assert not (tmp_path / "documents" / "doc-1.txt").exists()
    assert not _sidecar_path(tmp_path, "documents/doc-1.txt").exists()
    assert not store.exists("documents/doc-1.txt")


def test_local_fs_object_store_delete_missing_is_no_op(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    store.put_bytes("documents/doc-1.txt", b"keep me")

    store.delete("missing.txt")

    stored = store.get_bytes("documents/doc-1.txt")
    assert stored.content == b"keep me"


def test_local_fs_object_store_exists_tracks_key_lifecycle(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    assert not store.exists("documents/doc-1.txt")

    store.put_bytes("documents/doc-1.txt", b"hello")

    assert store.exists("documents/doc-1.txt")

    store.delete("documents/doc-1.txt")

    assert not store.exists("documents/doc-1.txt")


def test_local_fs_object_store_list_keys_filters_all_and_sorted(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    store.put_bytes("documents/doc-c.txt", b"c")
    store.put_bytes("documents/doc-a.txt", b"a")
    store.put_bytes("artifacts/doc-a.json", b"{}")
    store.put_bytes("documents/nested/doc-b.txt", b"b")

    assert store.list_keys("documents/") == [
        "documents/doc-a.txt",
        "documents/doc-c.txt",
        "documents/nested/doc-b.txt",
    ]
    assert store.list_keys("") == [
        "artifacts/doc-a.json",
        "documents/doc-a.txt",
        "documents/doc-c.txt",
        "documents/nested/doc-b.txt",
    ]


def test_local_fs_object_store_list_keys_excludes_orphaned_sidecars(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    orphaned_sidecar = tmp_path / "documents" / "orphan.meta.json"
    orphaned_sidecar.parent.mkdir(parents=True)
    orphaned_sidecar.write_text("{}", encoding="utf-8")

    assert store.list_keys("") == []


@pytest.mark.parametrize(
    "key",
    [
        "",
        "   ",
        "/absolute.txt",
        "../escape.txt",
        "documents/../escape.txt",
        "documents\\doc-1.txt",
        "C:/temp/doc-1.txt",
        "//server/share/doc-1.txt",
        "documents/./doc-1.txt",
        "documents//doc-1.txt",
        "documents/doc-1.meta.json",
        "documents/doc-1.txt\x00",
    ],
)
def test_local_fs_object_store_rejects_unsafe_keys(
    tmp_path: Path,
    key: str,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    operations: list[Callable[[str], object]] = [
        lambda value: store.put_bytes(value, b"content"),
        store.get_bytes,
        store.exists,
        store.delete,
    ]
    for operation in operations:
        with pytest.raises(ValueError, match="Local filesystem"):
            operation(key)


@pytest.mark.parametrize(
    "prefix",
    [
        "   ",
        "/absolute",
        "../escape",
        "documents/../escape",
        "documents\\",
        "C:/temp",
        "//server/share",
        "documents/./",
        "documents//prefix",
        "documents/prefix\x00",
    ],
)
def test_local_fs_object_store_rejects_unsafe_prefixes(
    tmp_path: Path,
    prefix: str,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    with pytest.raises(ValueError, match="Local filesystem"):
        store.list_keys(prefix)


def test_local_fs_object_store_rejects_none_metadata_values(tmp_path: Path) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    with pytest.raises(ValueError, match="cannot be None"):
        store.put_bytes("documents/doc-1.txt", b"content", metadata={"bad": None})


def test_local_fs_object_store_rejects_nested_none_metadata_values(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    with pytest.raises(ValueError, match="cannot be None"):
        store.put_bytes(
            "documents/doc-1.txt",
            b"content",
            metadata={"nested": {"bad": None}},
        )


def test_local_fs_object_store_rejects_non_serializable_metadata(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    with pytest.raises(ValueError, match="JSON serializable"):
        store.put_bytes(
            "documents/doc-1.txt",
            b"content",
            metadata={"bad": object()},
        )


def test_local_fs_object_store_rejects_non_finite_float_metadata(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)

    with pytest.raises(ValueError, match="finite"):
        store.put_bytes(
            "documents/doc-1.txt",
            b"content",
            metadata={"bad": float("nan")},
        )


def test_local_fs_object_store_reserved_sidecar_suffix_cannot_corrupt_metadata(
    tmp_path: Path,
) -> None:
    store = LocalFsObjectStore(base_directory=tmp_path)
    store.put_bytes("documents/doc-1", b"safe", metadata={"source": "unit-test"})

    with pytest.raises(ValueError, match="reserved '.meta.json'"):
        store.put_bytes("documents/doc-1.meta.json", b"collision")

    stored = store.get_bytes("documents/doc-1")

    assert stored.content == b"safe"
    assert stored.metadata == {"source": "unit-test"}
    assert store.list_keys("") == ["documents/doc-1"]


def test_local_fs_object_store_exports_are_available() -> None:
    assert storage.LocalFsObjectStore is LocalFsObjectStore
    assert storage.adapters.LocalFsObjectStore is LocalFsObjectStore