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
from app.utils.logging import configure_logging

logger = logging.getLogger("worker")


def _make_signal_handler(heartbeat_path: Path):
    def signal_handler(signum, frame):
        logger.info("Received termination signal %s. Shutting down worker gracefully...", signum)
        try:
            heartbeat_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Could not unlink heartbeat file on shutdown: %s", exc)
        sys.exit(0)

    return signal_handler


def main():
    settings = load_settings()
    configure_logging("DEBUG" if settings.DEBUG else settings.LOG_LEVEL, settings.LOG_FORMAT)
    heartbeat_path = Path(settings.WORKER_HEARTBEAT_FILE)
    handler = _make_signal_handler(heartbeat_path)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    logger.info("Worker initialized with APP_ENV=%s", settings.APP_ENV)
    run_worker_loop(settings, heartbeat_file=str(heartbeat_path))


if __name__ == "__main__":
    main()
