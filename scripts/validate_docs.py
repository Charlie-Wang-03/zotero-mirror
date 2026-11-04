#!/usr/bin/env python3
"""Validate reusable-repository documentation and safe default invariants."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_text(path: str, needle: str, errors: list[str]) -> None:
    p = ROOT / path
    if not p.exists():
        errors.append(f"missing required file: {path}")
        return
    text = p.read_text(encoding="utf-8")
    if needle not in text:
        errors.append(f"{path} must mention {needle!r}")


def main() -> int:
    errors: list[str] = []
    required = [
        "README.md",
        "README.zh-CN.md",
        "AGENTS.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "docs/INDEX.md",
        "docs/QUICKSTART.md",
        "docs/TEMPLATE_DEPLOYMENT.md",
        "docs/FIRST_RUN.md",
        "docs/CONFIGURATION.md",
        "docs/ACCESS_MODES.md",
        "docs/TROUBLESHOOTING.md",
        "docs/AI_CLIENTS.md",
        "docs/ARCHITECTURE.md",
        "docs/PRIVACY_MODEL.md",
        "docs/CLEAN_ROOM_EXTRACTION.md",
        "library/README.md",
        "write_requests/README.md",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            errors.append(f"missing required file: {rel}")

    require_text("README.md", "Private-by-default", errors)
    require_text("README.md", "[简体中文](README.zh-CN.md)", errors)
    require_text("README.md", "First Run", errors)
    require_text("AGENTS.md", "read_only", errors)
    require_text("SECURITY.md", "ZOTERO_API_KEY_READONLY", errors)
    require_text("docs/QUICKSTART.md", "Use this template", errors)
    require_text("docs/FIRST_RUN.md", "ZOTERO_MIRROR_ENABLED=true", errors)
    require_text("docs/TEMPLATE_DEPLOYMENT.md", "Template, not fork", errors)
    require_text("docs/PRIVACY_MODEL.md", "public infrastructure", errors)

    mirror = json.loads((ROOT / "config" / "mirror.json").read_text(encoding="utf-8"))
    access = json.loads((ROOT / "config" / "access_mode.json").read_text(encoding="utf-8"))

    if str(mirror.get("zotero_user_id") or "").strip():
        errors.append("config/mirror.json must ship without a Zotero user ID")
    if access.get("mode") != "read_only":
        errors.append("config/access_mode.json must default to read_only")
    if access.get("allow_destructive") is not False:
        errors.append("destructive writes must be disabled by default")

    workflows = ROOT / ".github" / "workflows"
    sync = (workflows / "sync-zotero.yml").read_text(encoding="utf-8")
    write = (workflows / "zotero-write.yml").read_text(encoding="utf-8")
    ci = (workflows / "mirror-ci.yml").read_text(encoding="utf-8")

    for required_workflow in (
        "first-run.yml",
        "instance-preflight.yml",
        "manage-access-mode.yml",
    ):
        if not (workflows / required_workflow).exists():
            errors.append(f"missing onboarding workflow: {required_workflow}")

    if "vars.ZOTERO_MIRROR_ENABLED == 'true'" not in sync:
        errors.append("sync workflow must be opt-in")
    if "REQUIRE_READ_ONLY" not in sync:
        errors.append("sync workflow must enforce read-only key privilege")
    if "ZOTERO_API_KEY_READONLY" not in sync:
        errors.append("sync workflow must use generic read-only secret")
    if "vars.ZOTERO_WRITE_ENABLED == 'true'" not in write:
        errors.append("write workflow must be separately opt-in")
    if "ZOTERO_API_KEY_READWRITE" not in write:
        errors.append("write workflow must use generic read-write secret")
    if "github.repository == 'Charlie-Wang-03/zotero-mirror'" not in ci:
        errors.append("Upstream CI must be disabled in generated instance repositories")
    if "python scripts/validate_project.py" not in ci:
        errors.append("Upstream CI must call the canonical offline validation command")
    suite_path = ROOT / "scripts" / "validate_project.py"
    if not suite_path.exists():
        errors.append("missing canonical offline validation runner")
    else:
        suite = suite_path.read_text(encoding="utf-8")
        for required_validator in (
            "validate_public_tree.py",
            "validate_docs.py",
            "validate_onboarding.py",
            "validate_first_run.py",
            "validate_release.py",
            "validate_file_upload.py",
            "validate_saved_searches.py",
            "validate_annotations.py",
            "validate_annotation_notes.py",
        ):
            if required_validator not in suite:
                errors.append(f"canonical validation runner missing {required_validator}")

    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print("DOCS_CONTRACT_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
