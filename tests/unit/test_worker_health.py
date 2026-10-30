"""Tests for worker heartbeat health check logic and failure scenarios."""

import time
from pathlib import Path
import pytest

from scripts.check_worker_health import check_worker_health


def test_worker_health_healthy(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "worker_heartbeat"
    # Write current timestamp
    heartbeat_file.write_text(str(time.time()), encoding="utf-8")

    healthy, msg = check_worker_health(heartbeat_file, max_age_seconds=30.0)
    assert healthy is True
    assert "Worker healthy" in msg


def test_worker_health_missing_file(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "non_existent_heartbeat"
    healthy, msg = check_worker_health(heartbeat_file, max_age_seconds=30.0)
    assert healthy is False
    assert "not found" in msg


def test_worker_health_stale_heartbeat(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "worker_heartbeat"
    # Write timestamp 60 seconds ago
    stale_time = time.time() - 60.0
    heartbeat_file.write_text(str(stale_time), encoding="utf-8")

    healthy, msg = check_worker_health(heartbeat_file, max_age_seconds=30.0)
    assert healthy is False
    assert "stale" in msg


def test_worker_health_invalid_content(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "worker_heartbeat"
    heartbeat_file.write_text("corrupted_content", encoding="utf-8")

    healthy, msg = check_worker_health(heartbeat_file, max_age_seconds=30.0)
    assert healthy is False
    assert "Failed to read or parse" in msg


def test_worker_health_clock_skew_tolerance(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "worker_heartbeat"
    # Timestamp slightly into the future (2s)
    future_time = time.time() + 2.0
    heartbeat_file.write_text(str(future_time), encoding="utf-8")

    healthy, msg = check_worker_health(heartbeat_file, max_age_seconds=30.0)
    assert healthy is True
    assert "Worker healthy" in msg

    # Timestamp far into the future (20s)
    heartbeat_file.write_text(str(time.time() + 20.0), encoding="utf-8")
    healthy, msg = check_worker_health(heartbeat_file, max_age_seconds=30.0)
    assert healthy is False
    assert "future" in msg
