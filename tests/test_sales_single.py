"""Single-run sales API and website normalization."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import sales_app
from agent.sales_app import domain_hint_from_website


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _noop(job_id: str) -> None:
        return

    monkeypatch.setattr(sales_app, "_run_batch", _noop)
    return TestClient(sales_app.create_app())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("example.com", "example.com"),
        ("https://www.example.com/foo", "example.com"),
        ("http://sub.example.com:8080/", "sub.example.com"),
        ("WWW.FOO.COM", "foo.com"),
    ],
)
def test_domain_hint_from_website(raw: str | None, expected: str | None) -> None:
    assert domain_hint_from_website(raw) == expected


def test_post_single_returns_job(client: TestClient) -> None:
    r = client.post(
        "/api/single",
        json={
            "company": "Acme Corp",
            "website": "https://www.acme.com/path",
            "poc_name": "Jane Doe",
            "poc_title": "VP Sales",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["row_count"] == 1
    assert data["filename"] == "single-run"
    assert "job_id" in data
    assert len(data["rows"]) == 1
    assert data["rows"][0]["company"] == "Acme Corp"
    assert data["rows"][0]["domain"] == "acme.com"
