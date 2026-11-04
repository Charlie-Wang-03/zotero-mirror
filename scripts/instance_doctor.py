#!/usr/bin/env python3
"""Validate a deployed zotero-mirror instance without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def fetch_key_metadata(api_base: str, api_key: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/keys/current",
        headers={
            "Zotero-API-Key": api_key,
            "Zotero-API-Version": "3",
            "User-Agent": "zotero-mirror-instance-doctor/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc


def summarize_key(
    *,
    obj: dict[str, Any],
    expected_user_id: str,
    require_write: bool,
    require_read_only: bool,
) -> tuple[dict[str, bool], list[str]]:
    user_id = str(obj.get("userID") or "")
    access = ((obj.get("access") or {}).get("user") or {})
    summary = {
        "user_id_matches": user_id == expected_user_id,
        "library": bool(access.get("library")),
        "notes": bool(access.get("notes")),
        "files": bool(access.get("files")),
        "write": bool(access.get("write")),
    }
    errors: list[str] = []
    if not summary["user_id_matches"]:
        errors.append("key belongs to a different Zotero user")
    if not summary["library"]:
        errors.append("key lacks personal-library access")
    if not summary["notes"]:
        errors.append("key lacks notes access")
    if not summary["files"]:
        errors.append("key lacks file access")
    if require_write and not summary["write"]:
        errors.append("key lacks write permission")
    if require_read_only and summary["write"]:
        errors.append("read-only key has write permission")
    return summary, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--require-enabled", action="store_true")
    parser.add_argument("--check-write", action="store_true")
    args = parser.parse_args()

    mirror = load_json(ROOT / "config" / "mirror.json")
    access_mode = load_json(ROOT / "config" / "access_mode.json")

    user_id = os.environ.get("ZOTERO_USER_ID", "").strip()
    mirror_enabled = bool_env("ZOTERO_MIRROR_ENABLED")
    write_enabled = bool_env("ZOTERO_WRITE_ENABLED")
    readonly_key = os.environ.get("ZOTERO_API_KEY_READONLY", "").strip()
    readwrite_key = os.environ.get("ZOTERO_API_KEY_READWRITE", "").strip()
    repo_private_raw = os.environ.get("INSTANCE_REPOSITORY_PRIVATE", "").strip().lower()

    errors: list[str] = []
    warnings: list[str] = []

    if not user_id.isdigit():
        errors.append("ZOTERO_USER_ID must be configured as the numeric Zotero user ID")
    if args.require_enabled and not mirror_enabled:
        errors.append("ZOTERO_MIRROR_ENABLED must be true")
    if not readonly_key:
        errors.append("ZOTERO_API_KEY_READONLY is missing")
    if args.check_write and not write_enabled:
        errors.append("ZOTERO_WRITE_ENABLED must be true when --check-write is requested")
    if write_enabled and not readwrite_key:
        errors.append("ZOTERO_API_KEY_READWRITE is missing while write support is enabled")

    if repo_private_raw:
        if repo_private_raw != "true":
            errors.append("real Zotero mirrors must be deployed in a private repository")
    else:
        warnings.append("repository visibility was not supplied to the doctor")

    if mirror.get("zotero_user_id"):
        warnings.append("config/mirror.json contains a user ID; repository variable ZOTERO_USER_ID is preferred")

    if access_mode.get("allow_destructive") is not False:
        errors.append("allow_destructive must remain false during onboarding")

    readonly_summary: dict[str, Any] = {"present": bool(readonly_key)}
    write_summary: dict[str, Any] = {"present": bool(readwrite_key)}

    if args.online and user_id.isdigit() and readonly_key:
        try:
            obj = fetch_key_metadata(str(mirror["zotero_api_base"]), readonly_key)
            summary, key_errors = summarize_key(
                obj=obj,
                expected_user_id=user_id,
                require_write=False,
                require_read_only=True,
            )
            readonly_summary.update(summary)
            errors.extend(f"read-only key: {x}" for x in key_errors)
        except RuntimeError as exc:
            errors.append(f"read-only key verification failed: {exc}")

    need_write_check = args.check_write or write_enabled
    if args.online and need_write_check and user_id.isdigit() and readwrite_key:
        try:
            obj = fetch_key_metadata(str(mirror["zotero_api_base"]), readwrite_key)
            summary, key_errors = summarize_key(
                obj=obj,
                expected_user_id=user_id,
                require_write=True,
                require_read_only=False,
            )
            write_summary.update(summary)
            errors.extend(f"read-write key: {x}" for x in key_errors)
        except RuntimeError as exc:
            errors.append(f"read-write key verification failed: {exc}")

    report = {
        "status": "READY" if not errors else "NOT_READY",
        "online_checks": args.online,
        "repository_private": repo_private_raw == "true" if repo_private_raw else None,
        "user_id_configured": user_id.isdigit(),
        "mirror_enabled": mirror_enabled,
        "write_enabled": write_enabled,
        "default_access_mode": access_mode.get("mode"),
        "destructive_writes_enabled": bool(access_mode.get("allow_destructive")),
        "readonly_key": readonly_summary,
        "readwrite_key": write_summary,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
