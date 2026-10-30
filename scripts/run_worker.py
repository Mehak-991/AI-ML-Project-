"""Dedicated standalone background worker process for Phase 14/15.

Usage:
    python scripts/run_worker.py
"""

import logging
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_settings
from app.services.job_service import run_worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("worker")


HEARTBEAT_PATH = Path("/tmp/worker_heartbeat")


def signal_handler(signum, frame):
    logger.info("Received termination signal %s. Shutting down worker gracefully...", signum)
    try:
        if HEARTBEAT_PATH.exists():
            HEARTBEAT_PATH.unlink()
    except Exception as exc:
        logger.warning("Could not unlink heartbeat file on shutdown: %s", exc)
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    settings = load_settings()
    logger.info("Worker initialized with APP_ENV=%s", settings.APP_ENV)
    run_worker_loop(settings, heartbeat_file=str(HEARTBEAT_PATH))


if __name__ == "__main__":
    main()
