#!/usr/bin/env python3
"""Regression checks for PARTIAL_RICH_NOTE annotation serialization."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zotero_features import build_partial_rich_note_html


def main() -> int:
    caps = json.loads(
        (ROOT / "config" / "capabilities.json").read_text(encoding="utf-8")
    )
    cap = caps["capabilities"]["annotation_to_note"]
    assert cap["verdict"] == "PARTIALLY_SUPPORTED"
    assert cap["richness"] == "PARTIAL_RICH_NOTE"

    annotation = {
        "key": "ANN00001",
        "version": 1,
        "data": {
            "itemType": "annotation",
            "parentItem": "ATT00001",
            "annotationType": "underline",
            "annotationText": "zero-shot super-resolution",
            "annotationComment": "Check this claim.",
            "annotationColor": "#ffd400",
            "annotationPageLabel": "1",
            "annotationSortIndex": "00000|000001|00000",
            "annotationPosition": json.dumps({
                "pageIndex": 0,
                "rects": [[10.0, 20.0, 30.0, 40.0]],
            }),
        },
    }
    html = build_partial_rich_note_html(
        annotations=[annotation],
        parent_data={
            "itemType": "journalArticle",
            "title": "Example",
            "date": "2026",
            "creators": [],
        },
        parent_key="ITEM0001",
        user_id="123",
    )
    assert 'data-schema-version="10"' in html
    assert 'class="underline"' in html
    assert "data-annotation=" in html
    assert "data-citation=" in html

    match = re.search(r'data-annotation="([^"]+)"', html)
    assert match
    payload = json.loads(urllib.parse.unquote(match.group(1)))
    assert payload["annotationKey"] == "ANN00001"
    assert payload["attachmentURI"].endswith("/ATT00001")
    assert payload["position"]["pageIndex"] == 0
    assert payload["citationItem"]["locator"] == "1"

    fixture_notes = json.loads(
        (ROOT / "examples" / "synthetic-library" / "notes_all.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        "data-annotation=" in str(note.get("noteHtml") or "")
        for note in fixture_notes
    ), "synthetic fixture should contain a rich annotation-note sample"

    print(json.dumps({"status": "VALID", "richness": "PARTIAL_RICH_NOTE"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
