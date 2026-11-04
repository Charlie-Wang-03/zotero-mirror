#!/usr/bin/env python3
"""Consistency guard around sync_zotero.py.

This wrapper keeps Zotero read-only, checks that the upstream Web Library did
not change during a mirror run, reconciles server-side object counts with the
generated mirror, and writes auditable consistency evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "mirror.json"


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def request_json(
    base: str,
    user_id: str,
    api_key: str,
    route: str,
    params: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, str]]:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{base.rstrip('/')}/users/{user_id}{route}"
    if query:
        url += f"?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "Zotero-API-Key": api_key,
            "Zotero-API-Version": "3",
            "User-Agent": "zotero-mirror-guard/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        body = response.read().decode("utf-8")
        headers = {k: v for k, v in response.headers.items()}
    return json.loads(body), headers


def int_header(headers: dict[str, str], name: str) -> int | None:
    value = headers.get(name)
    return int(value) if value and value.isdigit() else None


def count_paginated_list(
    base: str,
    user_id: str,
    api_key: str,
    route: str,
    extra: dict[str, Any] | None = None,
) -> tuple[int, int | None]:
    """Count an endpoint by enumerating its actual list pages.

    Zotero's tags endpoint has different Total-Results semantics from normal
    object endpoints, so audit counts use the returned tag objects themselves.
    """
    start = 0
    total = 0
    version: int | None = None
    while True:
        params = {
            **(extra or {}),
            "limit": 100,
            "start": start,
            "format": "json",
        }
        obj, headers = request_json(base, user_id, api_key, route, params)
        if not isinstance(obj, list):
            raise RuntimeError(f"Unexpected Zotero list response for {route}")
        total += len(obj)
        current = int_header(headers, "Last-Modified-Version")
        if current is not None:
            version = current
        if len(obj) < 100:
            break
        start += len(obj)
    return total, version


def probe(
    base: str,
    user_id: str,
    api_key: str,
) -> dict[str, Any]:
    endpoints = {
        "allItems": ("/items", {}),
        "topLevelItems": ("/items/top", {}),
        "notes": ("/items", {"itemType": "note"}),
        "attachments": ("/items", {"itemType": "attachment"}),
        "annotations": ("/items", {"itemType": "annotation"}),
        "collections": ("/collections", {}),
        "searches": ("/searches", {}),
    }

    totals: dict[str, int | None] = {}
    endpoint_versions: dict[str, int | None] = {}
    library_version: int | None = None

    for name, (route, extra) in endpoints.items():
        params = {**extra, "limit": 1, "start": 0, "format": "json"}
        obj, headers = request_json(base, user_id, api_key, route, params)
        totals[name] = int_header(headers, "Total-Results")
        endpoint_versions[name] = int_header(headers, "Last-Modified-Version")
        if name == "allItems":
            library_version = endpoint_versions[name]

    tag_count, tag_version = count_paginated_list(
        base, user_id, api_key, "/tags"
    )
    totals["tags"] = tag_count
    endpoint_versions["tags"] = tag_version

    fulltext, headers = request_json(
        base, user_id, api_key, "/fulltext", {"since": 0}
    )
    if not isinstance(fulltext, dict):
        raise RuntimeError("Unexpected Zotero /fulltext response")
    totals["fulltext"] = len(fulltext)
    endpoint_versions["fulltext"] = int_header(headers, "Last-Modified-Version")

    if library_version is None:
        raise RuntimeError("Could not determine Zotero library version")

    return {
        "libraryVersion": library_version,
        "serverTotals": totals,
        "endpointVersions": endpoint_versions,
    }


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def mirror_counts(output_dir: Path) -> dict[str, int]:
    manifest = load_json(output_dir / "manifest.json")
    counts = manifest.get("counts") or {}
    return {
        "bibliographicItems": int(counts.get("bibliographicItems", 0)),
        "topLevelMisc": int(counts.get("topLevelMisc", 0)),
        "topLevelItems": int(counts.get("bibliographicItems", 0))
        + int(counts.get("topLevelMisc", 0)),
        "notes": int(counts.get("notesAll", 0)),
        "attachments": int(counts.get("attachments", 0)),
        "annotations": int(counts.get("annotations", 0)),
        "collections": int(counts.get("collections", 0)),
        "searches": int(counts.get("savedSearches", 0)),
        "tags": int(counts.get("tags", 0)),
        "fulltext": int(counts.get("fulltextAttachments", 0)),
    }


def tree_digest(directory: Path, pattern: str = "*.md") -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    if directory.exists():
        for path in sorted(directory.glob(pattern), key=lambda p: p.name):
            if not path.is_file():
                continue
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content_hash.encode("ascii"))
            digest.update(b"\n")
            count += 1
    return digest.hexdigest(), count


def build_checks(
    start: dict[str, Any],
    end: dict[str, Any],
    counts: dict[str, int],
    output_dir: Path,
) -> tuple[dict[str, bool], list[str], dict[str, Any]]:
    server = end["serverTotals"]
    checks: dict[str, bool] = {
        "snapshot_version_stable": start["libraryVersion"] == end["libraryVersion"],
        "top_level_count_matches":
            server["topLevelItems"] == counts["topLevelItems"],
        "notes_count_matches": server["notes"] == counts["notes"],
        "attachments_count_matches": server["attachments"] == counts["attachments"],
        "annotations_count_matches": server["annotations"] == counts["annotations"],
        "collections_count_matches": server["collections"] == counts["collections"],
        "searches_count_matches": server["searches"] == counts["searches"],
        "tags_count_matches": server["tags"] == counts["tags"],
        "fulltext_count_matches": server["fulltext"] == counts["fulltext"],
    }

    manifest = load_json(output_dir / "manifest.json")
    checks["manifest_version_matches"] = (
        int(manifest.get("libraryVersion") or -1) == end["libraryVersion"]
    )

    papers_digest, papers_count = tree_digest(output_dir / "papers")
    fulltext_digest, fulltext_count = tree_digest(output_dir / "fulltext")
    checks["paper_card_count_matches"] = (
        papers_count == counts["bibliographicItems"]
    )
    checks["fulltext_file_count_matches"] = (
        fulltext_count == counts["fulltext"]
    )

    discrepancies = [name for name, ok in checks.items() if not ok]
    digests = {
        "papersTreeSha256": papers_digest,
        "papersFileCount": papers_count,
        "fulltextTreeSha256": fulltext_digest,
        "fulltextFileCount": fulltext_count,
    }
    return checks, discrepancies, digests


def write_if_changed(path: Path, text: str) -> bool:
    encoded = text.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return True


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_status(report: dict[str, Any], config: dict[str, Any]) -> str:
    counts = report["mirroredCounts"]
    server = report["serverTotals"]
    fulltext_cov = (
        100.0 * counts["fulltext"] / counts["attachments"]
        if counts["attachments"]
        else 0.0
    )
    return f"""# Zotero Mirror Status

> **Health: CONSISTENT**

This file describes the latest Zotero Web Library snapshot that changed the
repository. No-change verification runs remain visible in GitHub Actions.

- Zotero library version: `{report["snapshotVersion"]}`
- Snapshot captured at: `{report["snapshotCapturedAt"]}`
- Consistency model: start/end library-version gate + server-count reconciliation
- Scheduled sync cadence: every {config["scheduled_sync_hours"]} hours
- On-demand refresh: update `.sync-trigger` or run **Sync Zotero**
- Zotero API access: **read-only**

## Mirror coverage

| Surface | Count |
|---|---:|
| Bibliographic items | {counts["bibliographicItems"]} |
| Top-level non-bibliographic items | {counts["topLevelMisc"]} |
| Attachments | {counts["attachments"]} |
| PDF annotations | {counts["annotations"]} |
| Full-text attachments | {counts["fulltext"]} |
| Collections | {counts["collections"]} |
| Saved searches | {counts["searches"]} |
| Tags | {counts["tags"]} |

Full-text coverage over attachments: **{fulltext_cov:.1f}%**

## Reconciliation evidence

| Upstream object family | Zotero server | Mirrored |
|---|---:|---:|
| Top-level items | {server["topLevelItems"]} | {counts["topLevelItems"]} |
| Notes | {server["notes"]} | {counts["notes"]} |
| Attachments | {server["attachments"]} | {counts["attachments"]} |
| Annotations | {server["annotations"]} | {counts["annotations"]} |
| Collections | {server["collections"]} | {counts["collections"]} |
| Saved searches | {server["searches"]} | {counts["searches"]} |
| Tags | {server["tags"]} | {counts["tags"]} |
| Full-text records | {server["fulltext"]} | {counts["fulltext"]} |

See `library/sync_report.json` for machine-readable evidence.

## Fast paths for ChatGPT

1. Discovery: `library/catalog.md`
2. Import classification: `library/classification_context.md`
3. Canonical Web resolution: `library/web_sources.md`
4. One paper: `library/papers/<ZOTERO_ITEM_KEY>.md`
5. Deep reading: resolve and version-align the canonical/current Web PDF
6. Personal reading memory: `library/annotations.md` and `library/notes.md`
7. Retrieval/fallback text: `library/fulltext/<ATTACHMENT_KEY>.md`
8. Library hygiene: `library/quality_report.md`
9. Citations: `library/references.bib`
"""


def run_sync(config_path: Path, config: dict[str, Any]) -> None:
    env = os.environ.copy()
    env["ZOTERO_USER_ID"] = str(config["zotero_user_id"])
    env["ZOTERO_API_BASE"] = str(config["zotero_api_base"])
    env["ZOTERO_OUTPUT_DIR"] = str(config["output_dir"])
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_zotero.py")],
        cwd=ROOT,
        env=env,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    config = load_config(args.config)
    if os.environ.get("ZOTERO_USER_ID", "").strip():
        config["zotero_user_id"] = os.environ["ZOTERO_USER_ID"].strip()
    if os.environ.get("ZOTERO_API_BASE", "").strip():
        config["zotero_api_base"] = os.environ["ZOTERO_API_BASE"].strip()
    if os.environ.get("ZOTERO_OUTPUT_DIR", "").strip():
        config["output_dir"] = os.environ["ZOTERO_OUTPUT_DIR"].strip()

    api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ZOTERO_API_KEY is not set", file=sys.stderr)
        return 2

    base = str(config["zotero_api_base"])
    user_id = str(config.get("zotero_user_id") or "").strip()
    if not user_id.isdigit():
        print(
            "ERROR: configure ZOTERO_USER_ID (repository variable) or "
            "config/mirror.json before syncing",
            file=sys.stderr,
        )
        return 2
    output_dir = ROOT / str(config["output_dir"])
    attempts = int(config.get("snapshot_retries", 3))
    delay = float(config.get("snapshot_retry_delay_seconds", 5))

    final_start: dict[str, Any] | None = None
    final_end: dict[str, Any] | None = None
    final_counts: dict[str, int] | None = None
    final_checks: dict[str, bool] | None = None
    final_discrepancies: list[str] | None = None
    final_digests: dict[str, Any] | None = None

    for attempt in range(1, attempts + 1):
        start = probe(base, user_id, api_key)
        print(
            f"snapshot attempt {attempt}/{attempts}: "
            f"start version={start['libraryVersion']}"
        )
        run_sync(args.config, config)
        end = probe(base, user_id, api_key)
        counts = mirror_counts(output_dir)
        checks, discrepancies, digests = build_checks(
            start, end, counts, output_dir
        )

        if not discrepancies:
            final_start = start
            final_end = end
            final_counts = counts
            final_checks = checks
            final_discrepancies = discrepancies
            final_digests = digests
            break

        details = {
            "server": end["serverTotals"],
            "mirror": counts,
        }
        print(
            "snapshot rejected: " + ", ".join(discrepancies)
            + " | " + json.dumps(details, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        if attempt < attempts:
            time.sleep(delay)

    if final_end is None:
        print(
            "ERROR: could not obtain a consistent Zotero snapshot "
            f"after {attempts} attempts",
            file=sys.stderr,
        )
        return 3

    previous_report: dict[str, Any] | None = None
    report_path = output_dir / "sync_report.json"
    if report_path.exists():
        try:
            obj = load_json(report_path)
            if isinstance(obj, dict):
                previous_report = obj
        except Exception:
            previous_report = None

    snapshot_version = int(final_end["libraryVersion"])
    same_snapshot = (
        previous_report
        and int(previous_report.get("snapshotVersion") or -1) == snapshot_version
        and previous_report.get("status") == "CONSISTENT"
    )

    if same_snapshot:
        captured_at = str(previous_report.get("snapshotCapturedAt"))
    else:
        captured_at = dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0
        ).isoformat()

    if same_snapshot and isinstance(previous_report.get("generator"), dict):
        generator = previous_report["generator"]
    else:
        generator = {
            "syncScript": "scripts/sync_zotero.py",
            "guardScript": "scripts/sync_guard.py",
            "config": str(args.config.relative_to(ROOT)),
            "capturedByGithubRunId": os.environ.get("GITHUB_RUN_ID"),
            "capturedFromGithubSha": os.environ.get("GITHUB_SHA"),
        }

    report = {
        "schemaVersion": 1,
        "status": "CONSISTENT",
        "snapshotVersion": snapshot_version,
        "snapshotCapturedAt": captured_at,
        "startLibraryVersion": int(final_start["libraryVersion"]),
        "endLibraryVersion": snapshot_version,
        "serverTotals": final_end["serverTotals"],
        "mirroredCounts": final_counts,
        "endpointVersionsAtEnd": final_end["endpointVersions"],
        "checks": final_checks,
        "discrepancies": final_discrepancies,
        "treeDigests": final_digests,
        "generator": generator,
    }

    report_changed = write_if_changed(report_path, stable_json(report))
    status_changed = write_if_changed(
        output_dir / "STATUS.md",
        render_status(report, config),
    )

    current_verification = dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0
    ).isoformat()
    print(stable_json({
        "status": "CONSISTENT",
        "verifiedAt": current_verification,
        "snapshotVersion": snapshot_version,
        "reportChanged": report_changed,
        "statusChanged": status_changed,
        "checks": final_checks,
    }).rstrip())

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(
                f"# Zotero mirror verification\n\n"
                f"- Status: **CONSISTENT**\n"
                f"- Verified at: `{current_verification}`\n"
                f"- Zotero library version: `{snapshot_version}`\n"
                f"- Bibliographic items: {final_counts['bibliographicItems']}\n"
                f"- Attachments: {final_counts['attachments']}\n"
                f"- Annotations: {final_counts['annotations']}\n"
                f"- Full-text records: {final_counts['fulltext']}\n"
                f"- Discrepancies: none\n"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
