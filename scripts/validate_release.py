#!/usr/bin/env python3
"""Pre-release structural assertions; use in addition to history/secret audit."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    sync = (ROOT / ".github/workflows/sync-zotero.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/mirror-ci.yml").read_text(encoding="utf-8")
    first_run = (ROOT / ".github/workflows/first-run.yml").read_text(encoding="utf-8")
    mirror = json.loads((ROOT / "config/mirror.json").read_text(encoding="utf-8"))
    access = json.loads((ROOT / "config/access_mode.json").read_text(encoding="utf-8"))

    if (ROOT / "docs/TERMINATION.md").exists():
        errors.append("superseded internal termination record remains in release tree")
    if "Discontinued" in readme or "DISCONTINUED" in agents:
        errors.append("obsolete discontinued product banner remains")
    if "MIT License" not in license_text:
        errors.append("missing MIT license")
    if "private repository" not in readme.lower():
        errors.append("README must require private user instances")
    if mirror.get("zotero_user_id"):
        errors.append("release config embeds Zotero user ID")
    if access.get("mode") != "read_only" or access.get("allow_destructive") is not False:
        errors.append("unsafe default access mode")
    if "schedule:" not in sync:
        errors.append("scheduled private-instance sync is missing")
    if "vars.ZOTERO_MIRROR_ENABLED == 'true'" not in sync:
        errors.append("live sync not opt-in")
    if "INSTANCE_REPOSITORY_PRIVATE" not in first_run:
        errors.append("First Run not privacy-gated")
    if "github.repository == 'Charlie-Wang-03/zotero-mirror'" not in ci:
        errors.append("upstream CI not scoped to canonical source repository")

    for p in ("docs/RELEASE_CHECKLIST.md", "docs/VALIDATION.md", "docs/PROJECT_HISTORY.md"):
        if not (ROOT / p).exists():
            errors.append("missing " + p)

    if errors:
        for e in errors:
            print("ERROR:", e)
        return 1

    print("RELEASE_STRUCTURE_VALID (history and secrets require separate audit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
