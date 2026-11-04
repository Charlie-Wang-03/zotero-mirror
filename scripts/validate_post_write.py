#!/usr/bin/env python3
"""Verify supported Zotero writes against the refreshed read-only mirror."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "library"
LAST_RUN = ROOT / "write_requests" / "last_run.json"
COMPLETED = ROOT / "write_requests" / "completed"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(message: str) -> None:
    print("ERROR: " + message, file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not LAST_RUN.exists():
        print(json.dumps({"status": "SKIP", "reason": "no last_run"}))
        return 0
    last = load(LAST_RUN)
    if last.get("status") != "success":
        print(json.dumps({"status": "SKIP", "reason": "last run was not success"}))
        return 0

    request_id = str(last.get("request_id") or "")
    receipt_path = COMPLETED / f"{request_id}.json"
    if not receipt_path.exists() and last.get("receipt"):
        receipt_path = ROOT / str(last["receipt"])
    if not receipt_path.exists():
        fail("successful last_run has no completed receipt")

    receipt = load(receipt_path)
    operation = str(receipt.get("operation") or "")
    result = receipt.get("result") or {}

    if operation == "upload_pdf":
        key = str(result.get("attachment_key") or "")
        attachments = load(LIB / "attachments.json")
        row = next((x for x in attachments if x.get("key") == key), None)
        if not row:
            fail(f"uploaded attachment {key} missing from read-only mirror")
        if row.get("parentItem") != result.get("parent_item_key"):
            fail("uploaded attachment parent mismatch")
        if str(row.get("contentType") or "") != "application/pdf":
            fail("uploaded attachment contentType is not application/pdf")
        expected_md5 = str((result.get("checksum") or {}).get("md5") or "")
        if expected_md5 and str(row.get("md5") or "") != expected_md5:
            fail("uploaded attachment MD5 mismatch")
        upload_result = result.get("upload_result") or {}
        if upload_result.get("registered") is not True:
            fail("uploaded attachment was not registered with Zotero Storage")
        fulltext = load(LIB / "fulltext" / "index.json").get("attachments") or {}
        fulltext_indexed = key in fulltext

    elif operation in {"create_saved_search", "patch_saved_search"}:
        key = str(
            result.get("created_search_key")
            or result.get("search_key")
            or ""
        )
        rows = load(LIB / "saved_searches.json")
        if not any(row.get("key") == key for row in rows):
            fail(f"saved search {key} missing from read-only mirror")

    elif operation == "delete_saved_search":
        key = str(result.get("deleted_search_key") or "")
        rows = load(LIB / "saved_searches.json")
        if any(row.get("key") == key for row in rows):
            fail(f"deleted saved search {key} still present in read-only mirror")

    elif operation == "create_annotation":
        key = str(result.get("created_item_key") or "")
        rows = load(LIB / "annotations.json")
        row = next((x for x in rows if x.get("key") == key), None)
        if not row:
            fail(f"annotation probe item {key} missing from read-only mirror")
        if str(row.get("attachmentKey") or "") != str(
            result.get("attachment_key") or ""
        ):
            fail("annotation probe parent attachment mismatch")
        if str(row.get("annotationType") or "") != str(
            result.get("annotation_type") or ""
        ):
            fail("annotation probe type mismatch")
        if str(row.get("annotationComment") or "") != str(
            result.get("annotation_comment") or ""
        ):
            fail("annotation probe comment mismatch")
        if str(row.get("annotationColor") or "") != str(
            result.get("annotation_color") or ""
        ):
            fail("annotation probe color mismatch")
        expected_position = (receipt.get("operation_audit") or {}).get("position")
        actual_position = row.get("annotationPosition")
        if isinstance(actual_position, str):
            actual_position = json.loads(actual_position)
        if expected_position != actual_position:
            fail("annotation probe exact position mismatch")

    elif operation == "patch_annotation_comment":
        key = str(result.get("annotation_key") or "")
        rows = load(LIB / "annotations.json")
        row = next((x for x in rows if x.get("key") == key), None)
        if not row:
            fail(f"annotation {key} missing from read-only mirror")
        if str(row.get("annotationComment") or "") != str(
            result.get("annotation_comment") or ""
        ):
            fail("annotation comment patch mismatch")

    elif operation == "create_annotation_note":
        key = str(result.get("created_item_key") or "")
        rows = load(LIB / "notes_all.json")
        row = next((x for x in rows if x.get("key") == key), None)
        if not row:
            fail(f"annotation note {key} missing from read-only mirror")
        note_html = str(row.get("noteHtml") or "")
        if "data-annotation=" not in note_html or "data-citation=" not in note_html:
            fail("annotation note lost rich-link metadata")
        for ann_key in result.get("source_annotation_keys") or []:
            if str(ann_key) not in note_html:
                fail(f"annotation note missing source annotation key {ann_key}")

    else:
        print(json.dumps({
            "status": "SKIP",
            "reason": f"operation {operation!r} has no extended verifier",
        }))
        return 0

    output = {
        "status": "VALID",
        "operation": operation,
        "request_id": request_id,
        "readonly_mirror_verified": True,
    }
    if operation == "upload_pdf":
        output["storage_attachment_verified"] = True
        output["fulltext_indexed"] = fulltext_indexed
        if not fulltext_indexed:
            output["fulltext_status"] = "PENDING_ZOTERO_INDEXING"
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
