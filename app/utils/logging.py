"""Logging setup shared by the API, scripts and background jobs.

Every record carries the current request ID (if any). In JSON mode each line is
one JSON object, which log shippers (Loki, CloudWatch, ELK) ingest directly.
Never pass secrets or request/response bodies to the logger.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s"

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes every LogRecord has; anything else was passed via `extra=` and is emitted.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "request_id"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configure root logging to stdout. Safe to call more than once (reconfigures)."""
    root = logging.getLogger()
    root.setLevel(level)
    handler = next((h for h in root.handlers if getattr(h, "_aiproject", False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler._aiproject = True  # type: ignore[attr-defined]
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT))
