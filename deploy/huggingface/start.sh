#!/bin/sh
# One Space container runs migrations, the demo seed, the job worker and the API.
set -e
cd /app/backend

alembic upgrade head

# Idempotent and sandbox-only; DEMO_SELLER_PAYPAL_EMAIL makes the demo store payable.
python seed.py || echo "demo seed skipped"

# The worker restarts on exit so a transient database error never stops alerts.
(
  while true; do
    python worker.py || true
    echo "worker exited; restarting in 5 seconds"
    sleep 5
  done
) &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" \
  --workers "${WEB_CONCURRENCY:-2}" --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" --timeout-keep-alive 5
