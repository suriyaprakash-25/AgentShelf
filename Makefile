.PHONY: setup db migrate seed demo-reset phase-b-preflight api worker web test
setup:
	cd backend && uv sync --frozen
	cd frontend && npm ci
db:
	docker compose up -d db
migrate:
	cd backend && uv run --env-file ../.env alembic upgrade head
seed:
	cd backend && uv run --env-file ../.env python seed.py
demo-reset:
	cd backend && uv run --env-file ../.env python seed.py
	cd backend && uv run --env-file ../.env python maintenance.py demo-reset --confirm RESET_SYNTHETIC_SANDBOX_STOCK
phase-b-preflight:
	cd backend && uv run --env-file ../.env python verify_phase_b.py preflight
api:
	cd backend && uv run --env-file ../.env uvicorn app.main:app --host 127.0.0.1 --port 8000
worker:
	cd backend && uv run --env-file ../.env python worker.py
web:
	cd frontend && npm run dev
test:
	cd backend && uv run --env-file ../.env pytest
