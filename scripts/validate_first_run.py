#!/usr/bin/env python3
"""Offline regression checks for P2 template and first-run UX."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []

    workflow_path = ROOT / ".github" / "workflows" / "first-run.yml"
    quickstart_path = ROOT / "docs" / "QUICKSTART.md"
    template_path = ROOT / "docs" / "TEMPLATE_DEPLOYMENT.md"
    ci_path = ROOT / ".github" / "workflows" / "mirror-ci.yml"

    for path in (workflow_path, quickstart_path, template_path, ci_path):
        if not path.exists():
            errors.append(f"missing P2 surface: {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    workflow = workflow_path.read_text(encoding="utf-8")
    quickstart = quickstart_path.read_text(encoding="utf-8")
    template = template_path.read_text(encoding="utf-8")
    ci = ci_path.read_text(encoding="utf-8")

    required_workflow_tokens = (
        "INSTANCE_REPOSITORY_PRIVATE",
        "INSTANCE_DEFAULT_BRANCH",
        "instance_doctor.py --online",
        "sync_guard.py",
        "validate_mirror.py --strict",
        "git add -A library",
        "GITHUB_STEP_SUMMARY",
    )
    for token in required_workflow_tokens:
        if token not in workflow:
            errors.append(f"First Run workflow missing {token}")

    forbidden_workflow_tokens = (
        "ZOTERO_API_KEY_READWRITE",
        "ZOTERO_WRITE_ENABLED == 'true'",
        "ZOTERO_MIRROR_ENABLED == 'true'",
    )
    for token in forbidden_workflow_tokens:
        if token in workflow:
            errors.append(f"First Run must not depend on write/scheduled-sync gate: {token}")

    if "ZOTERO_API_KEY_READONLY" not in workflow:
        errors.append("First Run must use the dedicated read-only key")

    if 'echo "Set repository variable `' in workflow or 'echo "Do not enable `' in workflow:
        errors.append("First Run summary must not use shell command-substitution backticks inside double quotes")

    first_run_pos = quickstart.find("## 4. Run First Run")
    enable_pos = quickstart.find("## 5. Enable ongoing sync")
    if first_run_pos < 0 or enable_pos < 0 or first_run_pos >= enable_pos:
        errors.append("Quickstart must run First Run before enabling scheduled sync")

    if "Use this template" not in quickstart:
        errors.append("Quickstart must begin from the template flow")

    if "Private" not in template or "fork" not in template.lower():
        errors.append("Template deployment doc must distinguish private template instances from forks")

    if "github.repository == 'Charlie-Wang-03/zotero-mirror'" not in ci:
        errors.append("public-upstream CI must not run inside generated private instances")

    access = json.loads((ROOT / "config" / "access_mode.json").read_text(encoding="utf-8"))
    if access.get("mode") != "read_only":
        errors.append("template must still ship in read_only mode")
    if access.get("allow_destructive") is not False:
        errors.append("template must ship with destructive writes disabled")

    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print(json.dumps({"status": "VALID", "checks": 17}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
