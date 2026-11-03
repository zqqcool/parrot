#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT/scripts/quality/check_secrets.py"
python3 "$ROOT/scripts/quality/check_file_size.py"

node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major !== 20 || minor < 9) { console.error("Node.js >=20.9 <21 is required"); process.exit(1); }'

if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  echo "backend/.venv is missing; create it with Python 3.13 and sync backend dependencies" >&2
  exit 1
fi

(cd "$ROOT/backend" && .venv/bin/ruff format --check app alembic tests)
(cd "$ROOT/backend" && .venv/bin/ruff check app alembic tests)
"$ROOT/backend/.venv/bin/ruff" format --check --config "$ROOT/backend/pyproject.toml" "$ROOT/scripts"
"$ROOT/backend/.venv/bin/ruff" check --config "$ROOT/backend/pyproject.toml" "$ROOT/scripts"
"$ROOT/backend/.venv/bin/pyright" --project "$ROOT/backend/pyproject.toml"
"$ROOT/backend/.venv/bin/lint-imports" --config "$ROOT/backend/pyproject.toml"
"$ROOT/backend/.venv/bin/alembic" -c "$ROOT/backend/alembic.ini" heads
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/check_openapi.py" --config "$ROOT/backend/config/dev.toml"
(cd "$ROOT/backend" && .venv/bin/pytest tests --cov=app --cov-report=term-missing --cov-report=json:coverage.json --cov-fail-under=0)
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/quality/check_backend_coverage.py" "$ROOT/backend/coverage.json"

npm --prefix "$ROOT/frontend" run check
