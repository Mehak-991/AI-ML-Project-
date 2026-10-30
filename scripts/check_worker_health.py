"""CLI script to verify the health of the background worker via heartbeat timestamp.

Usage:
    python scripts/check_worker_health.py [--max-age-seconds 30] [--heartbeat-file /tmp/worker_heartbeat]

Exit codes:
    0: Worker is healthy (heartbeat file exists, contains valid timestamp, and age <= max_age_seconds)
    1: Worker is unhealthy or stale
"""

import argparse
import sys
import time
from pathlib import Path

DEFAULT_HEARTBEAT_FILE = "/tmp/worker_heartbeat"
DEFAULT_MAX_AGE_SECONDS = 30.0


def check_worker_health(heartbeat_path: Path, max_age_seconds: float) -> tuple[bool, str]:
    if not heartbeat_path.exists():
        return False, f"Heartbeat file not found at {heartbeat_path}"

    try:
        content = heartbeat_path.read_text(encoding="utf-8").strip()
        last_heartbeat = float(content)
    except Exception as exc:
        return False, f"Failed to read or parse heartbeat timestamp: {exc}"

    current_time = time.time()
    age = current_time - last_heartbeat

    if age < 0:
        # Clock skew / future timestamp tolerance of 5 seconds
        if abs(age) > 5.0:
            return False, f"Heartbeat timestamp is in the future by {abs(age):.1f}s"
        age = 0.0

    if age > max_age_seconds:
        return False, f"Worker heartbeat is stale ({age:.1f}s old, max allowed {max_age_seconds:.1f}s)"

    return True, f"Worker healthy (heartbeat age: {age:.1f}s)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check background worker health")
    parser.add_argument(
        "--heartbeat-file",
        type=Path,
        default=Path(DEFAULT_HEARTBEAT_FILE),
        help="Path to the worker heartbeat file",
    )
    parser.add_argument(
        "--max-age-seconds",
        type=float,
        default=DEFAULT_MAX_AGE_SECONDS,
        help="Maximum allowed age of heartbeat in seconds",
    )
    args = parser.parse_args()

    healthy, message = check_worker_health(args.heartbeat_file, args.max_age_seconds)
    if healthy:
        print(f"[worker-health] OK: {message}")
        sys.exit(0)
    else:
        print(f"[worker-health] UNHEALTHY: {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
