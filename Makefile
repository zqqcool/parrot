.PHONY: api-generate backend-dev backend-serve backend-taskiq check compose-up compose-workers deps-down deps-up

check:
	./scripts/check.sh

api-generate:
	backend/.venv/bin/python scripts/generate_openapi.py --config backend/config/dev.toml
	npm --prefix frontend run generate:api

backend-serve:
	backend/.venv/bin/parrot serve --config backend/config/dev.toml

backend-dev:
	cd backend && .venv/bin/watchfiles --target-type command '.venv/bin/parrot serve --config config/dev.toml' app config

backend-taskiq:
	docker compose --profile workers up -d taskiq-worker taskiq-scheduler

deps-up:
	docker compose up -d postgres redis

deps-down:
	docker compose down

compose-up:
	docker compose up -d --build

compose-workers:
	docker compose --profile workers up -d
