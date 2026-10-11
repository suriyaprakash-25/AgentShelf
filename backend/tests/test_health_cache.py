"""Uptime must read current database health, never a cached success or outage."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app import main


def test_healthy_response_checks_database_and_forbids_caching(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    with TestClient(main.create_app()) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["database"] == "reachable"
    execute = engine.connect.return_value.__enter__.return_value.execute
    execute.assert_called_once()
    assert str(execute.call_args.args[0]) == "SELECT 1"


def test_database_outage_response_forbids_caching_and_private_error(monkeypatch):
    engine = MagicMock()
    engine.connect.side_effect = SQLAlchemyError("private-database-password")
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    with TestClient(main.create_app()) as client:
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "unavailable", "database": "unreachable"}
    assert "private" not in response.text
