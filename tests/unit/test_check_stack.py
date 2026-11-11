"""scripts/check_stack.py against simulated stacks: a healthy API, the web-app-answers-everything
trap, a dead proxy (the Vite dev 502), and a registration route that wrongly accepts input."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts import check_stack

HTML = b"<!doctype html><html><head><title>frontend</title></head><body></body></html>"
ERROR = {"error": {"code": "x", "message": "y"}}


def _make_handler(scenario: str, seen_posts: list):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence test output
            pass

        def _send(self, status, body=b"", content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload).encode())

        def do_GET(self):
            path = self.path
            if scenario == "spa_only":  # nginx SPA fallback answering for an API that is down
                return self._send(200, HTML, "text/html")
            if scenario == "dead_proxy":  # Vite dev proxy with nothing behind it
                return self._send(502)
            if path == "/api/v1/health":
                return self._json(200, {"status": "ok", "name": "x", "version": "0.5.0"})
            if path == "/api/v1/auth/me":
                return self._json(401, ERROR)
            if path == "/api/v1/auth/register":
                return self._json(405, ERROR)
            if path == "/health":
                return self._send(200, HTML, "text/html")  # web app, as on the bundled nginx
            return self._send(404, b"", "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            seen_posts.append((self.path, body))
            if scenario == "spa_only":
                return self._send(200, HTML, "text/html")
            if scenario == "dead_proxy":
                return self._send(502)
            if scenario == "accepts_anything":
                return self._json(201, {"id": "created"})
            if scenario == "rate_limited":
                return self._json(429, ERROR)
            if scenario == "no_route":
                return self._send(404, b"", "text/plain")
            return self._json(422, ERROR)

    return Handler


@pytest.fixture
def stack():
    servers = []

    def start(scenario: str):
        seen: list = []
        server = HTTPServer(("127.0.0.1", 0), _make_handler(scenario, seen))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}", seen

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _levels(origin: str) -> dict[str, str]:
    return {name: level for name, level, _ in check_stack.run(origin, timeout=5)}


def test_healthy_stack_passes_and_the_bare_health_html_is_only_a_warning(stack, capsys) -> None:
    origin, _seen = stack("healthy")
    assert check_stack.main(["--origin", origin]) == 0
    levels = _levels(origin)
    assert levels["GET /api/v1/health"] == "PASS"
    assert levels["GET /api/v1/auth/me"] == "PASS"
    assert levels["GET /api/v1/auth/register"] == "PASS"
    assert levels["POST /api/v1/auth/register (invalid body)"] == "PASS"
    assert levels["GET /health (informational)"] == "WARN"  # HTML is flagged, never counted as healthy
    assert "PASSED" in capsys.readouterr().out


def test_registration_check_only_ever_sends_an_invalid_body(stack) -> None:
    origin, seen = stack("healthy")
    check_stack.run(origin, timeout=5)
    assert seen, "the registration POST must actually be sent"
    for path, body in seen:
        assert path == "/api/v1/auth/register"
        assert body == check_stack.INVALID_REGISTRATION
        assert "@" not in body["email"], "the email must be malformed so no account can be created"


def test_html_answering_every_path_is_not_mistaken_for_a_healthy_api(stack, capsys) -> None:
    origin, _ = stack("spa_only")
    assert check_stack.main(["--origin", origin]) == 1
    levels = _levels(origin)
    assert levels["GET /api/v1/health"] == "FAIL"
    assert levels["GET /api/v1/auth/me"] == "FAIL"
    assert levels["POST /api/v1/auth/register (invalid body)"] == "FAIL"
    assert "HTML, not the API" in capsys.readouterr().out


def test_bare_health_html_never_counts_as_api_health() -> None:
    page = check_stack.Response(200, "text/html; charset=utf-8", HTML)
    assert check_stack.is_api_health(page) is False
    assert check_stack.check_health(page)[0] == "FAIL"
    mislabelled = check_stack.Response(200, "application/json", HTML)  # JSON header, HTML body
    assert check_stack.is_api_health(mislabelled) is False
    real = check_stack.Response(200, "application/json", b'{"status":"ok","version":"0.5.0"}')
    assert check_stack.is_api_health(real) is True
    degraded = check_stack.Response(200, "application/json", b'{"status":"unavailable","version":"0.5.0"}')
    assert check_stack.is_api_health(degraded) is False


def test_dead_proxy_502_is_reported_with_the_dev_server_hint(stack, capsys) -> None:
    origin, _ = stack("dead_proxy")
    assert check_stack.main(["--origin", origin]) == 1
    output = capsys.readouterr().out
    assert "HTTP 502" in output and "VITE_DEV_API_TARGET" in output


def test_registration_route_missing_is_a_failure(stack) -> None:
    origin, _ = stack("no_route")
    assert _levels(origin)["POST /api/v1/auth/register (invalid body)"] == "FAIL"


def test_accepting_an_invalid_registration_is_a_failure(stack) -> None:
    origin, _ = stack("accepts_anything")
    levels = _levels(origin)
    assert levels["POST /api/v1/auth/register (invalid body)"] == "FAIL"
    assert check_stack.main(["--origin", origin]) == 1


def test_rate_limited_registration_is_a_warning_not_a_failure(stack) -> None:
    origin, _ = stack("rate_limited")
    assert _levels(origin)["POST /api/v1/auth/register (invalid body)"] == "WARN"
    assert check_stack.main(["--origin", origin]) == 0


def test_unreachable_origin_fails_cleanly(capsys) -> None:
    assert check_stack.main(["--origin", "http://127.0.0.1:9", "--timeout", "1"]) == 1
    assert "cannot connect" in capsys.readouterr().out
