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
# Workers share nothing in-process that correctness depends on (quotas, jobs and MCP are
# stateless or in Postgres), so WEB_CONCURRENCY scales a container and a load balancer
# scales across containers. Only the listed proxy addresses may rewrite client info;
# quota identity is taken from the trusted rightmost X-Forwarded-For hop in the app.
ENV WEB_CONCURRENCY=2 FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS}\" --timeout-keep-alive 5"]
