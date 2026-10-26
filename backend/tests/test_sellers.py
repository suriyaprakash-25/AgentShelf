import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import auth, email, paypal
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.main import create_app
from app.models import LoginChallenge, Order, SellerSession, utcnow

pytestmark = pytest.mark.integration
ORIGIN = {"origin": "http://localhost:5173"}
PROFILE = {"name": "New shop", "country": "IN", "paypal_email": "payee@example.invalid"}


@pytest.fixture
def delivery(monkeypatch):
    sent = []
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda recipient, link, key: sent.append(link))
    monkeypatch.setattr(get_settings(), "app_env", "test")
    return sent


def login(client, delivery, address="owner@example.invalid"):
    response = client.post(
        "/api/onboarding", headers=ORIGIN, json={**PROFILE, "email": address, "consent": True}
    )
    assert response.status_code == 202
    token = delivery[-1].split("#sign-in=")[1]
    assert token not in response.text
    reply = client.post("/api/auth/redeem", headers=ORIGIN, json={"token": token})
    assert reply.status_code == 200
    cookie = reply.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    me = client.get("/api/me")
    assert me.headers["cache-control"] == "no-store"
    return me.json(), {**ORIGIN, "x-csrf-token": me.json()["csrf_token"]}, token


def test_onboard_single_use_logout_and_hashed_capabilities(db_clean, delivery):
    with TestClient(create_app(), base_url="https://testserver") as client:
        me, headers, token = login(client, delivery)
        assert me["live_eligible"] is False
        assert (
            client.post("/api/auth/redeem", headers=ORIGIN, json={"token": token}).status_code
            == 401
        )
        with session_factory() as db:
            challenge = db.get(LoginChallenge, auth.digest(token))
            assert challenge.consumed_at is not None
            assert db.scalar(select(SellerSession)).token_hash != client.cookies[auth.COOKIE]
        assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 403
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/me").status_code == 401


def test_expired_link_and_session_are_refused(db_clean, delivery):
    auth.request_link("owner@example.invalid", PROFILE, "fixture-ip")
    token = delivery[-1].split("#sign-in=")[1]
    with session_factory() as db, db.begin():
        db.get(LoginChallenge, auth.digest(token)).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(DomainError, match="expired"):
        auth.redeem(token)
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client, delivery)
        with session_factory() as db, db.begin():
            db.get(SellerSession, auth.digest(client.cookies[auth.COOKIE])).expires_at = (
                utcnow() - timedelta(seconds=1)
            )
        assert client.get("/api/me").status_code == 401


def test_concurrent_redemption_has_exactly_one_winner(db_clean, delivery):
    auth.request_link("owner@example.invalid", PROFILE, "fixture-ip")
    token = delivery[-1].split("#sign-in=")[1]

    def redeem(_):
        try:
            return auth.redeem(token)
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(redeem, range(8)))
    assert results.count("LINK_INVALID") == 7
    with session_factory() as db:
        assert len(list(db.scalars(select(SellerSession)))) == 1


def test_shared_email_quota_enforced_across_requests(db_clean, delivery):
    with TestClient(create_app(), base_url="https://testserver") as client:
        for _ in range(3):
            assert (
                client.post(
                    "/api/auth/request-link",
                    headers=ORIGIN,
                    json={"email": "owner@example.invalid"},
                ).status_code
                == 202
            )
        assert (
            client.post(
                "/api/auth/request-link", headers=ORIGIN, json={"email": "owner@example.invalid"}
            ).status_code
            == 429
        )
        assert len(delivery) == 3


def test_catalog_confirm_csrf_and_cross_seller_ownership(db_clean, delivery, provider, monkeypatch):
    with (
        TestClient(create_app(), base_url="https://testserver") as owner,
        TestClient(create_app(), base_url="https://testserver") as outsider,
    ):
        me, headers, _ = login(owner, delivery)
        _, other_headers, _ = login(outsider, delivery, "other@example.invalid")
        body = {"title": "Scarf", "description": "Blue scarf", "price_minor": 4500, "stock": 2}
        assert owner.post("/api/me/products", headers=ORIGIN, json=body).status_code == 403
        created = owner.post("/api/me/products", headers=headers, json=body)
        assert created.status_code == 201
        product = created.json()
        assert product["status"] == "draft"
        path = "/api/me/products/" + product["id"]
        assert (
            owner.post(path + "/publish", headers=headers, json={"confirm": False}).status_code
            == 400
        )
        assert (
            owner.post(path + "/publish", headers=headers, json={"confirm": True}).json()["status"]
            == "live"
        )
        assert outsider.get("/api/me/products").json()["items"] == []
        assert (
            outsider.patch(path, headers=other_headers, json={"price_minor": 1}).status_code == 404
        )
        assert (
            outsider.post(
                path + "/publish", headers=other_headers, json={"confirm": True}
            ).status_code
            == 404
        )
        assert outsider.post(path + "/archive", headers=other_headers).status_code == 404
        assert owner.patch(path, headers=headers, json={"stock": -1}).status_code == 422
        assert owner.patch(path, headers=headers, json={"price_minor": None}).status_code == 400
        assert owner.patch(path, headers=headers, json={"stock": 0}).json()["stock"] == 0
        assert owner.get("/api/me/products?page_size=101").status_code == 422
        buyer = owner.post("/api/playground/sessions", json={"budget_minor": 6000}).json()
        assert owner.patch(path, headers=headers, json={"stock": 1}).status_code == 200
        quote = owner.post(
            "/api/quotes",
            json={
                "product_id": product["id"],
                "session_id": buyer["session_id"],
                "qty": 1,
                "ship_to_country": "GB",
            },
        ).json()
        checkout = owner.post(
            "/api/checkouts",
            json={"quote_id": quote["quote_id"], "session_id": buyer["session_id"]},
        )
        assert checkout.status_code == 200
        order_path = "/api/me/orders/" + checkout.json()["order_id"]
        assert owner.get(order_path).json()["title"] == "Scarf"
        assert outsider.get(order_path).status_code == 404
        shipment = {"carrier": "DHL", "tracking_number": "12345"}
        assert (
            outsider.post(
                order_path + "/tracking", headers=other_headers, json=shipment
            ).status_code
            == 404
        )
        assert (
            owner.post(order_path + "/tracking", headers=ORIGIN, json=shipment).status_code == 403
        )
        assert (
            owner.post(order_path + "/tracking", headers=headers, json=shipment).status_code == 409
        )
        with session_factory() as db, db.begin():
            order = db.get(Order, uuid.UUID(checkout.json()["order_id"]))
            order.status, order.capture_id = "paid", "CAPTURE"
            provider_id = order.paypal_order_id
        monkeypatch.setattr(
            paypal,
            "request",
            lambda *args: {
                "id": provider_id,
                "purchase_units": [{"shipping": {"trackers": [{"id": "CAPTURE-12345"}]}}],
            },
        )
        assert (
            owner.post(order_path + "/tracking", headers=headers, json=shipment).json()["status"]
            == "shipped"
        )
        assert len(owner.get("/api/me/orders").json()["items"]) == 1
        assert outsider.get("/api/me/orders").json()["items"] == []
        assert owner.post(path + "/archive", headers=headers).json()["status"] == "archived"
        assert (
            owner.post(path + "/publish", headers=headers, json={"confirm": True}).status_code
            == 409
        )
        assert me["store_slug"].startswith("store-")


def test_untrusted_origin_cannot_request_or_redeem_links(db_clean, delivery):
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert (
            client.post(
                "/api/onboarding",
                headers={"origin": "https://evil.invalid"},
                json={**PROFILE, "email": "owner@example.invalid", "consent": True},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/auth/redeem",
                headers={"origin": "https://evil.invalid"},
                json={"token": uuid.uuid4().hex},
            ).status_code
            == 403
        )
        assert delivery == []


def test_forwarded_ip_isolated_per_client_in_deployed_proxy_mode(db_clean, delivery, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "staging")
    with TestClient(create_app(), base_url="https://testserver") as client:
        for i in range(4):
            res = client.post(
                "/api/auth/request-link",
                headers={**ORIGIN, "x-forwarded-for": f"203.0.113.{10 + i}, 10.0.0.1"},
                json={"email": f"seller{i}@example.invalid"},
            )
            assert res.status_code == 202
