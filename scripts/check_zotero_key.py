#!/usr/bin/env python3
"""Verify a Zotero API key without exposing it."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("ZOTERO_API_BASE", "https://api.zotero.org").rstrip("/")
API_KEY = os.environ.get("ZOTERO_API_KEY", "").strip()
EXPECTED_USER_ID = os.environ.get("ZOTERO_USER_ID", "").strip()
REQUIRE_WRITE = os.environ.get("REQUIRE_WRITE", "false").lower() == "true"
REQUIRE_READ_ONLY = os.environ.get("REQUIRE_READ_ONLY", "false").lower() == "true"
REQUIRE_NOTES = os.environ.get("REQUIRE_NOTES", "true").lower() == "true"
REQUIRE_FILES = os.environ.get("REQUIRE_FILES", "true").lower() == "true"


def main() -> int:
    if not API_KEY:
        print("ERROR: ZOTERO_API_KEY is not set", file=sys.stderr)
        return 2

    if REQUIRE_WRITE and REQUIRE_READ_ONLY:
        print("ERROR: REQUIRE_WRITE and REQUIRE_READ_ONLY are mutually exclusive", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        f"{API_BASE}/keys/current",
        headers={
            "Zotero-API-Key": API_KEY,
            "Zotero-API-Version": "3",
            "User-Agent": "zotero-mirror-key-check/1.1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            obj = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: Zotero key check failed: HTTP {exc.code}: {detail[:500]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: Zotero key check failed: {exc}", file=sys.stderr)
        return 1

    user_id = str(obj.get("userID") or "")
    access = ((obj.get("access") or {}).get("user") or {})
    summary = {
        "user_id_matches": (not EXPECTED_USER_ID or user_id == EXPECTED_USER_ID),
        "library": bool(access.get("library")),
        "notes": bool(access.get("notes")),
        "files": bool(access.get("files")),
        "write": bool(access.get("write")),
    }

    errors: list[str] = []
    if not summary["user_id_matches"]:
        errors.append("Zotero key belongs to a different user")
    if not summary["library"]:
        errors.append("Zotero key lacks personal-library access")
    if REQUIRE_NOTES and not summary["notes"]:
        errors.append("Zotero key lacks notes access")
    if REQUIRE_FILES and not summary["files"]:
        errors.append("Zotero key lacks file access")
    if REQUIRE_WRITE and not summary["write"]:
        errors.append("Zotero key lacks write permission")
    if REQUIRE_READ_ONLY and summary["write"]:
        errors.append("read-only key unexpectedly has write permission")

    if errors:
        print(json.dumps({"status": "INVALID", **summary}, ensure_ascii=False, indent=2))
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps({"status": "VALID", **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
