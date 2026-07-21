from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse

from sanjiv.operations.contracts import ComponentHealth
from sanjiv.settings import Settings


async def _tcp_component(name: str, host: str, port: int) -> ComponentHealth:
    now = datetime.now(UTC)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.0)
        del reader
        writer.close()
        await writer.wait_closed()
        return ComponentHealth(
            component=name,
            status="HEALTHY",
            checked_at=now,
            detail=f"TCP dependency reachable at {host}:{port}.",
        )
    except (OSError, TimeoutError):
        return ComponentHealth(
            component=name,
            status="UNAVAILABLE",
            checked_at=now,
            detail=f"TCP dependency unavailable at {host}:{port}.",
            stale=True,
        )


def _host_port(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or default_port


async def dependency_health(settings: Settings) -> list[ComponentHealth]:
    database_host, database_port = _host_port(settings.database_url, 5432)
    redis_host, redis_port = _host_port(settings.redis_url, 6379)
    minio_host, minio_port = _host_port(settings.minio_endpoint, 9000)
    return list(
        await asyncio.gather(
            _tcp_component("database:postgres", database_host, database_port),
            _tcp_component("cache:redis", redis_host, redis_port),
            _tcp_component("object-store:minio", minio_host, minio_port),
        )
    )
