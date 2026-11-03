from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import load_app_config  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the committed OpenAPI document")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=BACKEND / "openapi" / "openapi.json")
    args = parser.parse_args()

    expected = create_app(load_app_config(args.config)).openapi()
    actual = json.loads(args.schema.read_text(encoding="utf-8"))
    if actual != expected:
        raise SystemExit("OpenAPI is stale; run scripts/generate_openapi.py")


if __name__ == "__main__":
    main()
