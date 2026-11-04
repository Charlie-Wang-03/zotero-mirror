#!/usr/bin/env python3
"""Offline validation for native Zotero Saved Search support."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zotero_features import validate_saved_search


def main() -> int:
    caps = json.loads(
        (ROOT / "config" / "capabilities.json").read_text(encoding="utf-8")
    )
    cap = caps["capabilities"]["saved_searches"]
    assert cap["verdict"] == "SUPPORTED_BY_WEB_API"
    assert cap["enabled"] is True
    assert cap["web_api_executes_results"] is False

    search = validate_saved_search(
        "Unread example benchmark",
        [
            {"condition": "joinMode", "operator": "all", "value": ""},
            {"condition": "tag", "operator": "is", "value": "/unread"},
            {
                "condition": "title",
                "operator": "contains",
                "value": "example operator",
            },
            {
                "condition": "annotationText",
                "operator": "contains",
                "value": "benchmark",
            },
        ],
    )
    assert search["conditions"][1]["value"] == "/unread"

    try:
        validate_saved_search(
            "bad",
            [{"condition": "invented", "operator": "is", "value": "x"}],
        )
    except RuntimeError as exc:
        assert "UNSUPPORTED_SEARCH_CONDITION" in str(exc)
    else:
        raise AssertionError("unknown Saved Search condition was accepted")

    path = ROOT / "library" / "saved_searches.json"
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row.get("key"), str)
            assert isinstance(row.get("version"), int)
            assert isinstance(row.get("name"), str)
            assert isinstance(row.get("conditions"), list)

    print(json.dumps({"status": "VALID", "native_saved_searches": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
