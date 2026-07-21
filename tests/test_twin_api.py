import httpx
import pytest
from sanjiv.main import app


@pytest.mark.asyncio
async def test_network_api_exposes_frozen_inspectable_snapshot() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/twin/network")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mass_balance"]["conserved"] is True
    assert len(payload["grades"]) == 12
    assert payload["evidence_records"]
    assert payload["assumptions"]
    assert len(payload["fingerprint"]) == 64


@pytest.mark.asyncio
async def test_snapshot_lookup_requires_exact_immutable_id() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        current = (await client.get("/api/v1/twin/snapshots/current")).json()
        found = await client.get(f"/api/v1/twin/snapshots/{current['snapshot_id']}")
        missing = await client.get("/api/v1/twin/snapshots/00000000-0000-0000-0000-000000000000")
    assert found.status_code == 200
    assert found.json()["fingerprint"] == current["fingerprint"]
    assert missing.status_code == 404


def test_openapi_contains_twin_contracts() -> None:
    schema = app.openapi()
    assert "/api/v1/twin/network" in schema["paths"]
    assert "TwinSnapshot" in schema["components"]["schemas"]
    required = set(schema["components"]["schemas"]["TwinSnapshot"]["required"])
    assert {"fingerprint", "nodes", "routes", "grades", "mass_balance"} <= required
