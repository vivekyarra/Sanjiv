from __future__ import annotations

import os
import subprocess


def _alembic(*args: str) -> None:
    subprocess.run(["uv", "run", "alembic", *args], check=True, env=os.environ.copy())


def test_phase8_migration_upgrade_downgrade_reupgrade() -> None:
    _alembic("upgrade", "20260721_0009")
    _alembic("downgrade", "20260721_0008")
    _alembic("upgrade", "20260721_0009")
