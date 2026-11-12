# Backend-only image for a Hugging Face Docker Space. The browser app is served by
# Vercel, which forwards /api, /mcp, /.well-known, /checkout and /webhooks here.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.9.26
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY seed/ /app/seed/
COPY start.sh /app/start.sh
# Spaces run containers as uid 1000.
RUN useradd --create-home --uid 1000 user && chown -R user:user /app
USER user
ENV PATH="/app/backend/.venv/bin:$PATH" PORT=7860 WEB_CONCURRENCY=2 FORWARDED_ALLOW_IPS=127.0.0.1 \
    SERVE_FRONTEND=false
EXPOSE 7860
CMD ["sh", "/app/start.sh"]
