from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def _run(
    command: list[str], *, stdin: bytes | None = None, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, input=stdin, capture_output=True, check=check)


def main() -> None:
    runtime = Path("data/runtime/backups")
    runtime.mkdir(parents=True, exist_ok=True)
    backup = runtime / "sanjiv-restore-test.dump"
    report_path = Path("reports/recovery/backup-restore.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    dump = _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "sanjiv",
            "-d",
            "sanjiv",
            "-Fc",
        ]
    ).stdout
    backup.write_bytes(dump)
    os.chmod(backup, 0o600)
    checksum = hashlib.sha256(dump).hexdigest()
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "dropdb",
            "-U",
            "sanjiv",
            "--if-exists",
            "sanjiv_restore_verify",
        ]
    )
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "createdb",
            "-U",
            "sanjiv",
            "--template",
            "template0",
            "sanjiv_restore_verify",
        ]
    )
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "sanjiv",
            "-d",
            "sanjiv_restore_verify",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT timescaledb_pre_restore();",
        ]
    )
    restored = _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "sanjiv",
            "-d",
            "sanjiv_restore_verify",
            "--exit-on-error",
        ],
        stdin=dump,
    )
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "sanjiv",
            "-d",
            "sanjiv_restore_verify",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "SELECT timescaledb_post_restore();",
        ]
    )
    verification = (
        _run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "sanjiv",
                "-d",
                "sanjiv_restore_verify",
                "-Atc",
                "SELECT version_num FROM alembic_version",
            ]
        )
        .stdout.decode()
        .strip()
    )
    corrupted = bytearray(dump)
    if corrupted:
        corrupted[0] ^= 0xFF
    corrupt_result = _run(
        ["docker", "compose", "exec", "-T", "postgres", "pg_restore", "-U", "sanjiv", "-l"],
        stdin=bytes(corrupted),
        check=False,
    )
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "dropdb",
            "-U",
            "sanjiv",
            "--if-exists",
            "sanjiv_restore_verify",
        ]
    )
    backup.unlink()
    report = {
        "schema_version": "1.0",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "backup_sha256": checksum,
        "backup_bytes": len(dump),
        "restore_exit_code": restored.returncode,
        "restored_migration": verification,
        "corrupt_artifact_rejected": corrupt_result.returncode != 0,
        "confidentiality": (
            "Temporary backup permission 0600; deleted immediately after verification."
        ),
        "status": "PASS" if verification and corrupt_result.returncode != 0 else "FAIL",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
