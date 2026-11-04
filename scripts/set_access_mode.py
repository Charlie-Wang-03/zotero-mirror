#!/usr/bin/env python3
"""Open or close a time-bounded zotero-mirror read-write session."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "access_mode.json"


def parse_utc(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso_seconds(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def build_access_config(
    current: dict[str, Any],
    *,
    mode: str,
    minutes: int,
    now: dt.datetime,
) -> dict[str, Any]:
    if mode not in {"read_only", "read_write"}:
        raise ValueError("mode must be read_only or read_write")
    if minutes < 5 or minutes > 120:
        raise ValueError("minutes must be between 5 and 120")

    updated = dict(current)
    updated["schema_version"] = int(updated.get("schema_version", 1))
    updated["allow_destructive"] = False

    if mode == "read_only":
        updated["mode"] = "read_only"
        updated["activated_at"] = None
        updated["expires_at"] = None
        return updated

    expires = now + dt.timedelta(minutes=minutes)
    updated["mode"] = "read_write"
    updated["read_write_session_minutes"] = minutes
    updated["activated_at"] = iso_seconds(now)
    updated["expires_at"] = iso_seconds(expires)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["read_only", "read_write"], required=True)
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--now")
    args = parser.parse_args()

    current = json.loads(args.config.read_text(encoding="utf-8"))
    now = parse_utc(args.now)
    updated = build_access_config(current, mode=args.mode, minutes=args.minutes, now=now)
    args.config.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "UPDATED",
        "mode": updated["mode"],
        "activated_at": updated.get("activated_at"),
        "expires_at": updated.get("expires_at"),
        "allow_destructive": updated.get("allow_destructive"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
