#!/usr/bin/env python3
"""Emit SHA-256 metadata for audit artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def hash_file(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            digest.update(chunk)
    return {"path": str(path), "bytes": total, "sha256": digest.hexdigest()}


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: hash-artifact.py <file> [<file> ...]", file=sys.stderr)
        return 2

    paths = [Path(arg) for arg in argv]
    for path in paths:
        if not path.is_file():
            print(f"error: {path} is not a regular file", file=sys.stderr)
            return 2

    print(json.dumps([hash_file(path) for path in paths], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
