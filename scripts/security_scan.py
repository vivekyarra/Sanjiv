from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _run(command: list[str], *, output: Path | None = None) -> dict[str, Any]:
    executed = command
    if os.name == "nt" and command[0] == "npm":
        executed = ["npm.cmd", *command[1:]]
    elif os.name == "nt" and command[0] in {"uv", "uvx"}:
        uv_arguments = ["tool", "run", *command[1:]] if command[0] == "uvx" else command[1:]
        executed = [sys._base_executable, "-m", "uv", *uv_arguments]
    completed = subprocess.run(executed, capture_output=True, text=True, check=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(completed.stdout or "{}\n", encoding="utf-8")
    return {
        "command": command[0],
        "exit_code": completed.returncode,
        "stderr_tail": completed.stderr[-1000:],
    }


def _docker_mount(root: Path) -> str:
    return f"{root.resolve()}:/repo"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the portable Sanjiv security gate.")
    parser.add_argument("--images", action="store_true", help="Also scan built API and web images.")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    report_dir = root / "reports" / "security"
    report_dir.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, Any]] = {}

    checks["npm_audit"] = _run(["npm", "audit", "--json"], output=report_dir / "npm-audit.json")
    requirements = report_dir / "requirements-audit.txt"
    checks["uv_export"] = _run(
        [
            "uv",
            "export",
            "--frozen",
            "--all-groups",
            "--format",
            "requirements.txt",
            "--no-hashes",
            "--output-file",
            "reports/security/requirements-audit.txt",
        ]
    )
    checks["pip_audit"] = _run(
        ["uvx", "pip-audit", "--requirement", str(requirements), "--format", "json"],
        output=report_dir / "pip-audit.json",
    )
    checks["bandit"] = _run(
        [
            "uvx",
            "bandit",
            "-r",
            "services/api/sanjiv",
            "workers",
            "scripts",
            "-f",
            "json",
            "-q",
            "-ll",
        ],
        output=report_dir / "bandit.json",
    )

    gitleaks_report = report_dir / "gitleaks.json"
    if shutil.which("gitleaks"):
        gitleaks_command = [
            "gitleaks",
            "dir",
            str(root),
            "--no-banner",
            "--redact",
            "--report-format",
            "json",
            "--report-path",
            str(gitleaks_report),
        ]
    else:
        gitleaks_command = [
            "docker",
            "run",
            "--rm",
            "-v",
            _docker_mount(root),
            "zricethezav/gitleaks:latest",
            "dir",
            "/repo",
            "--no-banner",
            "--redact",
            "--report-format",
            "json",
            "--report-path",
            "/repo/reports/security/gitleaks.json",
        ]
    checks["gitleaks"] = _run(gitleaks_command)
    if not gitleaks_report.exists():
        gitleaks_report.write_text("[]\n", encoding="utf-8")

    trivy_command = [
        "docker",
        "run",
        "--rm",
        "-v",
        _docker_mount(root),
        "-v",
        "sanjiv-trivy-cache:/root/.cache/trivy",
        "aquasec/trivy:latest",
        "fs",
        "--no-progress",
        "--timeout",
        "10m",
        "--scanners",
        "vuln,misconfig",
        "--severity",
        "MEDIUM,HIGH,CRITICAL",
        "--ignored-licenses",
        "LGPL-3.0-or-later",
        "--ignored-licenses",
        "Apache-2.0 AND LGPL-3.0-or-later",
        "--ignored-licenses",
        "Apache-2.0 AND LGPL-3.0-or-later AND MIT",
        "--ignored-licenses",
        "MPL-2.0",
        "--include-dev-deps",
        "--exit-code",
        "1",
        "--skip-dirs",
        "node_modules",
        "--skip-dirs",
        ".venv",
        "--skip-dirs",
        ".git",
        "--skip-dirs",
        "apps/web/.next",
        "--skip-dirs",
        "reports",
        "--format",
        "json",
        "--output",
        "/repo/reports/security/trivy-filesystem.json",
        "/repo",
    ]
    checks["trivy_filesystem"] = _run(trivy_command)
    checks["trivy_licenses"] = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            _docker_mount(root),
            "-v",
            "sanjiv-trivy-cache:/root/.cache/trivy",
            "aquasec/trivy:latest",
            "fs",
            "--no-progress",
            "--scanners",
            "license",
            "--severity",
            "MEDIUM,HIGH,CRITICAL",
            "--ignored-licenses",
            "LGPL-3.0-or-later",
            "--ignored-licenses",
            "Apache-2.0 AND LGPL-3.0-or-later",
            "--ignored-licenses",
            "Apache-2.0 AND LGPL-3.0-or-later AND MIT",
            "--ignored-licenses",
            "MPL-2.0",
            "--exit-code",
            "1",
            "--format",
            "json",
            "--output",
            "/repo/reports/security/trivy-licenses.json",
            "/repo/package-lock.json",
        ]
    )
    if arguments.images:
        for image in ("sanjiv-api:phase9", "sanjiv-web:phase9"):
            name = image.split(":", 1)[0].replace("-", "_")
            checks[f"trivy_{name}"] = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    "/var/run/docker.sock:/var/run/docker.sock",
                    "-v",
                    _docker_mount(root),
                    "-v",
                    "sanjiv-trivy-cache:/root/.cache/trivy",
                    "aquasec/trivy:latest",
                    "image",
                    "--no-progress",
                    "--scanners",
                    "vuln",
                    "--severity",
                    "MEDIUM,HIGH,CRITICAL",
                    "--ignore-unfixed",
                    "--exit-code",
                    "1",
                    "--format",
                    "json",
                    "--output",
                    f"/repo/reports/security/trivy-{name}.json",
                    image,
                ]
            )

    failures = {name: item for name, item in checks.items() if item["exit_code"] != 0}
    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "scope": "repository, dependencies, secrets, licenses, configuration, and optional images",
        "checks": checks,
        "status": "PASS" if not failures else "FAIL",
        "failure_names": sorted(failures),
        "notice": (
            "Scanner output is preserved under reports/security using repository-relative paths."
        ),
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
