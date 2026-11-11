"""Diagnose the configured database connection (reads DATABASE_URL from env/.env).

Usage: python scripts/check_db.py
Exit code 0 if connected, 1 otherwise. The password is never printed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect

from app.database.session import diagnose_database, get_engine


def main() -> int:
    result = diagnose_database()
    print(f"URL:       {result.url or '(not set)'}")
    print(f"Status:    {'OK' if result.ok else 'FAILED'} ({result.category})")
    print(f"Hint:      {result.hint}")
    if result.ok:
        print(f"Server:    {result.server_version}")
        print(f"Latency:   {result.latency_ms} ms")
        tables = inspect(get_engine()).get_table_names()
        print(f"Tables:    {', '.join(sorted(tables)) or '(none - run: alembic upgrade head)'}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
