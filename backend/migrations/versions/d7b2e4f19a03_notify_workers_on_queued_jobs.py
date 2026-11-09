"""notify workers on queued jobs

A trigger signals idle workers through LISTEN/NOTIFY when a job becomes queued, so new
work starts immediately instead of waiting for the next poll. SQL is frozen here so
later model edits cannot change what this revision applied.

Revision ID: d7b2e4f19a03
Revises: c3a91d2e7f10
"""

from alembic import op

revision = "d7b2e4f19a03"
down_revision = "c3a91d2e7f10"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agentshelf_notify_job() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('agentshelf_jobs', NEW.kind);
            RETURN NULL;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER jobs_notify
        AFTER INSERT OR UPDATE OF status, run_after ON jobs
        FOR EACH ROW WHEN (NEW.status = 'queued')
        EXECUTE FUNCTION agentshelf_notify_job()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS jobs_notify ON jobs")
    op.execute("DROP FUNCTION IF EXISTS agentshelf_notify_job()")
