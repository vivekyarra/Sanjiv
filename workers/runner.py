from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

WorkerMode = Literal["ingestion", "refresh", "compute"]


def _heartbeat(path: Path, mode: WorkerMode) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "service": "sanjiv-worker",
        "mode": mode,
        "pid": os.getpid(),
        "heartbeat_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "HEALTHY",
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


async def run(mode: WorkerMode, runtime_dir: Path, *, once: bool) -> None:
    target = runtime_dir / f"{mode}.json"
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(event, stopped.set)
    while not stopped.is_set():
        _heartbeat(target, mode)
        print(
            json.dumps(
                {
                    "event": "worker_heartbeat",
                    "mode": mode,
                    "status": "HEALTHY",
                    "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        if once:
            return
        try:
            await asyncio.wait_for(stopped.wait(), timeout=10.0)
        except TimeoutError:
            continue


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded Sanjiv worker role.")
    parser.add_argument("mode", choices=("ingestion", "refresh", "compute"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("data/runtime/workers"))
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(run(arguments.mode, arguments.runtime_dir, once=arguments.once))


if __name__ == "__main__":
    main()
