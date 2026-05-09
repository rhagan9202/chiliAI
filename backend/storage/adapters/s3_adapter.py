"""S3-compatible object store adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import importlib
import json
import os
from types import ModuleType
from typing import Protocol, cast

from config.schema import ObjectStoreConfig
from storage.models import StoredObject, StoredObjectWriteResult

__all__ = ["S3ObjectStore"]


class ReadableBodyProtocol(Protocol):
    """Readable response body returned by an S3 get_object call."""

    def read(self) -> bytes: ...


class S3ClientProtocol(Protocol):
    """Narrow structural boundary for the boto3 S3 client."""

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        **kwargs: object,
    ) -> object: ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def delete_object(self, *, Bucket: str, Key: str) -> object: ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def list_objects_v2(self, **kwargs: object) -> Mapping[str, object]: ...


class S3ClientFactoryProtocol(Protocol):
    """Factory boundary used to create S3 clients lazily and in tests."""

    def __call__(
        self,
        *,
        endpoint_url: str | None = None,
        credentials: AwsCredentials | None = None,
    ) -> S3ClientProtocol: ...


@dataclass(frozen=True)
class AwsCredentials:
    """Credentials loaded from the configured environment variable."""

    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str | None = None


class S3ObjectStore:
    """Persist raw object bytes in an S3-compatible bucket."""

    def __init__(
        self,
        config: ObjectStoreConfig,
        *,
        client: S3ClientProtocol | None = None,
        client_factory: S3ClientFactoryProtocol | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        """Create an adapter from object-store configuration."""

        self._bucket = _require_bucket(config.bucket)
        self._base_path = _normalize_base_path(config.base_path)
        self._endpoint_url = _normalize_optional_string(config.endpoint_url)
        credentials = _credentials_from_config(
            config,
            environment=os.environ if environment is None else environment,
        )

        if client is not None:
            self._client = client
        else:
            factory = client_factory or _create_s3_client
            self._client = factory(
                endpoint_url=self._endpoint_url,
                credentials=credentials,
            )

    def put_bytes(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredObjectWriteResult:
        """Store bytes under a logical key and return write metadata."""

        object_metadata = _normalize_metadata(metadata)
        object_parameters: dict[str, object] = {
            "Metadata": object_metadata,
        }
        if media_type is not None:
            object_parameters["ContentType"] = media_type

        self._client.put_object(
            Bucket=self._bucket,
            Key=self._storage_key(key),
            Body=content,
            **object_parameters,
        )
        return StoredObjectWriteResult(
            key=key,
            size_bytes=len(content),
            media_type=media_type,
            metadata=dict(object_metadata),
        )

    def get_bytes(self, key: str) -> StoredObject:
        """Retrieve bytes for a logical key, raising KeyError if missing."""

        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=self._storage_key(key),
            )
        except Exception as exc:
            if _is_missing_object_error(exc):
                raise KeyError(f"Stored object not found: {key}") from exc
            raise

        content = _read_response_body(response)
        return StoredObject(
            key=key,
            content=content,
            size_bytes=_content_length(response, content),
            media_type=_content_type(response),
            metadata=_response_metadata(response),
        )

    def delete(self, key: str) -> None:
        """Delete a logical key; missing objects are treated as a no-op."""

        try:
            self._client.delete_object(Bucket=self._bucket, Key=self._storage_key(key))
        except Exception as exc:
            if _is_missing_object_error(exc):
                return
            raise

    def exists(self, key: str) -> bool:
        """Return whether a logical key currently exists."""

        try:
            self._client.head_object(Bucket=self._bucket, Key=self._storage_key(key))
        except Exception as exc:
            if _is_missing_object_error(exc):
                return False
            raise
        return True

    def list_keys(self, prefix: str) -> list[str]:
        """List logical keys matching the provided logical prefix."""

        storage_prefix = self._storage_key(prefix)
        continuation_token: str | None = None
        logical_keys: list[str] = []

        while True:
            parameters: dict[str, object] = {
                "Bucket": self._bucket,
                "Prefix": storage_prefix,
            }
            if continuation_token is not None:
                parameters["ContinuationToken"] = continuation_token

            response = self._client.list_objects_v2(**parameters)
            logical_keys.extend(self._logical_keys_from_response(response))

            if not bool(response.get("IsTruncated", False)):
                break

            next_token = response.get("NextContinuationToken")
            if not isinstance(next_token, str) or next_token == "":
                break
            continuation_token = next_token

        return sorted(logical_keys)

    def _storage_key(self, key: str) -> str:
        logical_key = _validate_logical_key(key)
        return f"{self._base_path}{logical_key}"

    def _logical_keys_from_response(self, response: Mapping[str, object]) -> list[str]:
        contents = response.get("Contents", [])
        if not isinstance(contents, Sequence) or isinstance(contents, str | bytes):
            return []

        keys: list[str] = []
        for item in cast(Sequence[object], contents):
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[str, object], item)
            raw_key = item_mapping.get("Key")
            if not isinstance(raw_key, str):
                continue
            if not raw_key.startswith(self._base_path):
                continue
            keys.append(raw_key.removeprefix(self._base_path))
        return keys


def _create_s3_client(
    *,
    endpoint_url: str | None = None,
    credentials: AwsCredentials | None = None,
) -> S3ClientProtocol:
    """Create a boto3 S3 client only when the adapter is instantiated."""

    boto3_module = _load_boto3_module()
    client_constructor = getattr(boto3_module, "client", None)
    if not callable(client_constructor):
        raise ImportError("boto3 is installed, but boto3.client is not available.")

    parameters: dict[str, object] = {}
    if endpoint_url is not None:
        parameters["endpoint_url"] = endpoint_url
    if credentials is not None:
        parameters["aws_access_key_id"] = credentials.aws_access_key_id
        parameters["aws_secret_access_key"] = credentials.aws_secret_access_key
        if credentials.aws_session_token is not None:
            parameters["aws_session_token"] = credentials.aws_session_token

    constructor = cast(S3ClientFactoryCallable, client_constructor)
    client = constructor("s3", **parameters)
    return cast(S3ClientProtocol, client)


class S3ClientFactoryCallable(Protocol):
    """Callable signature for boto3.client."""

    def __call__(self, service_name: str, **kwargs: object) -> object: ...


def _load_boto3_module() -> ModuleType:
    try:
        return importlib.import_module("boto3")
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "The optional boto3 dependency is not installed. Install "
            "chili-backend[s3]."
        ) from exc


def _require_bucket(bucket: str | None) -> str:
    if bucket is None or bucket.strip() == "":
        raise ValueError("S3ObjectStore requires ObjectStoreConfig.bucket to be set.")
    return bucket.strip()


def _normalize_base_path(base_path: str | None) -> str:
    if base_path is None or base_path.strip() == "":
        return ""
    stripped = base_path.strip().strip("/")
    return f"{stripped}/" if stripped else ""


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalize_metadata(metadata: dict[str, object] | None) -> dict[str, str]:
    if metadata is None:
        return {}

    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        if value is None:
            raise ValueError(f"S3 object metadata value for '{key}' cannot be None.")
        normalized[key] = str(value)
    return normalized


def _validate_logical_key(key: str) -> str:
    """Validate object-store logical keys before physical S3 key mapping."""

    if key.startswith("/"):
        raise ValueError("S3 object keys must be relative logical keys.")
    return key


def _credentials_from_config(
    config: ObjectStoreConfig,
    *,
    environment: Mapping[str, str],
) -> AwsCredentials | None:
    env_var = config.credentials_env_var
    if env_var is None:
        return None

    env_var_name = env_var.strip()
    if env_var_name == "":
        raise ValueError("ObjectStoreConfig.credentials_env_var cannot be blank.")

    raw_credentials = environment.get(env_var_name)
    if raw_credentials is None or raw_credentials.strip() == "":
        raise ValueError(
            "S3 credentials are missing. Set the environment variable "
            f"'{env_var_name}'."
        )

    try:
        parsed_credentials = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"S3 credentials in '{env_var_name}' must be a JSON object."
        ) from exc

    if not isinstance(parsed_credentials, dict):
        raise ValueError(f"S3 credentials in '{env_var_name}' must be a JSON object.")

    credentials = cast(dict[str, object], parsed_credentials)
    access_key = _required_credential_string(
        credentials,
        key="aws_access_key_id",
        env_var_name=env_var_name,
    )
    secret_key = _required_credential_string(
        credentials,
        key="aws_secret_access_key",
        env_var_name=env_var_name,
    )
    session_token = _optional_credential_string(
        credentials,
        key="aws_session_token",
        env_var_name=env_var_name,
    )
    return AwsCredentials(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
    )


def _required_credential_string(
    credentials: Mapping[str, object],
    *,
    key: str,
    env_var_name: str,
) -> str:
    value = credentials.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(
            f"S3 credentials in '{env_var_name}' must include non-blank string "
            f"'{key}'."
        )
    return value


def _optional_credential_string(
    credentials: Mapping[str, object],
    *,
    key: str,
    env_var_name: str,
) -> str | None:
    value = credentials.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(
            f"S3 credentials in '{env_var_name}' must include string '{key}' "
            "when provided."
        )
    return value


def _read_response_body(response: Mapping[str, object]) -> bytes:
    body = response.get("Body")
    if body is None:
        return b""
    return cast(ReadableBodyProtocol, body).read()


def _content_length(response: Mapping[str, object], content: bytes) -> int:
    raw_length = response.get("ContentLength")
    return raw_length if isinstance(raw_length, int) else len(content)


def _content_type(response: Mapping[str, object]) -> str | None:
    raw_content_type = response.get("ContentType")
    return raw_content_type if isinstance(raw_content_type, str) else None


def _response_metadata(response: Mapping[str, object]) -> dict[str, object]:
    raw_metadata = response.get("Metadata", {})
    if not isinstance(raw_metadata, Mapping):
        return {}
    metadata = cast(Mapping[object, object], raw_metadata)
    return {str(key): value for key, value in metadata.items()}


def _is_missing_object_error(exc: Exception) -> bool:
    code = _error_code(exc)
    return code in {"404", "NoSuchKey", "NotFound"}


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return None
    response_mapping = cast(Mapping[str, object], response)
    error = response_mapping.get("Error")
    if not isinstance(error, Mapping):
        return None
    error_mapping = cast(Mapping[str, object], error)
    code = error_mapping.get("Code")
    return str(code) if code is not None else None