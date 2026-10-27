"""Logging setup shared by the API, scripts and background jobs."""

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging to stdout. Safe to call more than once."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_aiproject", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._aiproject = True  # type: ignore[attr-defined]
        root.addHandler(handler)
