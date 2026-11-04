#!/usr/bin/env python3
"""Offline regression checks for P1 instance onboarding."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from set_access_mode import build_access_config

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    current = json.loads((ROOT / "config" / "access_mode.json").read_text(encoding="utf-8"))
    fixed = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)

    rw = build_access_config(current, mode="read_write", minutes=30, now=fixed)
    if rw["mode"] != "read_write":
        errors.append("read_write session mode regression")
    if rw["expires_at"] != "2026-01-02T03:34:05+00:00":
        errors.append("read_write expiry regression")
    if rw["allow_destructive"] is not False:
        errors.append("access workflow must never enable destructive writes")

    ro = build_access_config(rw, mode="read_only", minutes=30, now=fixed)
    if ro["mode"] != "read_only" or ro["activated_at"] is not None or ro["expires_at"] is not None:
        errors.append("read_only close-session regression")

    preflight = (ROOT / ".github" / "workflows" / "instance-preflight.yml").read_text(encoding="utf-8")
    manage = (ROOT / ".github" / "workflows" / "manage-access-mode.yml").read_text(encoding="utf-8")
    sync = (ROOT / ".github" / "workflows" / "sync-zotero.yml").read_text(encoding="utf-8")
    write = (ROOT / ".github" / "workflows" / "zotero-write.yml").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")

    for needle in ("instance_doctor.py", "ZOTERO_API_KEY_READONLY", "ZOTERO_USER_ID", "INSTANCE_REPOSITORY_PRIVATE"):
        if needle not in preflight:
            errors.append(f"instance preflight missing {needle}")

    if "--require-enabled" in preflight:
        errors.append("first-run preflight must not require sync to be enabled")
    if "set_access_mode.py" not in manage or "workflow_dispatch" not in manage:
        errors.append("manage-access-mode workflow is incomplete")
    for name, workflow in (("sync", sync), ("write", write), ("manage-access", manage)):
        if "INSTANCE_REPOSITORY_PRIVATE" not in workflow:
            errors.append(f"{name} workflow does not enforce private deployment")
    if "REQUIRE_READ_ONLY" not in sync:
        errors.append("sync workflow does not enforce a non-write read-only key")
    if write.count("check_zotero_key.py") < 2:
        errors.append("write workflow must preflight both read-only and read-write keys")
    if "Use this template" not in quickstart or "Instance Preflight" not in quickstart:
        errors.append("quickstart is missing the standard onboarding path")
    # First Run performs read-only preflight and the initial verified sync.
    # It must precede the step that activates recurring synchronization.
    first_run = quickstart.find("## 4. Run First Run")
    enable_sync = quickstart.find("## 5. Enable ongoing sync")
    if first_run < 0 or enable_sync < 0 or first_run >= enable_sync:
        errors.append("quickstart must finish First Run before enabling scheduled sync")

    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print(json.dumps({"status": "VALID", "checks": 15}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
