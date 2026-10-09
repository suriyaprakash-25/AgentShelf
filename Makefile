.PHONY: setup db migrate seed api worker web test
setup:
	cd backend && uv sync --frozen
	cd frontend && npm ci
db:
	docker compose up -d db
migrate:
	cd backend && uv run --env-file ../.env alembic upgrade head
seed:
	cd backend && uv run --env-file ../.env python seed.py
api:
	cd backend && uv run --env-file ../.env uvicorn app.main:app --host 127.0.0.1 --port 8000
worker:
	cd backend && uv run --env-file ../.env python worker.py
web:
	cd frontend && npm run dev
test:
	cd backend && uv run --env-file ../.env pytest
