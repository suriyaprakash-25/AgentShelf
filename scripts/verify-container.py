"""Read-only HTTP smoke checks for the isolated local/CI deployment image."""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:18000"


def request(path, expected=200, data=None):
    try:
        response = urllib.request.urlopen(urllib.request.Request(BASE+path, data=data, headers={"Content-Type": "application/json"}), timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    assert response.status == expected, f"Unexpected status for {path}: {response.status}"
    return response.read(), response.headers


for attempt in range(30):
    try:
        content, _ = request("/healthz")
        assert json.loads(content)["database"] == "reachable"
        break
    except (OSError, AssertionError):
        time.sleep(1)
else:
    raise RuntimeError("Container readiness timed out")
content, _ = request("/api/stores/meera-jaipur")
assert len(json.loads(content)["products"]) == 6
content, headers = request("/dashboard")
assert b'<div id="root">' in content
assert headers.get("Content-Security-Policy") and headers.get("X-Content-Type-Options") == "nosniff"
request("/api/me", 401)
request("/api/ops", 401)
request("/api/auth/request-link", 413, b"x" * 65537)
result = {"environment": "isolated synthetic sandbox", "database": "reachable", "catalog_products": 6, "frontend": "served", "security_headers": "present", "private_routes": "unauthorized", "oversized_json": "rejected", "provider_acceptance": "not tested"}
Path("work").mkdir(exist_ok=True)
Path("work/container-smoke.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
