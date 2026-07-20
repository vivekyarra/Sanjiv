import httpx
import pytest
from sanjiv.main import app


@pytest.mark.asyncio
async def test_liveness() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_contract_sample_is_not_live() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/contracts/sample")
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]["mode"] == "FIXTURE"
    assert payload["metric"]["truth_class"] == "ASSUMPTION"
