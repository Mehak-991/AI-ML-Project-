"""Run the API with `python main.py` (equivalent to `uvicorn app.main:app`).

Development (APP_ENV=development, the default): auto-reload on code changes, bound to
127.0.0.1 only. Any other APP_ENV runs without reload. In production prefer the Docker image
or an explicit `uvicorn app.main:app --host 0.0.0.0 --workers N --proxy-headers` command.

Options (environment variables): HOST (default 127.0.0.1), PORT (default 8000).
"""

import os

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=settings.APP_ENV == "development",
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
