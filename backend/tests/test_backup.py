import os
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import maintenance
from app.config import get_settings
from tests.test_orders import fixture_data


@pytest.mark.integration
def test_real_dump_restore_preserves_catalog_and_budget(db_clean, monkeypatch, tmp_path):
    dump = os.environ.get("PG_DUMP") or shutil.which("pg_dump")
    restore = os.environ.get("PG_RESTORE") or shutil.which("pg_restore")
    if not dump or not restore or not Path(dump).is_file() or not Path(restore).is_file():
        if os.environ.get("CI"):
            pytest.fail(
                "CI requires matching PostgreSQL backup clients; the drill must not silently skip."
            )
        pytest.skip("Restore drill requires pg_dump and pg_restore matching server major version")
    fixture_data()
    source = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setattr(get_settings(), "database_url", source)
    monkeypatch.setattr(get_settings(), "app_env", "test")
    monkeypatch.setattr(get_settings(), "paypal_mode", "sandbox")
    backup = maintenance.backup(dump, tmp_path / "fixture.dump")
    name = "agentshelf_" + uuid.uuid4().hex[:12] + "_restore_test"
    target_url = make_url(source).set(database=name)
    admin = create_engine(make_url(source).set(database="postgres"), isolation_level="AUTOCOMMIT")
    target = None
    try:
        with admin.connect() as db:
            db.execute(text(f'CREATE DATABASE "{name}"'))
        maintenance.restore(restore, backup, target_url.render_as_string(hide_password=False))
        target = create_engine(target_url)
        with target.connect() as db:
            assert db.scalar(text("SELECT stock FROM products")) == 1
            assert db.scalar(text("SELECT budget_minor FROM agent_sessions")) == 6000
            assert db.scalar(text("SELECT total_minor FROM quotes")) == 5500
    finally:
        if target:
            target.dispose()
        # Only the exact random local drill DB created above is ever dropped.
        assert name.startswith("agentshelf_") and name.endswith("_restore_test")
        with admin.connect() as db:
            db.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def test_restore_rejects_live_remote_and_non_drill_targets(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "app_env", "test")
    monkeypatch.setattr(get_settings(), "paypal_mode", "sandbox")
    for target in [
        "postgresql+psycopg://fixture@remote.invalid/drill_restore_test",
        "postgresql+psycopg://fixture@127.0.0.1/agentshelf",
    ]:
        with pytest.raises(ValueError, match="local sandbox"):
            maintenance.restore("never-executed", tmp_path / "fixture.dump", target)
