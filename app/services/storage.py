"""Streaming upload storage with type, size and content checks.

Client filenames are only kept as display metadata. Files are written under a
server-generated name inside the configured directory.
"""

import codecs
import contextlib
import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import BinaryIO

from app.core.exceptions import FileTooLargeError, InvalidFileError
from app.ml.ingestion import detect_file_format
from app.utils.paths import resolve_within, sanitize_display_filename

CHUNK_SIZE = 1024 * 1024
XLSX_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class StoredFile:
    path: Path
    stored_filename: str
    original_filename: str
    file_format: str
    size_bytes: int
    sha256: str


def _check_content_signature(file_format: str, head: bytes) -> None:
    if file_format == "excel":
        if not head.startswith(XLSX_MAGIC):
            raise InvalidFileError("The file content is not an .xlsx workbook.")
        return
    if b"\x00" in head:
        raise InvalidFileError("The file appears to be binary, not CSV text.")
    try:
        # Incremental decode tolerates a multi-byte character cut at the chunk boundary.
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        raise InvalidFileError("CSV files must be UTF-8 encoded.") from None


def store_upload(
    source: BinaryIO, original_filename: str | None, dest_dir: Path, *, max_bytes: int
) -> StoredFile:
    """Stream `source` to `dest_dir`, enforcing the size limit while writing."""
    display_name = sanitize_display_filename(original_filename)
    file_format = detect_file_format(display_name)
    extension = PurePath(display_name).suffix.lower()

    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{extension}"
    final_path = resolve_within(dest_dir, stored_filename)
    temp_path = final_path.with_name(final_path.name + ".part")

    digest = hashlib.sha256()
    size = 0
    try:
        with temp_path.open("xb") as out:
            first = True
            while chunk := source.read(CHUNK_SIZE):
                if first:
                    _check_content_signature(file_format, chunk)
                    first = False
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(
                        f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit."
                    )
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise InvalidFileError("The file is empty.")
        os.replace(temp_path, final_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    return StoredFile(
        path=final_path,
        stored_filename=stored_filename,
        original_filename=display_name,
        file_format=file_format,
        size_bytes=size,
        sha256=digest.hexdigest(),
    )


def delete_stored_file(dest_dir: Path, stored_filename: str) -> None:
    with contextlib.suppress(OSError, ValueError):
        resolve_within(dest_dir, stored_filename).unlink(missing_ok=True)
