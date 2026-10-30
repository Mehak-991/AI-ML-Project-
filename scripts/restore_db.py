"""Safe PostgreSQL restore utility with SHA-256 validation, dry-run checks, and target isolation.

Safety constraints:
- NEVER restores to a production database unless explicit flags and target are specified.
- Verifies SHA-256 checksum against the `.sha256` sidecar before attempting restore.
- Requires `--confirm` flag to proceed with database modifications.
- Allows specifying a temporary or isolated target database for safe verification.

Usage:
    python scripts/restore_db.py --backup backups/db_backup_aiproject_20261031.sql.gz --target-db aiproject_restore_test --confirm
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("restore")


def verify_checksum(backup_path: Path, checksum_path: Path | None = None) -> bool:
    """Validate backup file SHA-256 against recorded checksum."""
    if checksum_path is None:
        checksum_path = backup_path.with_name(f"{backup_path.name}.sha256")

    if not checksum_path.exists():
        logger.error("Missing checksum file: %s", checksum_path)
        return False

    expected_line = checksum_path.read_text(encoding="utf-8").strip()
    expected_hash = expected_line.split()[0]

    hasher = hashlib.sha256()
    with open(backup_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest()

    if actual_hash.lower() != expected_hash.lower():
        logger.error("Checksum mismatch! Expected: %s, Actual: %s", expected_hash, actual_hash)
        return False

    logger.info("SHA-256 checksum verified successfully: %s", actual_hash[:16])
    return True


def restore_backup(
    backup_path: Path,
    target_db: str,
    db_container: str = "aiproject-db-1",
    db_user: str = "aiproject",
    confirm: bool = False,
) -> None:
    """Restore a verified compressed SQL dump into the target database."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Step 1: Checksum verification
    if not verify_checksum(backup_path):
        raise ValueError("Backup file integrity check failed. Restore aborted.")

    # Step 2: Safety checks
    if target_db.lower() in ("aiproject", "production", "prod") and not confirm:
        raise PermissionError(
            f"Restoring to protected target '{target_db}' requires explicit --confirm flag."
        )

    if not confirm:
        raise PermissionError(
            "Restore requires --confirm flag to execute changes. Run with --confirm to proceed."
        )

    logger.info("Preparing to restore %s to database '%s' on container '%s'...", backup_path.name, target_db, db_container)

    # Step 3: Ensure target database exists
    create_db_cmd = [
        "docker", "exec", "-i", db_container,
        "psql", "-U", db_user, "-d", "postgres",
        "-c", f"CREATE DATABASE {target_db};"
    ]
    res = subprocess.run(create_db_cmd, capture_output=True, text=True)
    if res.returncode == 0:
        logger.info("Created target database '%s'.", target_db)
    else:
        logger.info("Target database '%s' already exists or notice: %s", target_db, res.stderr.strip())

    # Step 4: Decompress and pipe to psql
    restore_cmd = [
        "docker", "exec", "-i", db_container,
        "psql", "-U", db_user, "-d", target_db
    ]

    logger.info("Piping decompressed SQL data to psql inside container...")
    proc = subprocess.Popen(restore_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    with gzip.open(backup_path, "rb") as gz_in:
        while chunk := gz_in.read(65536):
            if proc.stdin is not None:
                proc.stdin.write(chunk)

    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"psql restore failed with code {proc.returncode}: {stderr.decode('utf-8', errors='replace')}")

    logger.info("Database restore to '%s' completed successfully!", target_db)


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe PostgreSQL Database Restore Utility")
    parser.add_argument("--backup", type=Path, required=True, help="Path to .sql.gz backup file")
    parser.add_argument("--target-db", type=str, default=None, help="Target PostgreSQL database name")
    parser.add_argument("--container", type=str, default="aiproject-db-1", help="Database docker container name")
    parser.add_argument("--user", type=str, default="aiproject", help="PostgreSQL user")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation to execute restore")
    parser.add_argument("--verify-only", action="store_true", help="Only verify checksum without restoring")

    args = parser.parse_args()

    if args.verify_only:
        valid = verify_checksum(args.backup)
        sys.exit(0 if valid else 1)

    if not args.target_db:
        logger.error("--target-db is required when restoring.")
        sys.exit(1)

    try:
        restore_backup(
            backup_path=args.backup,
            target_db=args.target_db,
            db_container=args.container,
            db_user=args.user,
            confirm=args.confirm,
        )
    except Exception as exc:
        logger.error("Restore failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
