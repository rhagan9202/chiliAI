"""Tests for storage.models — StoredObject and StoredObjectWriteResult."""

from __future__ import annotations

from storage.models import StoredObject, StoredObjectWriteResult


class TestStoredObjectWriteResult:
    def test_round_trip(self) -> None:
        result = StoredObjectWriteResult(
            key="docs/test.txt",
            size_bytes=42,
            media_type="text/plain",
            metadata={"author": "test"},
        )
        assert result.key == "docs/test.txt"
        assert result.size_bytes == 42
        assert result.media_type == "text/plain"
        assert result.metadata == {"author": "test"}

    def test_defaults(self) -> None:
        result = StoredObjectWriteResult(key="k", size_bytes=0)
        assert result.media_type is None
        assert result.metadata == {}

    def test_serialization(self) -> None:
        result = StoredObjectWriteResult(key="k", size_bytes=10)
        data = result.model_dump()
        restored = StoredObjectWriteResult.model_validate(data)
        assert restored == result


class TestStoredObject:
    def test_round_trip(self) -> None:
        obj = StoredObject(
            key="docs/test.txt",
            content=b"hello world",
            size_bytes=11,
            media_type="text/plain",
        )
        assert obj.key == "docs/test.txt"
        assert obj.content == b"hello world"
        assert obj.size_bytes == 11

    def test_defaults(self) -> None:
        obj = StoredObject(key="k", content=b"", size_bytes=0)
        assert obj.media_type is None
        assert obj.metadata == {}

    def test_serialization(self) -> None:
        obj = StoredObject(key="k", content=b"abc", size_bytes=3)
        data = obj.model_dump()
        restored = StoredObject.model_validate(data)
        assert restored == obj
