#!/usr/bin/env python3
"""Offline integrity validator for the committed Zotero mirror."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "library"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(directory: Path, pattern: str = "*.md") -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(directory.glob(pattern), key=lambda p: p.name):
        if not path.is_file():
            continue
        content_hash = sha256(path)
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
        count += 1
    return digest.hexdigest(), count


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    required = [
        "manifest.json",
        "sync_report.json",
        "STATUS.md",
        "items.json",
        "top_level_misc.json",
        "attachments.json",
        "annotations.json",
        "notes.json",
        "notes_all.json",
        "collections.json",
        "tags.json",
        "references.bib",
        "catalog.md",
        "quality_report.md",
        "fulltext/index.json",
    ]
    for rel in required:
        if not (LIB / rel).exists():
            fail(errors, f"missing required file: library/{rel}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    manifest = load_json(LIB / "manifest.json")
    report = load_json(LIB / "sync_report.json")
    counts = manifest.get("counts") or {}
    schema_version = int(manifest.get("schemaVersion") or 0)
    if schema_version >= 4 and not (LIB / "saved_searches.json").exists():
        fail(errors, "schema v4+ mirror is missing library/saved_searches.json")

    if report.get("status") != "CONSISTENT":
        fail(errors, "sync_report status is not CONSISTENT")
    if report.get("startLibraryVersion") != report.get("endLibraryVersion"):
        fail(errors, "start/end library versions differ")
    if int(manifest.get("libraryVersion") or -1) != int(
        report.get("snapshotVersion") or -2
    ):
        fail(errors, "manifest and sync_report library versions differ")

    list_checks = {
        "bibliographicItems": "items.json",
        "topLevelMisc": "top_level_misc.json",
        "attachments": "attachments.json",
        "annotations": "annotations.json",
        "notesRelevant": "notes.json",
        "notesAll": "notes_all.json",
        "collections": "collections.json",
        "tags": "tags.json",
    }
    if schema_version >= 4:
        list_checks["savedSearches"] = "saved_searches.json"
    for key, rel in list_checks.items():
        obj = load_json(LIB / rel)
        if not isinstance(obj, list):
            fail(errors, f"{rel} is not a JSON list")
            continue
        expected = int(counts.get(key, -1))
        if len(obj) != expected:
            fail(errors, f"{rel}: expected {expected}, found {len(obj)}")

    for rel, expected_hash in (manifest.get("sha256") or {}).items():
        path = LIB / rel
        if not path.exists():
            fail(errors, f"manifest hash target missing: {rel}")
            continue
        actual = sha256(path)
        if actual != expected_hash:
            fail(errors, f"SHA-256 mismatch: {rel}")

    paper_digest, paper_count = tree_digest(LIB / "papers")
    fulltext_digest, fulltext_count = tree_digest(LIB / "fulltext")
    tree = report.get("treeDigests") or {}
    if paper_digest != tree.get("papersTreeSha256"):
        fail(errors, "papers tree digest mismatch")
    if paper_count != int(tree.get("papersFileCount") or -1):
        fail(errors, "papers file count mismatch")
    if fulltext_digest != tree.get("fulltextTreeSha256"):
        fail(errors, "fulltext tree digest mismatch")
    if fulltext_count != int(tree.get("fulltextFileCount") or -1):
        fail(errors, "fulltext file count mismatch")

    if paper_count != int(counts.get("bibliographicItems") or -1):
        fail(errors, "paper-card count does not equal bibliographic item count")
    if fulltext_count != int(counts.get("fulltextAttachments") or -1):
        fail(errors, "fulltext file count does not equal manifest fulltext count")

    full_index = load_json(LIB / "fulltext" / "index.json")
    indexed = full_index.get("attachments") or {}
    if len(indexed) != fulltext_count:
        fail(errors, "fulltext index count does not equal fulltext file count")
    for key, meta in indexed.items():
        rel = meta.get("file")
        if not rel or not (LIB / rel.replace("fulltext/", "fulltext/")).exists():
            fail(errors, f"fulltext index target missing for {key}: {rel}")

    report_counts = report.get("mirroredCounts") or {}
    mapping = {
        "bibliographicItems": "bibliographicItems",
        "topLevelMisc": "topLevelMisc",
        "notes": "notesAll",
        "attachments": "attachments",
        "annotations": "annotations",
        "collections": "collections",
        "tags": "tags",
        "fulltext": "fulltextAttachments",
    }
    if schema_version >= 4:
        mapping["searches"] = "savedSearches"
    for report_key, manifest_key in mapping.items():
        if int(report_counts.get(report_key, -1)) != int(
            counts.get(manifest_key, -2)
        ):
            fail(
                errors,
                f"sync_report/mirror manifest count mismatch: {report_key}",
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "VALID",
                "snapshotVersion": report.get("snapshotVersion"),
                "bibliographicItems": counts.get("bibliographicItems"),
                "attachments": counts.get("attachments"),
                "annotations": counts.get("annotations"),
                "fulltextAttachments": counts.get("fulltextAttachments"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
