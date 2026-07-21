from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sanjiv.main import create_app
from sanjiv.operations import security
from sanjiv.operations.security import ProductionSecurityMiddleware
from sanjiv.settings import Settings

from workers.runner import run


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "sanjiv_maritime_storage": "memory",
        "sanjiv_maritime_autostart": False,
        "sanjiv_scenario_storage": "memory",
        "sanjiv_procurement_storage": "memory",
        "sanjiv_reserve_storage": "memory",
        "sanjiv_risk_storage": "memory",
        "sanjiv_audit_storage": "memory",
        "sanjiv_phase8_storage": "memory",
        "sanjiv_worker_runtime_dir": tmp_path / "workers",
        "sanjiv_replay_runtime_dir": tmp_path / "replay",
    }
    values.update(updates)
    return Settings(**values)


def test_production_api_fails_closed_and_accepts_configured_key(tmp_path: Path) -> None:
    closed = _settings(tmp_path, sanjiv_env="production", sanjiv_api_keys="[]")
    with TestClient(create_app(settings=closed)) as client:
        response = client.get("/api/v1/contracts/sample")
        assert response.status_code == 503
        assert response.json()["code"] == "AUTH_CONFIGURATION_REQUIRED"

    configured = _settings(
        tmp_path,
        sanjiv_env="production",
        sanjiv_api_keys='["production-test-key"]',
    )
    with TestClient(create_app(settings=configured)) as client:
        denied = client.get("/api/v1/contracts/sample")
        allowed = client.get(
            "/api/v1/contracts/sample", headers={"X-Sanjiv-API-Key": "production-test-key"}
        )
        assert denied.status_code == 401
        assert allowed.status_code == 200


def test_production_non_domain_mutation_cannot_bypass_auth_without_idempotency(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, sanjiv_env="production", sanjiv_api_keys="[]")
    with TestClient(create_app(settings=settings)) as client:
        response = client.post("/api/v1/replays/replay:hormuz-full-14d/runs", json={})
        assert response.status_code == 503
        assert response.json()["code"] == "AUTH_CONFIGURATION_REQUIRED"


def test_ssrf_destination_and_unbounded_security_configuration_are_rejected() -> None:
    with pytest.raises(ValueError, match="documented AISStream WSS host"):
        Settings(sanjiv_aisstream_url="wss://127.0.0.1/internal")
    with pytest.raises(ValueError):
        Settings(sanjiv_rate_limit_per_minute=1)
    with pytest.raises(ValueError):
        Settings(sanjiv_max_request_bytes=100_000_000)


def test_readiness_reports_database_redis_and_minio_interruptions(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        sanjiv_dependency_checks_enabled=True,
        database_url="postgresql+asyncpg://sanjiv:test@127.0.0.1:1/sanjiv",
        redis_url="redis://127.0.0.1:1/0",
        minio_endpoint="http://127.0.0.1:1",
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert set(response.json()["unavailable"]) == {
            "database:postgres",
            "cache:redis",
            "object-store:minio",
        }


def test_origin_size_type_rate_limit_and_security_headers(tmp_path: Path) -> None:
    settings = _settings(tmp_path, sanjiv_rate_limit_per_minute=10, sanjiv_max_request_bytes=1024)
    with TestClient(create_app(settings=settings)) as client:
        origin = client.get(
            "/api/v1/contracts/sample", headers={"Origin": "https://untrusted.example"}
        )
        assert origin.status_code == 403
        assert origin.json()["code"] == "ORIGIN_NOT_ALLOWED"

        oversized = client.post(
            "/api/v1/scenarios/compile",
            headers={"Content-Length": "2048", "Content-Type": "application/json"},
            content=b"{}",
        )
        assert oversized.status_code == 413

        unsupported = client.post(
            "/api/v1/scenarios/compile",
            headers={"Content-Type": "text/plain"},
            content=b"not-json",
        )
        assert unsupported.status_code == 415

    rate_settings = _settings(tmp_path, sanjiv_rate_limit_per_minute=10)
    with TestClient(create_app(settings=rate_settings)) as client:
        responses = [client.get("/health/live") for _ in range(11)]
        assert responses[-1].status_code == 429
        assert responses[-1].headers["Retry-After"] == "60"
        successful = responses[0]
        assert successful.headers["X-Content-Type-Options"] == "nosniff"
        assert successful.headers["Content-Security-Policy"].startswith("default-src")


def test_rate_limit_identity_storage_is_bounded_and_does_not_store_api_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security, "MAX_RATE_LIMIT_IDENTITIES", 5)
    middleware = ProductionSecurityMiddleware(object(), _settings(tmp_path))
    for index in range(20):
        middleware._rate_limited(middleware._rate_limit_key(f"private-key-{index}"))
    assert len(middleware._requests) <= 5
    assert all("private-key" not in identity for identity in middleware._requests)


def test_correlation_trace_metrics_worker_health_and_log_redaction(
    tmp_path: Path, caplog: object
) -> None:
    runtime = tmp_path / "workers"
    asyncio.run(run("ingestion", runtime, once=True))
    asyncio.run(run("refresh", runtime, once=True))
    asyncio.run(run("compute", runtime, once=True))
    settings = _settings(tmp_path)
    logger_capture = caplog
    assert hasattr(logger_capture, "set_level")
    logger_capture.set_level(logging.INFO, logger="sanjiv.request")
    with TestClient(create_app(settings=settings)) as client:
        response = client.get(
            "/api/v1/contracts/sample",
            headers={
                "X-Correlation-ID": "phase9-correlation",
                "X-Causation-ID": "phase9-causation",
                "Authorization": "Bearer must-not-appear",
            },
        )
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == "phase9-correlation"
        assert response.headers["X-Causation-ID"] == "phase9-causation"
        assert response.headers["traceparent"].startswith("00-")
        status = client.get("/api/v1/operations/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["opentelemetry_compatible"] is True
        assert (
            len([item for item in payload["components"] if item["component"].startswith("worker:")])
            == 3
        )
        assert all(
            item["status"] == "HEALTHY"
            for item in payload["components"]
            if item["component"].startswith("worker:")
        )
        assert any(
            item["operation"] == "GET /api/v1/contracts/sample" for item in payload["runtimes"]
        )
    records = [
        json.loads(record.message)
        for record in logger_capture.records
        if record.name == "sanjiv.request"
    ]
    assert records
    assert "must-not-appear" not in json.dumps(records)


def test_unhandled_error_redacts_exception_and_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import sanjiv.sample

    def fail_safely() -> object:
        raise RuntimeError("private-token-must-not-leak")

    monkeypatch.setattr(sanjiv.sample, "build_foundation_sample", fail_safely)
    caplog.set_level(logging.ERROR, logger="sanjiv.error")
    with TestClient(
        create_app(settings=_settings(tmp_path)), raise_server_exceptions=False
    ) as client:
        response = client.get("/api/v1/contracts/sample")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "private-token" not in response.text
    assert "private-token" not in caplog.text
