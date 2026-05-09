"""Tests for the S3-compatible object store adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
import importlib
import json
import sys
from types import ModuleType
from typing import Protocol, cast

import pytest

from config.schema import ObjectStoreConfig
from storage.adapters.s3_adapter import (
    AwsCredentials,
    S3ClientProtocol,
    S3ObjectStore,
)
from storage.protocols import ObjectStore


class Boto3ModuleProtocol(Protocol):
    """Small boto3 module surface required by moto integration tests."""

    def client(self, service_name: str, **kwargs: object) -> MotoS3ClientProtocol: ...


class MotoS3ClientProtocol(Protocol):
    """Small S3 client surface used by the moto tests."""

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

    def create_bucket(self, *, Bucket: str) -> object: ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def list_objects_v2(self, **kwargs: object) -> Mapping[str, object]: ...


class Body:
    """Readable body for fake get_object responses."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self) -> bytes:
        return self._content


class ClientError(Exception):
    """Minimal botocore-like error exposing a response code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response: dict[str, object] = {"Error": {"Code": code}}


class FakeS3Client:
    """In-memory fake S3 client for adapter edge-case tests."""

    def __init__(self, *, page_size: int | None = None) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str], str | None]] = {}
        self.deleted_keys: list[str] = []
        self.page_size = page_size
        self.list_calls: list[dict[str, object]] = []

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        **kwargs: object,
    ) -> object:
        metadata = cast(dict[str, str], kwargs.get("Metadata", {}))
        content_type = cast(str | None, kwargs.get("ContentType"))
        self.objects[Key] = (Body, metadata, content_type)
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:
        stored = self.objects.get(Key)
        if stored is None:
            raise ClientError("NoSuchKey")
        content, metadata, content_type = stored
        response: dict[str, object] = {
            "Body": Body(content),
            "ContentLength": len(content),
            "Metadata": metadata,
        }
        if content_type is not None:
            response["ContentType"] = content_type
        return response

    def delete_object(self, *, Bucket: str, Key: str) -> object:
        self.deleted_keys.append(Key)
        self.objects.pop(Key, None)
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:
        if Key not in self.objects:
            raise ClientError("404")
        return {}

    def list_objects_v2(self, **kwargs: object) -> Mapping[str, object]:
        self.list_calls.append(dict(kwargs))
        prefix = cast(str, kwargs.get("Prefix", ""))
        token = cast(str | None, kwargs.get("ContinuationToken"))
        start = int(token) if token is not None else 0
        matching_keys = sorted(key for key in self.objects if key.startswith(prefix))

        if self.page_size is None:
            page_keys = matching_keys[start:]
            next_index = len(matching_keys)
        else:
            next_index = start + self.page_size
            page_keys = matching_keys[start:next_index]

        response: dict[str, object] = {
            "Contents": [{"Key": key} for key in page_keys],
            "IsTruncated": next_index < len(matching_keys),
        }
        if next_index < len(matching_keys):
            response["NextContinuationToken"] = str(next_index)
        return response


class StrictDeleteFakeS3Client(FakeS3Client):
    """Fake S3 client that raises when deleting a missing key."""

    def delete_object(self, *, Bucket: str, Key: str) -> object:
        if Key not in self.objects:
            raise ClientError("NoSuchKey")
        return super().delete_object(Bucket=Bucket, Key=Key)


class RecordingFactory:
    """Client factory that records construction parameters."""

    def __init__(self) -> None:
        self.client = FakeS3Client()
        self.endpoint_url: str | None = None
        self.credentials: AwsCredentials | None = None
        self.calls = 0

    def __call__(
        self,
        *,
        endpoint_url: str | None = None,
        credentials: AwsCredentials | None = None,
    ) -> FakeS3Client:
        self.calls += 1
        self.endpoint_url = endpoint_url
        self.credentials = credentials
        return self.client


def _config(**overrides: object) -> ObjectStoreConfig:
    data: dict[str, object] = {"backend": "s3", "bucket": "test-bucket"}
    data.update(overrides)
    return ObjectStoreConfig.model_validate(data)


def _optional_module(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ImportError:
        pytest.skip(f"Optional test dependency is not installed: {name}")


def _mock_aws() -> AbstractContextManager[object]:
    moto_module = _optional_module("moto")
    mock_aws = getattr(moto_module, "mock_aws", None)
    if not callable(mock_aws):
        pytest.skip("Installed moto package does not expose mock_aws.")
    return cast(Callable[[], AbstractContextManager[object]], mock_aws)()


def _boto3() -> Boto3ModuleProtocol:
    return cast(Boto3ModuleProtocol, _optional_module("boto3"))


def _adapter_client(client: MotoS3ClientProtocol) -> S3ClientProtocol:
    return cast(S3ClientProtocol, client)


def test_s3_object_store_satisfies_protocol() -> None:
    store = S3ObjectStore(_config(), client=FakeS3Client())

    assert isinstance(store, ObjectStore)


def test_s3_object_store_round_trip_with_moto() -> None:
    with _mock_aws():
        boto3_module = _boto3()
        client = boto3_module.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        store = S3ObjectStore(_config(), client=_adapter_client(client))

        written = store.put_bytes(
            "documents/doc-1.txt",
            b"hello s3",
            media_type="text/plain",
            metadata={"source": "moto"},
        )
        stored = store.get_bytes("documents/doc-1.txt")

        assert written.key == "documents/doc-1.txt"
        assert written.size_bytes == 8
        assert written.media_type == "text/plain"
        assert written.metadata == {"source": "moto"}
        assert stored.content == b"hello s3"
        assert stored.media_type == "text/plain"
        assert stored.metadata == {"source": "moto"}
        assert store.exists("documents/doc-1.txt")

        store.delete("documents/doc-1.txt")

        assert not store.exists("documents/doc-1.txt")
        with pytest.raises(KeyError):
            store.get_bytes("documents/doc-1.txt")


def test_s3_object_store_writes_metadata_as_s3_headers_with_moto() -> None:
    with _mock_aws():
        boto3_module = _boto3()
        client = boto3_module.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        store = S3ObjectStore(_config(), client=_adapter_client(client))

        store.put_bytes(
            "documents/doc-1.json",
            b"{}",
            media_type="application/json",
            metadata={"source": "unit-test", "attempt": 2},
        )

        head = client.head_object(Bucket="test-bucket", Key="documents/doc-1.json")

        assert head["ContentType"] == "application/json"
        assert head["Metadata"] == {"source": "unit-test", "attempt": "2"}


def test_s3_object_store_applies_base_path_to_internal_keys_only() -> None:
    client = FakeS3Client()
    store = S3ObjectStore(
        _config(base_path="/knowledgebases/kb-1/"),
        client=client,
    )

    store.put_bytes("documents/doc-1.txt", b"one")
    store.put_bytes("documents/doc-2.txt", b"two")
    store.put_bytes("artifacts/doc-1.json", b"{}")

    assert sorted(client.objects) == [
        "knowledgebases/kb-1/artifacts/doc-1.json",
        "knowledgebases/kb-1/documents/doc-1.txt",
        "knowledgebases/kb-1/documents/doc-2.txt",
    ]
    assert store.list_keys("documents/") == [
        "documents/doc-1.txt",
        "documents/doc-2.txt",
    ]
    assert store.list_keys("") == [
        "artifacts/doc-1.json",
        "documents/doc-1.txt",
        "documents/doc-2.txt",
    ]


def test_s3_object_store_passes_endpoint_url_to_client_factory() -> None:
    factory = RecordingFactory()

    S3ObjectStore(
        _config(endpoint_url="http://localhost:9000"),
        client_factory=factory,
    )

    assert factory.calls == 1
    assert factory.endpoint_url == "http://localhost:9000"
    assert factory.credentials is None


def test_s3_object_store_reads_credentials_env_var_json() -> None:
    factory = RecordingFactory()
    environment = {
        "AWS_CREDENTIALS": json.dumps(
            {
                "aws_access_key_id": "access",
                "aws_secret_access_key": "secret",
            }
        )
    }

    S3ObjectStore(
        _config(credentials_env_var="AWS_CREDENTIALS"),
        client_factory=factory,
        environment=environment,
    )

    assert factory.credentials == AwsCredentials(
        aws_access_key_id="access",
        aws_secret_access_key="secret",
    )


def test_s3_object_store_reads_optional_session_token() -> None:
    factory = RecordingFactory()
    environment = {
        "AWS_CREDENTIALS": json.dumps(
            {
                "aws_access_key_id": "access",
                "aws_secret_access_key": "secret",
                "aws_session_token": "token",
            }
        )
    }

    S3ObjectStore(
        _config(credentials_env_var="AWS_CREDENTIALS"),
        client_factory=factory,
        environment=environment,
    )

    assert factory.credentials == AwsCredentials(
        aws_access_key_id="access",
        aws_secret_access_key="secret",
        aws_session_token="token",
    )


def test_s3_object_store_uses_default_credential_chain_when_env_var_unset() -> None:
    factory = RecordingFactory()

    S3ObjectStore(_config(), client_factory=factory, environment={})

    assert factory.credentials is None


@pytest.mark.parametrize(
    ("environment", "match"),
    [
        ({}, "missing"),
        ({"AWS_CREDENTIALS": "not json"}, "JSON object"),
        ({"AWS_CREDENTIALS": "[]"}, "JSON object"),
        (
            {"AWS_CREDENTIALS": json.dumps({"aws_secret_access_key": "secret"})},
            "aws_access_key_id",
        ),
        (
            {"AWS_CREDENTIALS": json.dumps({"aws_access_key_id": "access"})},
            "aws_secret_access_key",
        ),
        (
            {
                "AWS_CREDENTIALS": json.dumps(
                    {
                        "aws_access_key_id": "access",
                        "aws_secret_access_key": "secret",
                        "aws_session_token": "",
                    }
                )
            },
            "aws_session_token",
        ),
    ],
)
def test_s3_object_store_rejects_invalid_credentials_env_var(
    environment: Mapping[str, str],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        S3ObjectStore(
            _config(credentials_env_var="AWS_CREDENTIALS"),
            client_factory=RecordingFactory(),
            environment=environment,
        )


def test_s3_object_store_rejects_blank_credentials_env_var_name() -> None:
    with pytest.raises(ValueError, match="credentials_env_var"):
        S3ObjectStore(
            _config(credentials_env_var="  "),
            client_factory=RecordingFactory(),
            environment={},
        )


def test_s3_object_store_reports_missing_optional_boto3_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> ModuleType:
        if name == "boto3":
            raise ImportError("No module named boto3")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError, match=r"chili-backend\[s3\]"):
        S3ObjectStore(_config(), environment={})


def test_storage_package_import_does_not_require_boto3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> ModuleType:
        if name == "boto3":
            raise ImportError("No module named boto3")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    for module_name in [
        "storage",
        "storage.adapters",
        "storage.adapters.s3_adapter",
    ]:
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    storage_module = importlib.import_module("storage")

    assert getattr(storage_module, "S3ObjectStore") is not None


def test_s3_object_store_requires_non_blank_bucket() -> None:
    with pytest.raises(ValueError, match="bucket"):
        S3ObjectStore(_config(bucket="  "), client=FakeS3Client())


@pytest.mark.parametrize("key", ["/documents/doc-1.txt", "/"])
def test_s3_object_store_rejects_leading_slash_logical_keys(key: str) -> None:
    store = S3ObjectStore(_config(), client=FakeS3Client())

    with pytest.raises(ValueError, match="relative logical keys"):
        store.put_bytes(key, b"content")

    with pytest.raises(ValueError, match="relative logical keys"):
        store.get_bytes(key)

    with pytest.raises(ValueError, match="relative logical keys"):
        store.exists(key)

    with pytest.raises(ValueError, match="relative logical keys"):
        store.delete(key)

    with pytest.raises(ValueError, match="relative logical keys"):
        store.list_keys(key)


def test_s3_object_store_rejects_none_metadata_values() -> None:
    store = S3ObjectStore(_config(), client=FakeS3Client())

    with pytest.raises(ValueError, match="cannot be None"):
        store.put_bytes("documents/doc-1.txt", b"content", metadata={"bad": None})


def test_s3_object_store_stringifies_metadata_values() -> None:
    store = S3ObjectStore(_config(), client=FakeS3Client())

    written = store.put_bytes(
        "documents/doc-1.txt",
        b"content",
        metadata={"attempt": 2, "active": True},
    )
    stored = store.get_bytes("documents/doc-1.txt")

    assert written.metadata == {"attempt": "2", "active": "True"}
    assert stored.metadata == {"attempt": "2", "active": "True"}


def test_s3_object_store_list_keys_handles_pagination() -> None:
    client = FakeS3Client(page_size=2)
    store = S3ObjectStore(_config(base_path="kb-1"), client=client)
    for key in ["docs/c.txt", "docs/a.txt", "docs/b.txt", "other.txt", "docs/d.txt"]:
        store.put_bytes(key, key.encode())

    keys = store.list_keys("docs/")

    assert keys == ["docs/a.txt", "docs/b.txt", "docs/c.txt", "docs/d.txt"]
    assert len(client.list_calls) == 2
    assert client.list_calls[0]["Prefix"] == "kb-1/docs/"
    assert client.list_calls[1]["ContinuationToken"] == "2"


def test_s3_object_store_delete_missing_key_is_no_op() -> None:
    store = S3ObjectStore(_config(), client=FakeS3Client())

    store.delete("missing")

    assert not store.exists("missing")


def test_s3_object_store_delete_missing_key_error_is_no_op() -> None:
    store = S3ObjectStore(_config(), client=StrictDeleteFakeS3Client())

    store.delete("missing")

    assert not store.exists("missing")