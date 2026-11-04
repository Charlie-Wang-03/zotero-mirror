#!/usr/bin/env python3
"""Run the reproducible, offline validation suite for the public template."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# Keep this list aligned with CI claims. Instance-only validators that require
# a real private library (validate_import, validate_post_write) are excluded.
VALIDATORS = (
    "validate_public_tree.py",
    "validate_docs.py",
    "validate_onboarding.py",
    "validate_first_run.py",
    "validate_release.py",
    "validate_file_upload.py",
    "validate_saved_searches.py",
    "validate_annotations.py",
    "validate_annotation_notes.py",
)


def main() -> int:
    python_files = sorted(SCRIPTS.glob("*.py"))
    if not python_files:
        print("ERROR: no Python scripts found", file=sys.stderr)
        return 1

    checks = (
        ("privacy boundary (before compilation)", ("scripts/validate_public_tree.py",)),
        ("compile Python scripts", ("-m", "py_compile", *(str(p.relative_to(ROOT)) for p in python_files))),
        ("privacy boundary (after compilation)", ("scripts/validate_public_tree.py",)),
        *((name, (f"scripts/{name}",)) for name in VALIDATORS[1:]),
    )

    for label, args in checks:
        print(f"==> {label}", flush=True)
        result = subprocess.run((sys.executable, *args), cwd=ROOT, check=False)
        if result.returncode:
            print(f"ERROR: offline validation failed at {label}", file=sys.stderr)
            return result.returncode

    print(f"OFFLINE_UPSTREAM_VALID ({len(checks)} checks; no live Zotero access)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
