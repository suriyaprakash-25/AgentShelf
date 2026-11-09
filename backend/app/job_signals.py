"""Push wake-ups for the durable job queue via Postgres LISTEN/NOTIFY.

The jobs table stays the source of truth (durable, retryable, SKIP LOCKED claims).
A trigger only *signals* that work may exist, at commit time, so idle workers block
on a socket instead of polling, and new jobs start within milliseconds. A lost
notification is harmless: workers still wake on a bounded timeout and poll.
"""

import logging

import psycopg

from app.models import JOB_CHANNEL as CHANNEL

logger = logging.getLogger("agentshelf")


def conninfo(sqlalchemy_url):
    """Convert a SQLAlchemy psycopg URL into a libpq connection string."""
    return sqlalchemy_url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


class JobListener:
    """A dedicated autocommit connection subscribed to the job channel."""

    def __init__(self, url, connect_timeout=5):
        self._conninfo = conninfo(url)
        self._connect_timeout = connect_timeout
        self._connection = None

    def _connect(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg.connect(
                self._conninfo, autocommit=True, connect_timeout=self._connect_timeout
            )
            self._connection.execute(f"LISTEN {CHANNEL}")
        return self._connection

    def wait(self, timeout):
        """Block up to ``timeout`` seconds; True when a job was signalled."""
        try:
            for _ in self._connect().notifies(timeout=timeout, stop_after=1):
                return True
            return False
        except psycopg.Error:
            # Fall back to timed polling; the next wait reconnects.
            logger.warning('{"event":"job_listener_reconnect"}')
            self.close()
            return False

    def close(self):
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None
