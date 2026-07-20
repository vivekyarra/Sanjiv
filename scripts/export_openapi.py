import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from sanjiv.main import app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    schema = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    args.output.write_text(schema, encoding="utf-8")


if __name__ == "__main__":
    main()
