#!/usr/bin/env python3
"""Offline validator for paper-import/classification invariants."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "library"
CONFIG = ROOT / "config" / "import_policy.json"

sys.path.insert(0, str(ROOT / "scripts"))
from zotero_write import (  # noqa: E402
    canonical_tag_objects_from_rows,
    extract_arxiv_id,
    normalize_doi,
    normalize_title,
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []

    policy = load_json(CONFIG)
    collections = load_json(LIB / "collections.json")
    tags = load_json(LIB / "tags.json")
    items = load_json(LIB / "items.json")

    collection_keys = {str(x.get("key") or "") for x in collections}
    tag_names = {str(x.get("tag") or "") for x in tags}
    tag_name_counts: dict[str, int] = {}
    for row in tags:
        name = str(row.get("tag") or "")
        if name:
            tag_name_counts[name] = tag_name_counts.get(name, 0) + 1
    duplicate_tag_names = sorted(
        name for name, count in tag_name_counts.items() if count > 1
    )
    if duplicate_tag_names:
        fail(
            errors,
            "same-name Zotero tag variants detected: "
            + ", ".join(duplicate_tag_names),
        )

    for field in (
        "unclassified_collection_key",
        "metadata_verification_collection_key",
    ):
        key = str(policy.get(field) or "")
        if key and key not in collection_keys:
            fail(errors, f"{field} is not a current collection key: {key}")

    default_tag = str(policy.get("default_reading_tag") or "")
    if default_tag and default_tag not in tag_names:
        fail(errors, f"default_reading_tag is not a current tag: {default_tag}")

    for field in (
        "classification_confidence_threshold",
        "metadata_confidence_threshold",
    ):
        value = float(policy.get(field, -1))
        if not 0 <= value <= 1:
            fail(errors, f"{field} must be in [0,1]")

    if int(policy.get("max_automatic_collections", 0)) < 1:
        fail(errors, "max_automatic_collections must be >= 1")

    # Pure-function regression checks used by duplicate detection.
    if normalize_doi("https://doi.org/10.48550/arXiv.9999.99999") != "10.48550/arxiv.9999.99999":
        fail(errors, "DOI normalization regression")
    if extract_arxiv_id({
        "DOI": "10.48550/arXiv.9999.99999",
        "url": "",
        "extra": "",
    }) != "9999.99999":
        fail(errors, "arXiv extraction regression")
    if normalize_title("Example Operator Paper: Parametric PDEs") != normalize_title(
        "Example operator paper — parametric PDEs"
    ):
        fail(errors, "title normalization regression")


    # Existing-tag reuse must preserve Zotero tag type. This regression models
    # a long-lived automatic tag plus a one-off same-name regular tag.
    canonical = canonical_tag_objects_from_rows([
        {"tag": "/unread", "type": 1, "meta": {"numItems": 10}},
        {"tag": "/unread", "type": 0, "meta": {"numItems": 1}},
        {"tag": "topic/example", "type": 0, "meta": {"numItems": 3}},
    ])
    if canonical.get("/unread") != {"tag": "/unread", "type": 1}:
        fail(errors, "tag-type reuse regression for /unread")
    if canonical.get("topic/example") != {"tag": "topic/example", "type": 0}:
        fail(errors, "tag-type reuse regression for regular tags")

    # Library duplicate diagnostics using the same strong identifiers.
    doi_map: dict[str, list[str]] = {}
    arxiv_map: dict[str, list[str]] = {}
    for item in items:
        key = str(item.get("key") or "")
        doi = normalize_doi(item.get("DOI"))
        arxiv = extract_arxiv_id(item)
        if doi:
            doi_map.setdefault(doi, []).append(key)
        if arxiv:
            arxiv_map.setdefault(arxiv, []).append(key)

    duplicate_doi_groups = sum(1 for keys in doi_map.values() if len(keys) > 1)
    duplicate_arxiv_groups = sum(1 for keys in arxiv_map.values() if len(keys) > 1)

    context = LIB / "classification_context.md"
    if not context.exists():
        fail(errors, "library/classification_context.md is missing")
    else:
        text = context.read_text(encoding="utf-8")
        for required in (
            str(policy.get("unclassified_collection_path") or ""),
            str(policy.get("metadata_verification_collection_path") or ""),
            str(policy.get("default_reading_tag") or ""),
        ):
            if required and required not in text:
                fail(errors, f"classification_context.md missing expected policy surface: {required}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "VALID",
        "collections": len(collections),
        "tags": len(tags),
        "items": len(items),
        "duplicate_doi_groups_existing_library": duplicate_doi_groups,
        "duplicate_arxiv_groups_existing_library": duplicate_arxiv_groups,
        "duplicate_tag_name_groups": len(duplicate_tag_names),
        "classification_context": "present",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
