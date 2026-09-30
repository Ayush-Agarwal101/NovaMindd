"""
Tests — Integration: API endpoints

Smoke-tests the FastAPI application layer with a TestClient.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from apps.api.main import app
    return TestClient(app, raise_server_exceptions=True)


def test_health_endpoint(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_list(client: TestClient):
    r = client.get("/api/v1/models/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_tools_list(client: TestClient):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    tools = r.json()
    assert isinstance(tools, list)
    ids = [t["tool_id"] for t in tools]
    assert "python_exec" in ids
    assert "knowledge_search" in ids


def test_artifact_generate_docx(client: TestClient):
    pytest.importorskip("docx")
    payload = {
        "format": "docx",
        "document_ir": {
            "title": "Test Report",
            "author": "NovaMindd",
            "blocks": [
                {"block_type": "paragraph", "text": "Hello from NovaMindd.", "items": [], "rows": [], "metadata": {}}
            ],
            "metadata": {},
            "evidence_refs": [],
        },
    }
    r = client.post("/api/v1/artifacts/generate", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert len(r.content) > 0


def test_artifact_generate_invalid_format(client: TestClient):
    payload = {
        "format": "csv",
        "document_ir": {"title": "T", "blocks": [], "metadata": {}, "evidence_refs": []},
    }
    r = client.post("/api/v1/artifacts/generate", json=payload)
    assert r.status_code == 400


def test_knowledge_search_empty_query(client: TestClient):
    r = client.post("/api/v1/knowledge/search", json={"query": "   ", "top_k": 5})
    assert r.status_code == 400


def test_model_route_unknown_capability(client: TestClient):
    r = client.post("/api/v1/models/route", json={"capability": "does_not_exist"})
    assert r.status_code == 400
