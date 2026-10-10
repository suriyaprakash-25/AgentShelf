FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
ARG VITE_AG_STUDIO_LICENSE_KEY
ENV VITE_AG_STUDIO_LICENSE_KEY=$VITE_AG_STUDIO_LICENSE_KEY
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.9.26
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY seed/ /app/seed/
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 agentshelf && chown -R agentshelf:agentshelf /app
USER agentshelf
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
