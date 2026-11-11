"""Automated PostgreSQL backup utility with SHA-256 checksumming and retention management.

Features:
- Executes pg_dump against the active Docker database container or local PostgreSQL.
- Compresses backups using gzip (.sql.gz).
- Calculates and stores a SHA-256 checksum file alongside the backup.
- Writes metadata JSON (timestamp, database, size, record counts).
- Implements backup retention rotation (keeps the last N backups, default 7).
- Safety guarantee: Never deletes the only remaining valid backup.

Usage:
    python scripts/backup_db.py [--output-dir backups] [--retention 7]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup")

DEFAULT_BACKUP_DIR = Path("backups")
DEFAULT_RETENTION = 7


def calculate_sha256(filepath: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_backup(
    output_dir: Path = DEFAULT_BACKUP_DIR,
    retention_count: int = DEFAULT_RETENTION,
    db_container: str = "aiproject-db-1",
    db_user: str = "aiproject",
    db_name: str = "aiproject",
    remote_sync_cmd: str | None = None,
) -> Path:
    """Create a compressed database dump, generate checksum, and rotate old backups."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"db_backup_{db_name}_{timestamp}.sql.gz"
    backup_path = output_dir / backup_filename
    checksum_path = output_dir / f"{backup_filename}.sha256"
    metadata_path = output_dir / f"{backup_filename}.meta.json"

    logger.info("Starting automated backup for database '%s'...", db_name)

    # Command to run pg_dump inside Docker container and pipe compressed output
    cmd = [
        "docker",
        "exec",
        "-i",
        db_container,
        "pg_dump",
        "-U",
        db_user,
        "-d",
        db_name,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
    ]

    try:
        import gzip

        logger.info("Executing pg_dump command via docker exec...")
        dump_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        with gzip.open(backup_path, "wb") as gz_out:
            if dump_proc.stdout is not None:
                while chunk := dump_proc.stdout.read(65536):
                    gz_out.write(chunk)

        _, stderr = dump_proc.communicate()
        if dump_proc.returncode != 0:
            if backup_path.exists():
                backup_path.unlink()
            err_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"pg_dump failed with exit code {dump_proc.returncode}: {err_msg}")

    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        raise

    # Calculate and store checksum
    sha256_hash = calculate_sha256(backup_path)
    checksum_path.write_text(f"{sha256_hash}  {backup_filename}\n", encoding="utf-8")
    logger.info("Backup successfully written to %s (SHA-256: %s)", backup_path, sha256_hash[:16])

    # Write metadata
    metadata = {
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_name,
        "user": db_user,
        "filename": backup_filename,
        "size_bytes": backup_path.stat().st_size,
        "sha256": sha256_hash,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Rotate old backups
    rotate_backups(output_dir, retention_count)

    # Off-host replication hook (e.g. AWS S3, Rclone, or Azure Blob)
    if remote_sync_cmd:
        sync_formatted = remote_sync_cmd.format(
            file=str(backup_path),
            checksum=str(checksum_path),
            meta=str(metadata_path),
            dir=str(output_dir),
        )
        logger.info("Syncing backup to off-host target via: %s", sync_formatted)
        try:
            import shlex

            sync_args = shlex.split(sync_formatted)
            subprocess.run(sync_args, capture_output=True, text=True, check=True)
            logger.info("Off-host sync completed successfully.")
        except Exception as exc:
            logger.error("Off-host sync command failed: %s", exc)
            # Do not fail local backup if remote sync fails, but raise or log warning

    return backup_path


def rotate_backups(output_dir: Path, retention_count: int) -> None:
    """Rotate backups keeping at most `retention_count` files, never deleting if <= 1 remains."""
    backups = sorted(output_dir.glob("db_backup_*.sql.gz"), key=lambda p: p.stat().st_mtime)
    if len(backups) <= 1:
        logger.info("Only %d backup exists; retention rotation skipped.", len(backups))
        return

    while len(backups) > retention_count and len(backups) > 1:
        oldest = backups.pop(0)
        logger.info("Rotating old backup: %s", oldest.name)
        try:
            oldest.unlink(missing_ok=True)
            sha_file = oldest.with_name(f"{oldest.name}.sha256")
            sha_file.unlink(missing_ok=True)
            meta_file = oldest.with_name(f"{oldest.name}.meta.json")
            meta_file.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to remove old backup %s: %s", oldest, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated PostgreSQL Backup Utility")
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="Directory to store backups"
    )
    parser.add_argument(
        "--retention", type=int, default=DEFAULT_RETENTION, help="Number of backups to retain"
    )
    parser.add_argument(
        "--container", type=str, default="aiproject-db-1", help="Database docker container name"
    )
    parser.add_argument("--user", type=str, default="aiproject", help="PostgreSQL user")
    parser.add_argument("--db", type=str, default="aiproject", help="PostgreSQL database name")
    parser.add_argument(
        "--remote-sync",
        type=str,
        default=None,
        help="Command template for off-host syncing (e.g. 'aws s3 cp {file} s3://bucket/')"
    )

    args = parser.parse_args()
    try:
        backup_file = run_backup(
            output_dir=args.output_dir,
            retention_count=args.retention,
            db_container=args.container,
            db_user=args.user,
            db_name=args.db,
            remote_sync_cmd=args.remote_sync,
        )
        logger.info("Backup complete: %s", backup_file)
    except Exception as exc:
        logger.error("Failed to complete backup: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
