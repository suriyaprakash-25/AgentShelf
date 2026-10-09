"""Run the durable job worker separately from the API."""

import logging
import time

from app.jobs import run_one

logger = logging.getLogger("agentshelf")


def main():
    """Poll until interrupted; let unexpected failures surface for supervision."""
    while True:
        if not run_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
