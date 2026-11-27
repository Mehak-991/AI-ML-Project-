"""Run the API with `python main.py` (equivalent to `uvicorn app.main:app`).

Development (APP_ENV=development, the default): auto-reload on code changes, bound to
127.0.0.1 only. Any other APP_ENV runs without reload. In production prefer the Docker image
or an explicit `uvicorn app.main:app --host 0.0.0.0 --workers N --proxy-headers` command.

Options (environment variables): HOST (default 127.0.0.1), PORT (default 8000).
"""

import os
from pathlib import Path

import uvicorn

from app.core.config import get_settings

APP_DIR = Path(__file__).resolve().parent / "app"


def main() -> None:
    settings = get_settings()
    reload = settings.APP_ENV == "development"
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=reload,
        # Watch only application code: never .venv (pip installs would restart the server),
        # uploads/, trained_models/ or logs/.
        reload_dirs=[str(APP_DIR)] if reload else None,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
