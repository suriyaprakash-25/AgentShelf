from app import observability


def test_alert_allowlist_excludes_customer_provider_and_exception_data():
    dirty = {
        "message": "agentshelf:JOB_HANDLER_FAILED",
        "request": {"data": "buyer-address", "headers": {"Authorization": "secret"}},
        "user": {"email": "private@example.invalid"},
        "breadcrumbs": [{"message": "private prompt"}],
        "exception": {"values": [{"value": "secret"}]},
        "level": "error",
    }
    clean = observability.scrub(dirty, {})
    assert set(clean) == {"event_id", "timestamp", "level", "message", "environment"}
    assert "secret" not in str(clean) and "private" not in str(clean)
    assert observability.scrub({"message": "private provider error"}, {}) is None
