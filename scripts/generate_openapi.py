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
    parser = argparse.ArgumentParser(description="Generate the canonical Parrot OpenAPI document")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=BACKEND / "openapi" / "openapi.json")
    args = parser.parse_args()

    schema = create_app(load_app_config(args.config)).openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schema, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
