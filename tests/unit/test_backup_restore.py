"""Unit tests for backup and restore utilities (scripts/backup_db.py and scripts/restore_db.py)."""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.backup_db import calculate_sha256, rotate_backups, run_backup
from scripts.restore_db import restore_backup, verify_checksum


def test_calculate_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "sample.txt"
    test_file.write_bytes(b"hello world production backup test")
    expected = hashlib.sha256(b"hello world production backup test").hexdigest()
    assert calculate_sha256(test_file) == expected


def test_verify_checksum_success(tmp_path: Path) -> None:
    data = b"compressed sql dump content"
    backup_file = tmp_path / "db_backup_test.sql.gz"
    backup_file.write_bytes(data)

    sha = hashlib.sha256(data).hexdigest()
    sha_file = tmp_path / "db_backup_test.sql.gz.sha256"
    sha_file.write_text(f"{sha}  db_backup_test.sql.gz\n", encoding="utf-8")

    assert verify_checksum(backup_file) is True


def test_verify_checksum_missing_file(tmp_path: Path) -> None:
    backup_file = tmp_path / "db_backup_test.sql.gz"
    backup_file.write_bytes(b"data")
    assert verify_checksum(backup_file) is False


def test_verify_checksum_mismatch(tmp_path: Path) -> None:
    backup_file = tmp_path / "db_backup_test.sql.gz"
    backup_file.write_bytes(b"actual data")

    sha_file = tmp_path / "db_backup_test.sql.gz.sha256"
    sha_file.write_text("0" * 64 + "  db_backup_test.sql.gz\n", encoding="utf-8")

    assert verify_checksum(backup_file) is False


def test_rotate_backups_preserves_single_backup(tmp_path: Path) -> None:
    single = tmp_path / "db_backup_aiproject_1.sql.gz"
    single.write_bytes(b"content")
    rotate_backups(tmp_path, retention_count=0)
    assert single.exists()


def test_rotate_backups_removes_oldest(tmp_path: Path) -> None:
    files = []
    for i in range(5):
        f = tmp_path / f"db_backup_aiproject_{i}.sql.gz"
        f.write_bytes(b"backup" + str(i).encode())
        sha = tmp_path / f"db_backup_aiproject_{i}.sql.gz.sha256"
        sha.write_text("dummy sha")
        meta = tmp_path / f"db_backup_aiproject_{i}.sql.gz.meta.json"
        meta.write_text("{}")
        files.append(f)
        time.sleep(0.01)

    rotate_backups(tmp_path, retention_count=3)
    remaining = sorted(tmp_path.glob("db_backup_*.sql.gz"))
    assert len(remaining) == 3
    assert files[0] not in remaining
    assert files[1] not in remaining
    assert files[4] in remaining
    assert not (tmp_path / "db_backup_aiproject_0.sql.gz.sha256").exists()


def test_restore_backup_requires_confirm(tmp_path: Path) -> None:
    backup_file = tmp_path / "db_backup_test.sql.gz"
    backup_file.write_bytes(b"test")
    sha_file = tmp_path / "db_backup_test.sql.gz.sha256"
    sha = hashlib.sha256(b"test").hexdigest()
    sha_file.write_text(f"{sha}  db_backup_test.sql.gz\n")

    with pytest.raises(PermissionError, match="requires --confirm flag"):
        restore_backup(backup_file, target_db="test_db", confirm=False)


def test_restore_backup_protects_production_target(tmp_path: Path) -> None:
    backup_file = tmp_path / "db_backup_test.sql.gz"
    backup_file.write_bytes(b"test")
    sha_file = tmp_path / "db_backup_test.sql.gz.sha256"
    sha = hashlib.sha256(b"test").hexdigest()
    sha_file.write_text(f"{sha}  db_backup_test.sql.gz\n")

    with pytest.raises(PermissionError, match="protected target"):
        restore_backup(backup_file, target_db="aiproject", confirm=False)


def test_run_backup_mocked_execution(tmp_path: Path) -> None:
    mock_proc = MagicMock()
    mock_proc.stdout.read.side_effect = [b"SELECT 1;\n", b""]
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    with patch("subprocess.Popen", return_value=mock_proc):
        backup_file = run_backup(
            output_dir=tmp_path,
            retention_count=7,
            db_container="test-db",
            db_user="testuser",
            db_name="testdb",
        )

    assert backup_file.exists()
    assert backup_file.name.endswith(".sql.gz")
    assert (tmp_path / f"{backup_file.name}.sha256").exists()
    meta_path = tmp_path / f"{backup_file.name}.meta.json"
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["database"] == "testdb"
    assert meta["user"] == "testuser"

    # Check that the file was compressed properly with gzip
    with gzip.open(backup_file, "rb") as gz:
        content = gz.read()
    assert content == b"SELECT 1;\n"
