"""Fail if Git tracks a file that must never be committed (database dumps, env files, keys).

Complements secret scanning: a dump holds password hashes and personal data that no
secret-pattern scanner recognises. Prints file names only, never contents.

Usage: python scripts/check_tracked_files.py [--paths FILE ...]   (default: `git ls-files`)
Exit code 1 when a forbidden file is tracked.
"""

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Real env files are forbidden; the committed templates are allowed.
ALLOWED = re.compile(r"(^|/)\.env\.(example|production\.example)$")
FORBIDDEN = re.compile(
    r"(^|/)\.env(\..+)?$"
    r"|\.(sql|sql\.gz|dump|dmp|bak|pgdump|sqlite3?|db|pem|key|p12|pfx|jks)$"
    r"|(^|/)backups/(?!\.gitkeep$)"
    r"|(^|/)monitoring/secrets/(?!\.gitignore$)",
    re.IGNORECASE,
)


def forbidden_files(paths: Iterable[str]) -> list[str]:
    normalized = (p.replace("\\", "/") for p in paths)
    return sorted(p for p in normalized if FORBIDDEN.search(p) and not ALLOWED.search(p))


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=ROOT, check=True
    )
    return result.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", help="Check these paths instead of `git ls-files`")
    args = parser.parse_args(argv)
    bad = forbidden_files(args.paths if args.paths is not None else tracked_files())
    if bad:
        print("Tracked files that must not be committed:")
        for path in bad:
            print(f"  {path}")
        return 1
    print("No forbidden tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
