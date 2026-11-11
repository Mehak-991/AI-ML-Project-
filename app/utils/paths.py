"""Safe path handling for server-managed storage directories."""

import re
import unicodedata
from pathlib import Path, PurePath

# Names we generate ourselves: hex/uuid stems with a short lowercase extension.
SAFE_STORED_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}\.[a-z0-9]{1,10}$")


def resolve_within(base_dir: Path, filename: str) -> Path:
    """Resolve `filename` inside `base_dir`, rejecting traversal and odd names.

    Raises ValueError if the name is not a plain generated filename or would
    resolve outside the base directory (e.g. via '..', absolute paths or symlinks).
    """
    if not SAFE_STORED_NAME.match(filename):
        raise ValueError("Invalid stored filename.")
    base = base_dir.resolve()
    candidate = (base / filename).resolve()
    if candidate.parent != base:
        raise ValueError("Path escapes the storage directory.")
    return candidate


def sanitize_display_filename(name: str | None, max_length: int = 255) -> str:
    """Make a client-supplied filename safe to store as metadata (never used as a path)."""
    if not name:
        return "upload"
    base = PurePath(name.replace("\\", "/")).name
    base = unicodedata.normalize("NFKC", base)
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"/\\|?*')
    base = base.strip(" .")
    return base[:max_length] or "upload"
