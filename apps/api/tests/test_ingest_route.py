"""Tests for the HTTP /ingest route guards (MTC-07, MTC-09).

The actual ingestion pipeline is mocked — these tests verify the request
plumbing: API key auth, MIME validation, size cap, and timeout handling.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.ingestion.pipeline import IngestionResult
from src.main import app

API_KEY = get_settings().api_key.get_secret_value()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fake_ingest():
    async def _fake(path: Path) -> IngestionResult:
        return IngestionResult(
            doc_id="abc123",
            source_uri=str(path.resolve()),
            total_chunks=4,
            upserted=4,
            skipped_unchanged=0,
        )

    with patch("src.routes.ingest.ingest_document", side_effect=_fake) as m:
        yield m


def test_ingest_requires_api_key(client: TestClient) -> None:
    response = client.post(
        "/ingest",
        files={"file": ("foo.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401


def test_ingest_accepts_text_plain(client: TestClient, fake_ingest) -> None:
    response = client.post(
        "/ingest",
        headers={"X-API-Key": API_KEY},
        files={"file": ("doc.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"] == "doc.txt"
    assert body["doc_id"] == "abc123"
    assert body["total_chunks"] == 4
    assert body["upserted"] == 4
    assert body["skipped_unchanged"] == 0


def test_ingest_accepts_pdf(client: TestClient, fake_ingest) -> None:
    response = client.post(
        "/ingest",
        headers={"X-API-Key": API_KEY},
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 200


def test_ingest_accepts_extension_when_mime_is_octet_stream(
    client: TestClient, fake_ingest
) -> None:
    # Some browsers send octet-stream for unknown types — fall back to extension.
    response = client.post(
        "/ingest",
        headers={"X-API-Key": API_KEY},
        files={"file": ("notes.md", b"# title", "application/octet-stream")},
    )
    assert response.status_code == 200


def test_ingest_rejects_unsupported_mime_and_extension(
    client: TestClient, fake_ingest
) -> None:
    # MTC-09: neither MIME nor extension is allowed.
    response = client.post(
        "/ingest",
        headers={"X-API-Key": API_KEY},
        files={"file": ("evil.exe", b"MZ\x90", "application/x-msdownload")},
    )
    assert response.status_code == 415


def test_ingest_rejects_oversized_file(client: TestClient, fake_ingest) -> None:
    # MTC-09: 25 MB cap. We send 26 MB to trigger the chunked-read abort.
    big = b"a" * (26 * 1024 * 1024)
    response = client.post(
        "/ingest",
        headers={"X-API-Key": API_KEY},
        files={"file": ("big.txt", big, "text/plain")},
    )
    assert response.status_code == 413


def test_ingest_translates_pipeline_value_error_to_400(client: TestClient) -> None:
    async def _raise(_path: Path) -> IngestionResult:
        raise ValueError("Loaded empty content from /tmp/foo.txt")

    with patch("src.routes.ingest.ingest_document", side_effect=_raise):
        response = client.post(
            "/ingest",
            headers={"X-API-Key": API_KEY},
            files={"file": ("empty.txt", b"   ", "text/plain")},
        )
    assert response.status_code == 400
    assert "empty content" in response.json()["detail"].lower()


def test_ingest_timeout_returns_408(client: TestClient) -> None:
    import asyncio

    async def _slow(_path: Path) -> IngestionResult:
        await asyncio.sleep(10)
        raise RuntimeError("should have been cancelled")

    settings = get_settings()
    with (
        patch("src.routes.ingest.ingest_document", side_effect=_slow),
        patch.object(settings, "ingest_timeout_seconds", 1),
    ):
        response = client.post(
            "/ingest",
            headers={"X-API-Key": API_KEY},
            files={"file": ("slow.txt", b"hi", "text/plain")},
        )
    assert response.status_code == 408


def _fake_qdrant_client(matched: int) -> object:
    """Return a context manager yielding a Qdrant client stub for DELETE tests."""
    client = SimpleNamespace(
        count=AsyncMock(return_value=SimpleNamespace(count=matched)),
        delete=AsyncMock(return_value=None),
    )

    @asynccontextmanager
    async def _cm():
        yield client

    return _cm


def test_delete_document_requires_api_key(client: TestClient) -> None:
    response = client.delete("/ingest/abc123")
    assert response.status_code == 401


def test_delete_document_removes_all_matching_points(client: TestClient) -> None:
    fake_cm = _fake_qdrant_client(matched=3)
    invalidate = MagicMock()
    with (
        patch("src.routes.ingest.qdrant_client", side_effect=fake_cm),
        patch("src.routes.ingest.invalidate_bm25_cache", side_effect=invalidate),
    ):
        response = client.delete(
            "/ingest/573013e6a628b8aa",
            headers={"X-API-Key": API_KEY},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"doc_id": "573013e6a628b8aa", "deleted": 3}
    invalidate.assert_called_once()


def test_delete_document_404_when_not_found(client: TestClient) -> None:
    fake_cm = _fake_qdrant_client(matched=0)
    with patch("src.routes.ingest.qdrant_client", side_effect=fake_cm):
        response = client.delete(
            "/ingest/nonexistent",
            headers={"X-API-Key": API_KEY},
        )
    assert response.status_code == 404
    assert "nonexistent" in response.json()["detail"]
