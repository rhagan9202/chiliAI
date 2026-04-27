"""Tests for input validation helpers wired into router-style endpoints (E10-S10).

The helpers in :mod:`shared.validation` are consumed by router code via
small local wrappers. These tests build a FastAPI test app that exercises
exactly the same wrappers a router would use, so coverage matches the
production pattern even before each router is hardened individually.
"""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.testclient import TestClient

from api.dependencies import get_domain_config
from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    ValidationConfig,
)
from shared.validation import (
    sanitize_filename,
    validate_content_type,
    validate_query_length,
)


def _build_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="t", display_name="T", description="d"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=False),
        validation=ValidationConfig(
            max_file_size_mb=1,
            allowed_content_types=["text/plain", "application/json"],
            max_query_length=20,
        ),
        alerts=AlertsConfig(thresholds={}),
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    config = _build_config()
    app.dependency_overrides[get_domain_config] = lambda: config

    validation = config.validation
    assert validation is not None
    max_bytes = validation.max_file_size_mb * 1024 * 1024
    allowed = set(validation.allowed_content_types)
    max_query = validation.max_query_length

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)) -> dict[str, object]:
        if not validate_content_type(file.content_type, allowed):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Content type '{file.content_type}' not allowed.",
            )
        body = await file.read()
        if len(body) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large.",
            )
        cleaned = sanitize_filename(file.filename or "upload")
        return {"filename": cleaned, "size": len(body)}

    @app.get("/search")
    def search(q: str = Query(...)) -> dict[str, object]:
        try:
            cleaned = validate_query_length(q, max_query)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        return {"q": cleaned}

    return app


class TestUploadValidation:
    def test_oversized_file_returns_413(self) -> None:
        client = TestClient(_build_app())
        # 1 MB cap; send 2 MB.
        body = b"x" * (2 * 1024 * 1024)
        response = client.post(
            "/upload",
            files={"file": ("big.txt", body, "text/plain")},
        )
        assert response.status_code == 413

    def test_disallowed_content_type_returns_415(self) -> None:
        client = TestClient(_build_app())
        response = client.post(
            "/upload",
            files={"file": ("dat.bin", b"abc", "application/octet-stream")},
        )
        assert response.status_code == 415

    def test_filename_with_path_traversal_is_sanitized(self) -> None:
        client = TestClient(_build_app())
        response = client.post(
            "/upload",
            files={"file": ("../../etc/passwd", b"hi", "text/plain")},
        )
        assert response.status_code == 200
        cleaned = response.json()["filename"]
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert ".." not in cleaned


class TestQueryValidation:
    def test_overlength_query_returns_422(self) -> None:
        client = TestClient(_build_app())
        response = client.get("/search", params={"q": "x" * 100})
        assert response.status_code == 422

    def test_within_limit_query_returns_200(self) -> None:
        client = TestClient(_build_app())
        response = client.get("/search", params={"q": "hello"})
        assert response.status_code == 200
        assert response.json()["q"] == "hello"


class TestHelperFunctionsDirectly:
    def test_validate_content_type_strips_parameters(self) -> None:
        assert validate_content_type(
            "text/plain; charset=utf-8", {"text/plain"}
        )

    def test_validate_content_type_none_rejected(self) -> None:
        assert not validate_content_type(None, {"text/plain"})

    def test_sanitize_filename_collapses_empty_to_default(self) -> None:
        assert sanitize_filename("") == "upload"
        assert sanitize_filename("....") == "upload"

    def test_sanitize_filename_strips_null_byte(self) -> None:
        assert "\x00" not in sanitize_filename("good\x00name.txt")

    def test_sanitize_filename_handles_windows_reserved_names(self) -> None:
        result = sanitize_filename("CON.txt")
        assert result.startswith("_")

    def test_validate_query_length_strips_whitespace(self) -> None:
        assert validate_query_length("  hello  ", 50) == "hello"

    def test_validate_query_length_raises_on_overflow(self) -> None:
        import pytest as _pytest

        with _pytest.raises(ValueError):
            validate_query_length("x" * 1000, 10)
