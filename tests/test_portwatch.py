from datetime import UTC, datetime

import pytest
from sanjiv.risk.portwatch import PortWatchService, PortWatchUnavailable


def _query() -> dict[str, object]:
    return {
        "features": [
            {
                "attributes": {
                    "date": "2026-07-19",
                    "portid": "chokepoint6",
                    "portname": "Strait of Hormuz",
                    "n_tanker": 4,
                    "n_total": 15,
                    "capacity_tanker": 39_216,
                    "capacity": 182_620,
                }
            }
        ]
    }


@pytest.mark.asyncio
async def test_portwatch_returns_typed_observed_current_data() -> None:
    async def fetcher(url: str, params: dict[str, str]) -> dict[str, object]:
        del params
        if url.endswith("/query"):
            return _query()
        return {"editingInfo": {"dataLastEditDate": 1_784_636_715_460}}

    observation = await PortWatchService(fetcher).hormuz_current()

    assert observation.source_id == "IMF_PORTWATCH"
    assert observation.mode == "LIVE"
    assert observation.truth_class == "OBSERVED"
    assert observation.tanker_transits == 4
    assert observation.total_transits == 15
    assert observation.estimated_tanker_tonnage == 39_216
    assert observation.source_modified_at == datetime.fromtimestamp(1_784_636_715.46, tz=UTC)
    assert len(observation.evidence_id) == 64


@pytest.mark.asyncio
async def test_portwatch_rejects_missing_observations() -> None:
    async def fetcher(url: str, params: dict[str, str]) -> dict[str, object]:
        del url, params
        return {"features": []}

    with pytest.raises(PortWatchUnavailable, match="no Strait of Hormuz"):
        await PortWatchService(fetcher).hormuz_current()
