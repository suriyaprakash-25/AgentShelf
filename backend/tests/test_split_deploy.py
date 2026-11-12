"""Browser origin on a proxy (Vercel rewrites) with the API on Render."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import mcp_transport

FRONT = "https://agentshelf.example.app"
RENDER_HOST = "agentshelf-api.example.onrender.com"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"},
    },
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def settings(**overrides):
    base = {
        "database_url": "postgresql+psycopg://u:p@127.0.0.1/db",
        "public_api_url": FRONT,
        "frontend_url": FRONT,
    }
    return Settings(_env_file=None, **{**base, **overrides})


def test_hosting_provider_database_urls_select_psycopg():
    for given in ("postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db"):
        assert settings(database_url=given).database_url == "postgresql+psycopg://u:p@h:5432/db"
    replica = settings(database_read_url="postgresql://r@h/db").database_read_url
    assert replica == "postgresql+psycopg://r@h/db"


def test_server_side_calls_go_straight_to_the_platform_host():
    assert settings().direct_api_url == FRONT
    assert settings(render_external_hostname=RENDER_HOST).direct_api_url == "https://" + RENDER_HOST


def mcp_status(cfg, host):
    _, app = mcp_transport(cfg)
    with TestClient(app, base_url=f"https://{host}") as client:  # runs the MCP lifespan
        return client.post("/mcp", json=INIT, headers=HEADERS).status_code


def test_mcp_accepts_proxied_and_direct_hosts_but_not_others():
    cfg = settings(render_external_hostname=RENDER_HOST)
    assert mcp_status(cfg, RENDER_HOST) == 200
    assert mcp_status(cfg, "agentshelf.example.app") == 200
    assert mcp_status(cfg, "evil.example.com") == 421
