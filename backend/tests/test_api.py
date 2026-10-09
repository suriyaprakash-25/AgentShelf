import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_request_validation_does_not_echo_inputs():
    with TestClient(create_app()) as client:
        response = client.post("/api/playground/sessions", json={"budget_minor": "private-input"})
        assert response.status_code == 422
        assert "private-input" not in response.text
        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.integration
def test_health_store_and_server_quote(db_clean):
    from seed import seed

    seed()
    seed()
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        store = client.get("/api/stores/meera-jaipur").json()
        assert len(store["products"]) == 6
        assert "paypal_email" not in str(store)
        session = client.post("/api/playground/sessions", json={"budget_minor": 6000}).json()
        result = client.post(
            "/api/quotes",
            json={
                "product_id": store["products"][0]["product_id"],
                "session_id": session["session_id"],
                "qty": 1,
                "ship_to_country": "GB",
            },
        )
        assert result.status_code == 201
        assert result.json()["currency"] == "USD"


def test_missing_paypal_credentials_is_explicit():
    import uuid

    with TestClient(create_app()) as client:
        result = client.post(
            "/api/checkouts", json={"quote_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4())}
        )
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "PAYPAL_NOT_CONFIGURED"
