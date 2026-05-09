"""Local filesystem object store adapter."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import cast

from config.schema import ObjectStoreConfig
from storage.models import StoredObject, StoredObjectWriteResult

__all__ = ["LocalFsObjectStore"]

_DEFAULT_BASE_DIRECTORY = Path("./data/objects/")
_SIDECAR_SUFFIX = ".meta.json"


class LocalFsObjectStore:
    """Persist object bytes and sidecar metadata on the local filesystem."""

    def __init__(
        self,
        config: ObjectStoreConfig | None = None,
        *,
        base_directory: Path | str | None = None,
    ) -> None:
        """Create a local filesystem store rooted at a safe base directory."""

        configured_base_path = _normalize_optional_string(
            config.base_path if config is not None else None
        )
        selected_base_directory = (
            Path(base_directory)
            if base_directory is not None
            else Path(configured_base_path)
            if configured_base_path is not None
            else _DEFAULT_BASE_DIRECTORY
        )
        self._base_directory = selected_base_directory.expanduser().resolve()
        self._base_directory.mkdir(parents=True, exist_ok=True)

    @property
    def base_directory(self) -> Path:
        """Return the resolved physical root used for object files."""

        return self._base_directory

    def put_bytes(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredObjectWriteResult:
        """Store bytes and JSON sidecar metadata under a logical key."""

        object_path = self._object_path(key)
        object_metadata = _normalize_metadata(metadata)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(content)

        sidecar_payload: dict[str, object] = {
            "key": key,
            "size_bytes": len(content),
            "media_type": media_type,
            "metadata": object_metadata,
        }
        self._sidecar_path(object_path).write_text(
            json.dumps(sidecar_payload, sort_keys=True),
            encoding="utf-8",
        )

        return StoredObjectWriteResult(
            key=key,
            size_bytes=len(content),
            media_type=media_type,
            metadata=object_metadata,
        )

    def get_bytes(self, key: str) -> StoredObject:
        """Retrieve bytes and metadata for a key, raising KeyError if absent."""

        object_path = self._object_path(key)
        if not object_path.is_file():
            raise KeyError(f"Stored object not found: {key}")

        content = object_path.read_bytes()
        sidecar = self._read_sidecar(object_path, expected_key=key)
        if sidecar.size_bytes != len(content):
            raise ValueError(
                f"Metadata sidecar for '{key}' has size {sidecar.size_bytes}, "
                f"but object has size {len(content)}."
            )

        return StoredObject(
            key=key,
            content=content,
            size_bytes=sidecar.size_bytes,
            media_type=sidecar.media_type,
            metadata=sidecar.metadata,
        )

    def delete(self, key: str) -> None:
        """Delete an object and sidecar; missing objects are a no-op."""

        object_path = self._object_path(key)
        sidecar_path = self._sidecar_path(object_path)

        if object_path.exists():
            object_path.unlink()
        if sidecar_path.exists():
            sidecar_path.unlink()

        self._cleanup_empty_parents(object_path.parent)

    def exists(self, key: str) -> bool:
        """Return whether an object file exists for the provided key."""

        return self._object_path(key).is_file()

    def list_keys(self, prefix: str) -> list[str]:
        """Return sorted logical keys whose POSIX key starts with prefix."""

        logical_prefix = _validate_logical_prefix(prefix)
        keys: list[str] = []
        for file_path in self._base_directory.rglob("*"):
            if not file_path.is_file() or self._is_sidecar_file(file_path):
                continue
            logical_key = file_path.relative_to(self._base_directory).as_posix()
            if logical_key.startswith(logical_prefix):
                keys.append(logical_key)
        return sorted(keys)

    def _object_path(self, key: str) -> Path:
        logical_key = _validate_logical_key(key)
        raw_path = self._base_directory.joinpath(*PurePosixPath(logical_key).parts)
        resolved_path = raw_path.resolve(strict=False)
        if not resolved_path.is_relative_to(self._base_directory):
            raise ValueError(
                "Local filesystem object key resolves outside the configured "
                "base directory."
            )
        return resolved_path

    def _read_sidecar(self, object_path: Path, *, expected_key: str) -> _Sidecar:
        sidecar_path = self._sidecar_path(object_path)
        if not sidecar_path.is_file():
            raise ValueError(f"Metadata sidecar is missing for '{expected_key}'.")

        try:
            raw_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Metadata sidecar for '{expected_key}' is malformed JSON."
            ) from exc

        if not isinstance(raw_payload, Mapping):
            raise ValueError(
                f"Metadata sidecar for '{expected_key}' must be a JSON object."
            )

        payload = cast(Mapping[str, object], raw_payload)
        sidecar_key = payload.get("key")
        if sidecar_key != expected_key:
            raise ValueError(
                f"Metadata sidecar key mismatch for '{expected_key}'."
            )

        size_bytes = payload.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError(
                f"Metadata sidecar for '{expected_key}' has invalid size_bytes."
            )

        media_type = payload.get("media_type")
        if media_type is not None and not isinstance(media_type, str):
            raise ValueError(
                f"Metadata sidecar for '{expected_key}' has invalid media_type."
            )

        raw_metadata = payload.get("metadata")
        if not isinstance(raw_metadata, Mapping):
            raise ValueError(
                f"Metadata sidecar for '{expected_key}' has invalid metadata."
            )

        metadata = _normalize_metadata(dict(cast(Mapping[str, object], raw_metadata)))
        return _Sidecar(
            size_bytes=size_bytes,
            media_type=media_type,
            metadata=metadata,
        )

    def _is_sidecar_file(self, file_path: Path) -> bool:
        return file_path.name.endswith(_SIDECAR_SUFFIX)

    def _cleanup_empty_parents(self, start_directory: Path) -> None:
        directory = start_directory
        while directory != self._base_directory and directory.is_relative_to(
            self._base_directory
        ):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent

    @staticmethod
    def _sidecar_path(object_path: Path) -> Path:
        return object_path.with_name(f"{object_path.name}{_SIDECAR_SUFFIX}")


class _Sidecar:
    """Validated metadata sidecar payload."""

    def __init__(
        self,
        *,
        size_bytes: int,
        media_type: str | None,
        metadata: dict[str, object],
    ) -> None:
        self.size_bytes = size_bytes
        self.media_type = media_type
        self.metadata = metadata


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _validate_logical_key(key: str) -> str:
    """Validate logical object keys before mapping to filesystem paths."""

    _validate_logical_path(value=key, allow_empty=False, label="object key")
    if key.endswith(_SIDECAR_SUFFIX):
        raise ValueError(
            "Local filesystem object key cannot end with the reserved "
            f"'{_SIDECAR_SUFFIX}' sidecar suffix."
        )
    return key


def _validate_logical_prefix(prefix: str) -> str:
    """Validate logical list prefixes while allowing the empty prefix."""

    _validate_logical_path(value=prefix, allow_empty=True, label="list prefix")
    return prefix


def _validate_logical_path(*, value: str, allow_empty: bool, label: str) -> None:
    if value == "" and allow_empty:
        return
    if value.strip() == "":
        raise ValueError(f"Local filesystem {label} cannot be empty or whitespace.")
    if "\x00" in value:
        raise ValueError(f"Local filesystem {label} cannot contain null bytes.")
    if "\\" in value:
        raise ValueError(
            f"Local filesystem {label} must use POSIX '/' separators, not backslashes."
        )
    if _has_windows_drive(value):
        raise ValueError(f"Local filesystem {label} cannot be a Windows path.")

    logical_path = PurePosixPath(value)
    if logical_path.is_absolute() or value.startswith("//"):
        raise ValueError(f"Local filesystem {label} must be a relative POSIX path.")

    segments = value.split("/")
    if any(segment == ".." for segment in segments):
        raise ValueError(
            f"Local filesystem {label} cannot contain '..' path segments."
        )
    empty_segment_indexes = [
        index for index, segment in enumerate(segments) if segment == ""
    ]
    has_unsafe_empty_segment = any(
        index != len(segments) - 1 for index in empty_segment_indexes
    )
    if (allow_empty and has_unsafe_empty_segment) or (
        not allow_empty and empty_segment_indexes
    ):
        raise ValueError(
            f"Local filesystem {label} cannot contain empty path segments."
        )
    if any(segment == "." for segment in segments):
        raise ValueError(
            f"Local filesystem {label} cannot contain '.' path segments."
        )


def _has_windows_drive(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"


def _normalize_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    if metadata is None:
        return {}

    normalized: dict[str, object] = {}
    for key, value in metadata.items():
        normalized[key] = _normalize_json_value(value, path=f"metadata.{key}")

    try:
        json.dumps(normalized, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Local filesystem object metadata must be JSON serializable."
        ) from exc
    return normalized


def _normalize_json_value(value: object, *, path: str) -> object:
    if value is None:
        raise ValueError(
            "Local filesystem object metadata value for "
            f"'{path}' cannot be None."
        )
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"Local filesystem object metadata value for '{path}' must be finite."
            )
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        sequence = cast(Sequence[object], value)
        return [
            _normalize_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(sequence)
        ]
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        normalized: dict[str, object] = {}
        for raw_key, raw_value in mapping.items():
            if not isinstance(raw_key, str):
                raise ValueError(
                    f"Local filesystem object metadata key at '{path}' must be a string."
                )
            normalized[raw_key] = _normalize_json_value(
                raw_value,
                path=f"{path}.{raw_key}",
            )
        return normalized
    raise ValueError("Local filesystem object metadata must be JSON serializable.")