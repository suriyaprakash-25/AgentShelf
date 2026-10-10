"""Explicit local operator management and guarded backup/restore commands."""

import argparse
import os
import subprocess
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.engine import make_url

from app import orders
from app.config import get_settings
from app.db import session_factory
from app.models import (
    AgentSession,
    LoginChallenge,
    OpsAudit,
    Order,
    Product,
    RateBucket,
    Seller,
    SellerSession,
    utcnow,
)


def pg_environment(database_url):
    url = make_url(database_url)
    environment = os.environ.copy()
    environment.update(
        PGHOST=url.host or "localhost",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database or "",
        PGCONNECT_TIMEOUT="10",
    )
    return environment


def backup(executable, path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise ValueError("Choose a new backup filename; existing backups are never overwritten.")
    subprocess.run(
        [executable, "--format=custom", "--no-owner", "--no-acl", "--file", str(path)],
        env=pg_environment(get_settings().database_url),
        check=True,
        timeout=300,
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def restore(executable, path, target):
    url = make_url(target)
    if (
        get_settings().paypal_mode != "sandbox"
        or get_settings().app_env not in {"local", "test"}
        or not url.database
        or not url.database.endswith("_restore_test")
        or url.host not in {"localhost", "127.0.0.1"}
    ):
        raise ValueError(
            "Restore requires a local sandbox and a loopback database ending _restore_test."
        )
    subprocess.run(
        [
            executable,
            "--dbname",
            url.database,
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            str(Path(path).resolve()),
        ],
        env=pg_environment(target),
        check=True,
        timeout=300,
    )


def grant_operator(address, revoke=False):
    with session_factory() as db, db.begin():
        seller = db.scalar(select(Seller).where(Seller.email == address.lower()).with_for_update())
        if not seller or seller.status != "active":
            raise ValueError("Verify an active seller account before granting an operator role.")
        seller.is_operator = not revoke
        db.add(
            OpsAudit(
                actor_id=seller.id,
                action="operator_revoke" if revoke else "operator_grant",
                resource_id=str(seller.id),
            )
        )


def demo_reset(confirm):
    settings = get_settings()
    if (
        settings.paypal_mode != "sandbox"
        or settings.app_env == "production"
        or confirm != "RESET_SYNTHETIC_SANDBOX_STOCK"
    ):
        raise ValueError("Demo reset requires sandbox and the exact confirmation phrase.")
    source = Path(__file__).resolve().parents[1] / "seed" / "demo_store.json"
    import json

    data = json.loads(source.read_text(encoding="utf-8"))
    with session_factory() as db, db.begin():
        seller = db.scalar(
            select(Seller).where(Seller.store_slug == data["store"]["store_slug"]).with_for_update()
        )
        if (
            not seller
            or seller.name != data["store"]["name"]
            or seller.paypal_email != data["store"]["paypal_email"]
        ):
            raise ValueError("Only the unchanged synthetic demo seller may be reset.")
        products = list(
            db.scalars(
                select(Product)
                .where(Product.seller_id == seller.id)
                .order_by(Product.id)
                .with_for_update()
            )
        )
        if db.scalar(
            select(Order.id)
            .where(Order.seller_id == seller.id, Order.status.in_(orders.RESERVED_STATES))
            .limit(1)
        ):
            raise ValueError("Reconcile outstanding demo reservations before resetting stock.")
        for number, initial in enumerate(data["products"], 1):
            product = next((p for p in products if p.short_no == number), None)
            if not product or product.title != initial["title"]:
                raise ValueError("The demo catalog changed; review it before resetting.")
            product.stock = initial["stock"]
        # All historical orders, payment events, captures and webhooks are preserved.
        db.add(OpsAudit(actor_id=seller.id, action="demo_stock_reset", resource_id=str(seller.id)))


def cleanup_expired():
    with session_factory() as db, db.begin():
        now = utcnow()
        db.execute(delete(LoginChallenge).where(LoginChallenge.expires_at <= now))
        db.execute(delete(SellerSession).where(SellerSession.expires_at <= now))
        db.execute(delete(RateBucket).where(RateBucket.expires_at <= now - timedelta(days=1)))
        db.execute(
            update(AgentSession)
            .where(AgentSession.created_at <= now - timedelta(days=30))
            .values(chat_history=[])
        )


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    role = actions.add_parser("operator")
    role.add_argument("email")
    role.add_argument("--revoke", action="store_true")
    dump = actions.add_parser("backup")
    dump.add_argument("path")
    dump.add_argument("--pg-dump", default="pg_dump")
    drill = actions.add_parser("restore-drill")
    drill.add_argument("path")
    drill.add_argument("--target-env", default="RESTORE_DATABASE_URL")
    drill.add_argument("--pg-restore", default="pg_restore")
    reset = actions.add_parser("demo-reset")
    reset.add_argument("--confirm", required=True)
    actions.add_parser("cleanup-expired")
    args = parser.parse_args()
    if args.action == "operator":
        grant_operator(args.email, args.revoke)
    elif args.action == "backup":
        backup(args.pg_dump, args.path)
    elif args.action == "restore-drill":
        restore(args.pg_restore, args.path, os.environ[args.target_env])
    elif args.action == "demo-reset":
        demo_reset(args.confirm)
    else:
        cleanup_expired()
    print("Maintenance command completed. Record sanitized verification evidence separately.")


if __name__ == "__main__":
    main()
