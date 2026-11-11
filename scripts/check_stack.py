"""Smoke-test a running stack through its public (frontend) origin.

Usage:
    python scripts/check_stack.py [--origin http://localhost] [--timeout 10]

Checks (exit code 1 on any FAIL; WARN does not fail):
  * GET  /api/v1/health          200, a JSON content type, and {"status": "ok", ...}.
  * GET  /api/v1/auth/me         401 with the API's JSON error envelope (unauthenticated).
  * GET  /api/v1/auth/register   405: the route exists and accepts only POST.
  * POST /api/v1/auth/register   422 for a deliberately INVALID body. A validation error proves the
                                 route accepts POST and is reachable; because the body is invalid,
                                 no account is ever created. Any 2xx is reported as a FAIL.
  * GET  /health                 Informational. On the bundled nginx this is the web app's HTML
                                 (a 200 that is NOT an API health check) and is never counted as one.

Only the endpoints above are called; no credentials are sent or printed.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# Invalid on purpose: the email is malformed, so request validation rejects it (422) before any
# database work, whichever role or settings the deployment uses.
INVALID_REGISTRATION = {"email": "not-an-email", "password": "x", "full_name": "stack check"}


@dataclass
class Response:
    status: int  # 0 when the connection itself failed
    content_type: str
    body: bytes
    error: str = ""

    def json(self) -> object | None:
        if "json" not in self.content_type.lower():
            return None
        try:
            return json.loads(self.body or b"null")
        except ValueError:
            return None

    @property
    def looks_like_html(self) -> bool:
        head = self.body[:200].lstrip().lower()
        return "html" in self.content_type.lower() or head.startswith((b"<!doctype html", b"<html"))


def fetch(origin: str, method: str, path: str, body: object | None = None, timeout: float = 10) -> Response:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(origin.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return Response(reply.status, reply.headers.get("Content-Type", ""), reply.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", exc.read())
    except (urllib.error.URLError, OSError) as exc:
        return Response(0, "", b"", error=type(exc).__name__)


def _hint(reply: Response) -> str:
    if reply.status == 0:
        return f"cannot connect ({reply.error})"
    if reply.status in (502, 503, 504):
        return (
            f"HTTP {reply.status}: the proxy cannot reach the API. If this origin is the Vite dev "
            "server, nothing is listening on its proxy target (set VITE_DEV_API_TARGET)"
        )
    if reply.looks_like_html:
        return f"HTTP {reply.status} but HTML, not the API: the web app answered instead of the API"
    return f"HTTP {reply.status}"


def is_api_health(reply: Response) -> bool:
    """True only for the API's own health JSON; a 200 HTML page (the web app) never qualifies."""
    payload = reply.json()
    return reply.status == 200 and isinstance(payload, dict) and payload.get("status") == "ok" and "version" in payload


def check_health(reply: Response) -> tuple[str, str]:
    if is_api_health(reply):
        return "PASS", "JSON 200 with status ok"
    return "FAIL", _hint(reply)


def check_unauthenticated_me(reply: Response) -> tuple[str, str]:
    payload = reply.json()
    if reply.status == 401 and isinstance(payload, dict) and "error" in payload:
        return "PASS", "401 with the JSON error envelope"
    return "FAIL", _hint(reply)


def check_register_requires_post(reply: Response) -> tuple[str, str]:
    payload = reply.json()
    if reply.status == 405 and isinstance(payload, dict) and "error" in payload:
        return "PASS", "405: route exists, POST only"
    return "FAIL", _hint(reply)


def check_register_accepts_post(reply: Response) -> tuple[str, str]:
    payload = reply.json()
    if reply.status == 422 and isinstance(payload, dict) and "error" in payload:
        return "PASS", "POST reached the route and the invalid body was rejected (422); nothing created"
    if reply.status == 429:
        return "WARN", "rate limited (429); the route answered, but validation was not exercised"
    if 200 <= reply.status < 300:
        return "FAIL", f"HTTP {reply.status}: an invalid body was ACCEPTED; an account may have been created"
    return "FAIL", _hint(reply)


def check_bare_health(reply: Response) -> tuple[str, str]:
    """Informational only: whatever /health answers, it is never counted as the API's health."""
    if is_api_health(reply):
        return "INFO", "the API answers on /health too"
    if reply.looks_like_html:
        return "WARN", "returns the web app's HTML: not an API health check, ignored (use /api/v1/health)"
    return "INFO", f"{_hint(reply)}; ignored (use /api/v1/health)"


def run(origin: str, timeout: float = 10) -> list[tuple[str, str, str]]:
    return [
        ("GET /api/v1/health", *check_health(fetch(origin, "GET", "/api/v1/health", timeout=timeout))),
        ("GET /api/v1/auth/me", *check_unauthenticated_me(fetch(origin, "GET", "/api/v1/auth/me", timeout=timeout))),
        (
            "GET /api/v1/auth/register",
            *check_register_requires_post(fetch(origin, "GET", "/api/v1/auth/register", timeout=timeout)),
        ),
        (
            "POST /api/v1/auth/register (invalid body)",
            *check_register_accepts_post(
                fetch(origin, "POST", "/api/v1/auth/register", INVALID_REGISTRATION, timeout=timeout)
            ),
        ),
        ("GET /health (informational)", *check_bare_health(fetch(origin, "GET", "/health", timeout=timeout))),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origin", default="http://localhost", help="Public origin of the stack")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)

    results = run(args.origin, args.timeout)
    for name, level, detail in results:
        print(f"[stack] {level:<4} {name}: {detail}")
    failures = sum(1 for _, level, _ in results if level == "FAIL")
    print(f"[stack] {'FAILED' if failures else 'PASSED'} against {args.origin} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
