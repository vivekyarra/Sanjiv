from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path


def _verify_manifest(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload_name = manifest.get("payload") or manifest.get("data_file")
    if not isinstance(payload_name, str):
        raise RuntimeError(f"{path} has no payload reference")
    payload = path.parent / payload_name
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    if digest != manifest["checksum_sha256"]:
        raise RuntimeError(f"checksum mismatch: {path}")


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as response:  # nosec B310 - fixed local URLs.
        return response.status, response.read(4096).decode("utf-8", errors="replace")


def main() -> None:
    for manifest in (
        Path("data/replay/maritime-watch-v1/manifest.json"),
        Path("data/replay/risk-intelligence-v1/manifest.json"),
        Path("data/replay/energy-validation-v1/manifest.json"),
        Path("data/fixtures/lpg/manifest.json"),
    ):
        _verify_manifest(manifest)
    api_status, api_body = _get("http://localhost:8000/health/ready")
    web_status, web_body = _get("http://localhost:3000/historical-replay")
    if api_status != 200 or '"status":"ready"' not in api_body:
        raise RuntimeError("API is not ready")
    if web_status != 200 or "Historical Replay" not in web_body:
        raise RuntimeError("Web application is not ready")
    print("PREFLIGHT_PASS classification=SYNTHETIC_FIXTURE external_credentials=none")


if __name__ == "__main__":
    main()
