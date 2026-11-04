#!/usr/bin/env python3
"""Validate annotation mirror semantics and the fail-closed write boundary."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import zotero_features as zf


def main() -> int:
    caps = json.loads(
        (ROOT / "config" / "capabilities.json").read_text(encoding="utf-8")
    )
    cap = caps["capabilities"]["annotation_write"]
    assert cap["verdict"] == "PARTIALLY_SUPPORTED"
    assert cap["enabled"] is True
    assert cap["contract_status"] == "undocumented_but_live_verified"
    assert "create_annotation" in zf.EXTENDED_OPERATIONS
    assert "patch_annotation_comment" in zf.EXTENDED_OPERATIONS
    assert "probe_create_annotation" not in zf.EXTENDED_OPERATIONS

    source = {
        "key": "SOURCE01",
        "data": {
            "itemType": "annotation",
            "parentItem": "ATT00001",
            "annotationType": "highlight",
            "annotationText": "exact source text",
            "annotationPageLabel": "1",
            "annotationSortIndex": "00000|000123|00000",
            "annotationPosition": json.dumps({
                "pageIndex": 0,
                "rects": [[10.0, 20.0, 30.0, 40.0]],
            }),
        },
    }
    probe_item, probe_audit = zf._build_annotation_item_from_source(
        attachment_key="ATT00001",
        source_annotation=source,
        annotation_type="note",
        comment="capability probe",
        color="#ffd400",
    )
    assert probe_item["itemType"] == "annotation"
    assert probe_item["parentItem"] == "ATT00001"
    assert probe_item["annotationType"] == "note"
    assert probe_item["annotationComment"] == "capability probe"
    assert json.loads(probe_item["annotationPosition"]) == {
        "pageIndex": 0,
        "rects": [[10.0, 20.0, 30.0, 40.0]],
    }
    assert probe_audit["source_annotation_key"] == "SOURCE01"
    assert probe_audit["geometry_source"] == "existing_synchronized_annotation"

    write_source = (ROOT / "scripts" / "zotero_write.py").read_text(
        encoding="utf-8"
    )
    assert "SPECIAL_ITEM_TYPE_REQUIRES_DEDICATED_WORKFLOW" in write_source

    rows = json.loads(
        (ROOT / "examples" / "synthetic-library" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(rows, list)
    known = {"highlight", "underline", "note", "text", "image", "ink"}
    observed: set[str] = set()
    positional = 0
    for row in rows:
        annotation_type = str(row.get("annotationType") or "")
        if annotation_type:
            observed.add(annotation_type)
            assert annotation_type in known
        position = row.get("annotationPosition")
        if position:
            parsed = position if isinstance(position, dict) else json.loads(position)
            assert isinstance(parsed.get("pageIndex"), int)
            positional += 1

    assert positional > 0, "expected synchronized annotations with exact positions"
    print(json.dumps({
        "status": "VALID",
        "write_enabled": True,
        "production_create_available": True,
        "comment_patch_available": True,
        "generic_special_item_guard": True,
        "observed_types": sorted(observed),
        "position_records": positional,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
