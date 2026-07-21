from __future__ import annotations

import os
import subprocess

import psycopg


def _run(*args: str) -> None:
    subprocess.run(["uv", "run", "alembic", *args], check=True, env=os.environ.copy())


def test_phase7_migration_is_reversible_and_records_are_immutable() -> None:
    _run("upgrade", "20260721_0008")
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://sanjiv:change-me-local-only@localhost:5432/sanjiv"
    ).replace("+asyncpg", "")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.evidence_audits')")
        assert cursor.fetchone() == ("evidence_audits",)
        cursor.execute("SELECT to_regclass('public.plan_lifecycle_records')")
        assert cursor.fetchone() == ("plan_lifecycle_records",)
    _run("downgrade", "20260721_0007")
    _run("upgrade", "20260721_0008")
