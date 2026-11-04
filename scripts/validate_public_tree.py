#!/usr/bin/env python3
"""Fail closed if reusable upstream contains instance-specific Zotero data."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Compiling and running tests generates transient bytecode/cache files.
# They are ignored by Git and must not be mistaken for committed binary data.
TRANSIENT_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}

FORBIDDEN_PREFIXES = (
    "library/fulltext/",
    "write_requests/completed/",
    "write_requests/failed/",
    "write_requests/pending/",
)
FORBIDDEN_INSTANCE_BASENAMES = {
    "items.json",
    "notes.json",
    "notes_all.json",
    "annotations.json",
    "attachments.json",
    "collections.json",
    "tags.json",
    "references.bib",
    "sync_report.json",
    "last_run.json",
}
SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
NUMERIC_CONFIG_USER = re.compile(r'"zotero_user_id"\s*:\s*"\d+"')
NUMERIC_WORKFLOW_USER = re.compile(r"ZOTERO_USER_ID\s*:\s*[\"\']?\d+")


def main() -> int:
    errors: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in TRANSIENT_DIRS for part in path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()

        if rel.startswith(FORBIDDEN_PREFIXES):
            errors.append(f"forbidden generated/private path: {rel}")

        if rel.startswith("library/") and path.name != "README.md":
            errors.append(f"reusable upstream library/ may contain README.md only: {rel}")

        if rel.startswith("write_requests/") and path.name != "README.md":
            errors.append(f"reusable upstream write_requests/ may contain README.md only: {rel}")

        is_fixture = rel.startswith("examples/synthetic-library/")
        if path.name in FORBIDDEN_INSTANCE_BASENAMES and not is_fixture:
            errors.append(f"forbidden instance artifact: {rel}")

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"unexpected binary file in reusable upstream: {rel}")
            continue

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"credential-like content in {rel}: {pattern.pattern}")

        if NUMERIC_CONFIG_USER.search(text):
            errors.append(f"hard-coded Zotero user ID in {rel}")
        if NUMERIC_WORKFLOW_USER.search(text):
            errors.append(f"hard-coded workflow Zotero user ID in {rel}")

    mirror = json.loads((ROOT / "config" / "mirror.json").read_text(encoding="utf-8"))
    if str(mirror.get("zotero_user_id") or "").strip():
        errors.append("config/mirror.json must not ship with a Zotero user ID")

    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print("PUBLIC_TREE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
