"""Read-only HTTP smoke checks for the isolated local/CI deployment image."""

import gzip
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:18000"


def request(path, expected=200, data=None, headers=None):
    """Read a bounded local response and verify its HTTP status."""
    try:
        response = urllib.request.urlopen(
            urllib.request.Request(
                BASE + path,
                data=data,
                headers={"Content-Type": "application/json", **(headers or {})},
            ),
            timeout=5,
        )
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        assert response.status == expected, (
            f"Unexpected status for {path}: {response.status}"
        )
        content = response.read(2 * 1024 * 1024 + 1)
        assert len(content) <= 2 * 1024 * 1024, "Smoke response exceeds its bound"
        return content, response.headers


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
assert headers.get("Content-Security-Policy")
assert headers.get("X-Content-Type-Options") == "nosniff"
assert headers.get("Cache-Control") == "no-store"
asset = re.search(rb'src="(/assets/[^"<>]+\.js)"', content)
assert asset, "The frontend entry asset must be present"
content, headers = request(asset.group(1).decode(), headers={"Accept-Encoding": "gzip"})
assert headers.get("Content-Encoding") == "gzip"
assert gzip.decompress(content), "The compressed frontend asset must be usable"
assert headers.get("Cache-Control") == "public, max-age=31536000, immutable"
for path in ("/api/me", "/api/ops"):
    _, headers = request(path, 401)
    assert headers.get("Cache-Control") == "no-store"
request("/api/auth/request-link", 413, b"x" * 65537)
result = {
    "environment": "isolated synthetic sandbox",
    "database": "reachable",
    "catalog_products": 6,
    "frontend": "served",
    "security_headers": "present",
    "private_routes": "unauthorized and no-store",
    "oversized_json": "rejected",
    "asset_compression": "gzip round-trip verified",
    "asset_cache": "immutable",
    "provider_acceptance": "not tested",
}
Path("work").mkdir(exist_ok=True)
Path("work/container-smoke.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
