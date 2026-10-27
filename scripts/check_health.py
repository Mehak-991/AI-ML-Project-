"""Smoke-check a running server's health endpoints.

Usage: python scripts/check_health.py [base_url]   (default http://127.0.0.1:8000)
"""

import json
import sys
import urllib.error
import urllib.request

PATHS = ("/", "/health", "/api/v1/health")


def main() -> int:
    base_url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
    failed = False
    for path in PATHS:
        try:
            with urllib.request.urlopen(base_url + path, timeout=5) as response:
                status, body = response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read().decode(errors="replace")
        except OSError as exc:
            status, body = None, str(exc)
        failed |= status != 200
        print(f"{path:<16} {status}  {body}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
