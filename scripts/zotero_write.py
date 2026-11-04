#!/usr/bin/env python3
"""Controlled Zotero Web API write executor.

Writes are disabled unless config/access_mode.json is in a non-expired
read_write session. Every request is version-checked and leaves an auditable
receipt in write_requests/completed or write_requests/failed.

The script is stdlib-only and never prints the API key.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from zotero_features import (
    EXTENDED_OPERATIONS,
    PartialWriteError,
    execute_extended_operation,
)

ROOT = Path(__file__).resolve().parents[1]
ACCESS_CONFIG = ROOT / "config" / "access_mode.json"
MIRROR_CONFIG = ROOT / "config" / "mirror.json"
IMPORT_CONFIG = ROOT / "config" / "import_policy.json"
PDF_UPLOAD_CONFIG = ROOT / "config" / "pdf_upload_policy.json"
PENDING = ROOT / "write_requests" / "pending"
COMPLETED = ROOT / "write_requests" / "completed"
FAILED = ROOT / "write_requests" / "failed"
LAST_RUN = ROOT / "write_requests" / "last_run.json"

SAFE_PATCH_FIELDS = {
    "title", "creators", "abstractNote", "date", "publicationTitle",
    "proceedingsTitle", "bookTitle", "university", "publisher", "place",
    "volume", "issue", "pages", "DOI", "ISBN", "ISSN", "url",
    "accessDate", "language", "rights", "shortTitle", "archive",
    "archiveLocation", "libraryCatalog", "extra", "tags", "collections",
    "relations", "note", "parentItem",
}

NONDESTRUCTIVE_OPERATIONS = {
    "patch_item",
    "add_tags",
    "remove_tags",
    "add_collections",
    "remove_collections",
    "create_note",
    "update_note",
    "create_item",
    "import_paper",
    "create_collection",
    "patch_collection",
    *EXTENDED_OPERATIONS,
}

DESTRUCTIVE_OPERATIONS = {
    "delete_item",
    "delete_collection",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def require_write_mode(access: dict[str, Any]) -> None:
    if access.get("mode") != "read_write":
        raise RuntimeError("WRITE_MODE_DISABLED: access mode is read_only")
    expires = parse_time(access.get("expires_at"))
    if expires is None:
        raise RuntimeError("WRITE_MODE_INVALID: read_write mode has no expires_at")
    if utcnow() >= expires:
        raise RuntimeError(
            f"WRITE_MODE_EXPIRED: read_write session expired at {expires.isoformat()}"
        )


def http_request(
    *,
    base: str,
    user_id: str,
    api_key: str,
    method: str,
    route: str,
    body: Any | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any | None, dict[str, str]]:
    url = f"{base.rstrip('/')}/users/{user_id}{route}"
    payload = None
    merged = {
        "Zotero-API-Key": api_key,
        "Zotero-API-Version": "3",
        "User-Agent": "zotero-mirror-write/1.1",
    }
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        merged["Content-Type"] = "application/json"
    if headers:
        merged.update(headers)

    request = urllib.request.Request(
        url,
        data=payload,
        headers=merged,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else None
            return response.status, parsed, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"ZOTERO_HTTP_{exc.code}: {detail[:1000]}"
        ) from exc


def get_object(
    base: str,
    user_id: str,
    api_key: str,
    route: str,
) -> dict[str, Any]:
    _, body, _ = http_request(
        base=base,
        user_id=user_id,
        api_key=api_key,
        method="GET",
        route=route,
    )
    if not isinstance(body, dict):
        raise RuntimeError(f"Unexpected Zotero response for {route}")
    return body


def fetch_all_list(
    base: str,
    user_id: str,
    api_key: str,
    route: str,
) -> list[dict[str, Any]]:
    start = 0
    rows: list[dict[str, Any]] = []
    while True:
        sep = "&" if "?" in route else "?"
        paged = f"{route}{sep}start={start}&limit=100&format=json"
        _, body, _ = http_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="GET",
            route=paged,
        )
        if not isinstance(body, list):
            raise RuntimeError(f"Unexpected Zotero list response for {route}")
        rows.extend(x for x in body if isinstance(x, dict))
        if len(body) < 100:
            break
        start += len(body)
    return rows


def current_library_version(
    base: str,
    user_id: str,
    api_key: str,
) -> int:
    _, _, headers = http_request(
        base=base,
        user_id=user_id,
        api_key=api_key,
        method="GET",
        route="/items?limit=1",
    )
    value = headers.get("Last-Modified-Version")
    if not value or not str(value).isdigit():
        raise RuntimeError("Could not determine current Zotero library version")
    return int(value)


def require_explicit_confirmation(request: dict[str, Any]) -> None:
    confirmation = request.get("human_confirmation")
    if not isinstance(confirmation, dict) or confirmation.get("explicit") is not True:
        raise RuntimeError("WRITE_NOT_CONFIRMED: human_confirmation.explicit must be true")
    if not confirmation.get("summary"):
        raise RuntimeError("WRITE_NOT_CONFIRMED: confirmation summary is required")


def require_expected_version(
    current: dict[str, Any],
    expected: Any,
    label: str,
) -> int:
    actual = int(current.get("version") or (current.get("data") or {}).get("version") or -1)
    if expected is None:
        raise RuntimeError(f"STALE_WRITE_GUARD_MISSING: expected {label} version is required")
    if int(expected) != actual:
        raise RuntimeError(
            f"STALE_WRITE_REJECTED: expected {label} version {expected}, current is {actual}"
        )
    return actual


def write_token(request_id: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]", "-", request_id)
    return token[:32] or "zotero-ai-write"


def item_patch(
    *,
    base: str,
    user_id: str,
    api_key: str,
    key: str,
    expected_version: int,
    patch: dict[str, Any],
) -> dict[str, Any]:
    invalid = sorted(set(patch) - SAFE_PATCH_FIELDS)
    if invalid:
        raise RuntimeError(f"UNSAFE_PATCH_FIELDS: {', '.join(invalid)}")
    status, body, headers = http_request(
        base=base,
        user_id=user_id,
        api_key=api_key,
        method="PATCH",
        route=f"/items/{key}",
        body=patch,
        headers={"If-Unmodified-Since-Version": str(expected_version)},
    )
    return {
        "http_status": status,
        "last_modified_version": headers.get("Last-Modified-Version"),
        "response": body,
    }


def normalize_tag_objects(values: list[Any]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for value in values:
        if isinstance(value, dict):
            tag = str(value.get("tag") or "").strip()
            tag_type = value.get("type")
        else:
            tag = str(value).strip()
            tag_type = None
        if not tag or tag in seen:
            continue
        seen.add(tag)
        entry: dict[str, Any] = {"tag": tag}
        if tag_type is not None:
            entry["type"] = tag_type
        result.append(entry)
    return result


def plain_text_to_note_html(text: str) -> str:
    paragraphs = [
        f"<p>{html.escape(part)}</p>"
        for part in re.split(r"\n\s*\n", text.strip())
        if part.strip()
    ]
    return "".join(paragraphs)


def normalize_doi(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^doi:\s*", "", raw, flags=re.IGNORECASE)
    return raw.strip().lower() or None


def extract_arxiv_id(data: dict[str, Any]) -> str | None:
    values = [
        str(data.get("DOI") or ""),
        str(data.get("url") or ""),
        str(data.get("extra") or ""),
    ]
    patterns = [
        r"10\.48550/arXiv\.([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
        r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
    ]
    for value in values:
        for pattern in patterns:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                return re.sub(r"v\d+$", "", match.group(1), flags=re.IGNORECASE).lower()
    return None


def normalize_title(value: Any) -> str:
    text = str(value or "").casefold()
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)


def first_author_key(data: dict[str, Any]) -> str | None:
    creators = data.get("creators") or []
    for creator in creators:
        if not isinstance(creator, dict):
            continue
        if creator.get("creatorType") not in {None, "", "author"}:
            continue
        name = str(creator.get("lastName") or creator.get("name") or "").strip()
        if name:
            return normalize_title(name)
    return None


def duplicate_candidates(
    *,
    base: str,
    user_id: str,
    api_key: str,
    incoming: dict[str, Any],
) -> list[dict[str, Any]]:
    incoming_doi = normalize_doi(incoming.get("DOI"))
    incoming_arxiv = extract_arxiv_id(incoming)
    incoming_title = normalize_title(incoming.get("title"))
    incoming_author = first_author_key(incoming)
    matches: list[dict[str, Any]] = []

    for obj in fetch_all_list(base, user_id, api_key, "/items/top"):
        data = obj.get("data") or {}
        if data.get("itemType") in {"attachment", "note", "annotation"}:
            continue

        reasons: list[str] = []
        existing_doi = normalize_doi(data.get("DOI"))
        existing_arxiv = extract_arxiv_id(data)
        existing_title = normalize_title(data.get("title"))
        existing_author = first_author_key(data)

        if incoming_doi and existing_doi and incoming_doi == existing_doi:
            reasons.append("doi")
        if incoming_arxiv and existing_arxiv and incoming_arxiv == existing_arxiv:
            reasons.append("arxiv")
        if incoming_title and existing_title and incoming_title == existing_title:
            if not incoming_author or not existing_author or incoming_author == existing_author:
                reasons.append("title")

        if reasons:
            matches.append({
                "key": str(obj.get("key") or data.get("key") or ""),
                "version": int(obj.get("version") or data.get("version") or 0),
                "title": data.get("title"),
                "DOI": data.get("DOI"),
                "url": data.get("url"),
                "reasons": reasons,
            })

    return matches


def current_collection_keys(
    base: str,
    user_id: str,
    api_key: str,
) -> set[str]:
    return {
        str(obj.get("key") or (obj.get("data") or {}).get("key") or "")
        for obj in fetch_all_list(base, user_id, api_key, "/collections")
        if str(obj.get("key") or (obj.get("data") or {}).get("key") or "")
    }


def canonical_tag_objects_from_rows(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Choose one existing Zotero tag object per visible tag name.

    Zotero distinguishes regular and automatic tags by the optional `type`
    field. Reusing only the text can create a second same-name tag of another
    type. Prefer the variant already attached to the most items; on an exact
    tie prefer a regular/manual tag (type 0) over an automatic tag (type 1).
    """
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for obj in rows:
        tag = str(obj.get("tag") or "").strip()
        if not tag:
            continue
        meta = obj.get("meta") or {}
        try:
            num_items = int(meta.get("numItems") or 0)
        except (TypeError, ValueError):
            num_items = 0

        entry: dict[str, Any] = {"tag": tag}
        tag_type = obj.get("type")
        if tag_type is not None:
            entry["type"] = int(tag_type)
        grouped.setdefault(tag, []).append((num_items, entry))

    canonical: dict[str, dict[str, Any]] = {}
    for tag, candidates in grouped.items():
        candidates.sort(
            key=lambda pair: (
                pair[0],
                1 if pair[1].get("type") == 0 else 0,
            ),
            reverse=True,
        )
        canonical[tag] = dict(candidates[0][1])
    return canonical


def current_tag_objects(
    base: str,
    user_id: str,
    api_key: str,
) -> dict[str, dict[str, Any]]:
    # Item JSON is authoritative for tag type. Build a small synthetic tag
    # catalog from live top-level items instead of assuming /tags includes type.
    counts: dict[tuple[str, int | None], int] = {}
    for obj in fetch_all_list(base, user_id, api_key, "/items/top"):
        data = obj.get("data") or {}
        for raw in data.get("tags") or []:
            if not isinstance(raw, dict):
                continue
            tag = str(raw.get("tag") or "").strip()
            if not tag:
                continue
            raw_type = raw.get("type")
            tag_type = int(raw_type) if raw_type is not None else None
            key = (tag, tag_type)
            counts[key] = counts.get(key, 0) + 1

    rows: list[dict[str, Any]] = []
    for (tag, tag_type), num_items in counts.items():
        row: dict[str, Any] = {
            "tag": tag,
            "meta": {"numItems": num_items},
        }
        if tag_type is not None:
            row["type"] = tag_type
        rows.append(row)
    return canonical_tag_objects_from_rows(rows)


def prepare_import_item(
    *,
    request: dict[str, Any],
    base: str,
    user_id: str,
    api_key: str,
    policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = request.get("payload") or {}
    item = payload.get("item")
    classification = payload.get("classification") or {}
    provenance = payload.get("provenance") or {}

    if not isinstance(item, dict):
        raise RuntimeError("INVALID_IMPORT: payload.item is required")
    if not item.get("itemType"):
        raise RuntimeError("INVALID_IMPORT: itemType is required")
    if not str(item.get("title") or "").strip():
        raise RuntimeError("INVALID_IMPORT: title is required")
    if item.get("itemType") in {"attachment", "note", "annotation"}:
        raise RuntimeError("INVALID_IMPORT: import_paper requires a bibliographic item type")

    metadata_sources = provenance.get("metadata_sources") or []
    if not isinstance(metadata_sources, list) or not any(str(x).strip() for x in metadata_sources):
        raise RuntimeError("INVALID_IMPORT: provenance.metadata_sources is required")

    metadata_conf = float(payload.get("metadata_confidence", 0.0))
    classification_conf = float(classification.get("confidence", 0.0))
    if not 0.0 <= metadata_conf <= 1.0:
        raise RuntimeError("INVALID_IMPORT: metadata_confidence must be in [0,1]")
    if not 0.0 <= classification_conf <= 1.0:
        raise RuntimeError("INVALID_IMPORT: classification.confidence must be in [0,1]")

    duplicates = duplicate_candidates(
        base=base,
        user_id=user_id,
        api_key=api_key,
        incoming=item,
    )
    if duplicates:
        raise RuntimeError(
            "DUPLICATE_CANDIDATE: " + json.dumps(
                duplicates, ensure_ascii=False, sort_keys=True
            )
        )

    available_collections = current_collection_keys(base, user_id, api_key)
    requested_collections = [
        str(x) for x in (classification.get("collection_keys") or []) if str(x)
    ]

    metadata_threshold = float(policy.get("metadata_confidence_threshold", 0.9))
    classification_threshold = float(
        policy.get("classification_confidence_threshold", 0.75)
    )

    classification_mode: str
    if metadata_conf < metadata_threshold:
        collections = [str(policy["metadata_verification_collection_key"])]
        classification_mode = "metadata_verification"
    elif classification_conf < classification_threshold or not requested_collections:
        collections = [str(policy["unclassified_collection_key"])]
        classification_mode = "pending_classification"
    else:
        max_collections = int(policy.get("max_automatic_collections", 4))
        collections = list(dict.fromkeys(requested_collections))[:max_collections]
        classification_mode = "classified"

    unknown_collections = [x for x in collections if x not in available_collections]
    if unknown_collections:
        raise RuntimeError(
            "UNKNOWN_COLLECTION_KEY: " + ", ".join(unknown_collections)
        )

    requested_tags = [
        str(x).strip()
        for x in (classification.get("tags") or [])
        if str(x).strip()
    ]
    default_tag = str(policy.get("default_reading_tag") or "").strip()
    if default_tag and payload.get("mark_read") is not True:
        requested_tags.append(default_tag)
    requested_tags = list(dict.fromkeys(requested_tags))

    warnings: list[str] = []
    tags = requested_tags
    tag_objects = normalize_tag_objects(tags)
    if policy.get("reuse_existing_tags_only") is True:
        existing_tags = current_tag_objects(base, user_id, api_key)
        allowed_names: list[str] = []
        allowed_objects: list[dict[str, Any]] = []
        omitted: list[str] = []

        if (
            default_tag
            and payload.get("mark_read") is not True
            and default_tag not in existing_tags
        ):
            raise RuntimeError(
                "DEFAULT_READING_TAG_MISSING: configured default tag is not "
                "present in the live Zotero library"
            )

        for tag in requested_tags:
            existing = existing_tags.get(tag)
            if existing is not None:
                allowed_names.append(tag)
                allowed_objects.append(dict(existing))
            else:
                omitted.append(tag)

        tags = allowed_names
        tag_objects = allowed_objects
        if omitted:
            warnings.append(
                "Omitted unknown automatic tags: " + ", ".join(omitted)
            )

    prepared = {
        k: v
        for k, v in item.items()
        if k not in {"key", "version", "collections", "tags"}
    }
    prepared["collections"] = collections
    prepared["tags"] = tag_objects

    audit = {
        "classification_mode": classification_mode,
        "metadata_confidence": metadata_conf,
        "classification_confidence": classification_conf,
        "collection_keys": collections,
        "tags": tags,
        "classification_reasons": classification.get("reasons") or [],
        "provenance": provenance,
        "warnings": warnings,
    }
    return prepared, audit


def created_object_key(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for field in ("successful", "success"):
        bucket = body.get(field)
        if not isinstance(bucket, dict):
            continue
        value = bucket.get("0")
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            key = value.get("key") or (value.get("data") or {}).get("key")
            if key:
                return str(key)
    return None


def execute_request(
    request: dict[str, Any],
    access: dict[str, Any],
    mirror: dict[str, Any],
    import_policy: dict[str, Any],
    pdf_upload_policy: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    require_write_mode(access)
    require_explicit_confirmation(request)

    request_id = str(request.get("request_id") or "").strip()
    operation = str(request.get("operation") or "").strip()
    if not request_id:
        raise RuntimeError("INVALID_REQUEST: request_id is required")
    if operation not in NONDESTRUCTIVE_OPERATIONS | DESTRUCTIVE_OPERATIONS:
        raise RuntimeError(f"UNSUPPORTED_OPERATION: {operation}")

    destructive = operation in DESTRUCTIVE_OPERATIONS
    if destructive:
        if access.get("allow_destructive") is not True:
            raise RuntimeError("DESTRUCTIVE_WRITE_DISABLED")
        phrase = str(access.get("destructive_confirmation_phrase") or "")
        provided = str(request.get("destructive_confirmation") or "")
        if not phrase or provided != phrase:
            raise RuntimeError("DESTRUCTIVE_WRITE_NOT_CONFIRMED")

    base = str(mirror["zotero_api_base"])
    user_id = str(mirror["zotero_user_id"])
    before_library_version = current_library_version(base, user_id, api_key)
    target = request.get("target") or {}
    payload = request.get("payload") or {}
    expected = request.get("expected") or {}

    result: dict[str, Any]
    audit_details: dict[str, Any] | None = None

    if operation in {"patch_item", "add_tags", "remove_tags", "add_collections", "remove_collections", "update_note", "delete_item"}:
        key = str(target.get("item_key") or "")
        if not key:
            raise RuntimeError("INVALID_REQUEST: target.item_key is required")
        current = get_object(base, user_id, api_key, f"/items/{key}")
        current_version = require_expected_version(
            current,
            expected.get("item_version"),
            "item",
        )
        data = current.get("data") or {}

        if operation == "patch_item":
            patch = payload.get("patch")
            if not isinstance(patch, dict) or not patch:
                raise RuntimeError("INVALID_REQUEST: payload.patch must be a non-empty object")
            result = item_patch(
                base=base, user_id=user_id, api_key=api_key,
                key=key, expected_version=current_version, patch=patch,
            )

        elif operation in {"add_tags", "remove_tags"}:
            existing = normalize_tag_objects(data.get("tags") or [])
            by_name = {x["tag"]: x for x in existing}
            tags = [str(x).strip() for x in (payload.get("tags") or []) if str(x).strip()]
            if operation == "add_tags":
                canonical = current_tag_objects(base, user_id, api_key)
                for tag in tags:
                    # Assign rather than setdefault: if this item currently
                    # carries a same-name tag of the wrong Zotero type, an
                    # explicit add normalizes it to the canonical live variant.
                    by_name[tag] = dict(canonical.get(tag, {"tag": tag}))
            else:
                for tag in tags:
                    by_name.pop(tag, None)
            result = item_patch(
                base=base, user_id=user_id, api_key=api_key,
                key=key, expected_version=current_version,
                patch={"tags": list(by_name.values())},
            )

        elif operation in {"add_collections", "remove_collections"}:
            current_keys = [str(x) for x in (data.get("collections") or [])]
            changes = [str(x) for x in (payload.get("collection_keys") or [])]
            if operation == "add_collections":
                new_keys = list(dict.fromkeys(current_keys + changes))
            else:
                remove = set(changes)
                new_keys = [x for x in current_keys if x not in remove]
            result = item_patch(
                base=base, user_id=user_id, api_key=api_key,
                key=key, expected_version=current_version,
                patch={"collections": new_keys},
            )

        elif operation == "update_note":
            if data.get("itemType") != "note":
                raise RuntimeError("TARGET_NOT_NOTE")
            note_html = payload.get("note_html")
            if note_html is None and payload.get("note_text") is not None:
                note_html = plain_text_to_note_html(str(payload["note_text"]))
            if not isinstance(note_html, str):
                raise RuntimeError("INVALID_REQUEST: note_html or note_text is required")
            result = item_patch(
                base=base, user_id=user_id, api_key=api_key,
                key=key, expected_version=current_version,
                patch={"note": note_html},
            )

        else:
            status, body, headers = http_request(
                base=base,
                user_id=user_id,
                api_key=api_key,
                method="DELETE",
                route=f"/items/{key}",
                headers={"If-Unmodified-Since-Version": str(current_version)},
            )
            result = {
                "http_status": status,
                "response": body,
                "last_modified_version": headers.get("Last-Modified-Version"),
            }

    elif operation in {"patch_collection", "delete_collection"}:
        key = str(target.get("collection_key") or "")
        if not key:
            raise RuntimeError("INVALID_REQUEST: target.collection_key is required")
        current = get_object(base, user_id, api_key, f"/collections/{key}")
        current_version = require_expected_version(
            current,
            expected.get("collection_version"),
            "collection",
        )
        if operation == "patch_collection":
            patch = payload.get("patch")
            if not isinstance(patch, dict) or not patch:
                raise RuntimeError("INVALID_REQUEST: payload.patch is required")
            allowed = {"name", "parentCollection"}
            invalid = sorted(set(patch) - allowed)
            if invalid:
                raise RuntimeError(f"UNSAFE_COLLECTION_PATCH_FIELDS: {', '.join(invalid)}")
            current_data = dict(current.get("data") or {})
            current_data.update(patch)
            current_data["version"] = current_version
            status, body, headers = http_request(
                base=base, user_id=user_id, api_key=api_key,
                method="PUT", route=f"/collections/{key}",
                body=current_data,
            )
        else:
            status, body, headers = http_request(
                base=base, user_id=user_id, api_key=api_key,
                method="DELETE", route=f"/collections/{key}",
                headers={"If-Unmodified-Since-Version": str(current_version)},
            )
        result = {
            "http_status": status,
            "response": body,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }

    elif operation in {"create_item", "create_note", "import_paper"}:
        if operation == "create_item":
            item = payload.get("item")
            if not isinstance(item, dict) or not item.get("itemType"):
                raise RuntimeError("INVALID_REQUEST: payload.item with itemType is required")
            special_type = str(item.get("itemType") or "")
            if special_type in {"annotation", "attachment", "note"}:
                raise RuntimeError(
                    "SPECIAL_ITEM_TYPE_REQUIRES_DEDICATED_WORKFLOW: "
                    + special_type
                )
            item = {k: v for k, v in item.items() if k not in {"key", "version"}}
        elif operation == "import_paper":
            item, audit_details = prepare_import_item(
                request=request,
                base=base,
                user_id=user_id,
                api_key=api_key,
                policy=import_policy,
            )
        else:
            note_html = payload.get("note_html")
            if note_html is None and payload.get("note_text") is not None:
                note_html = plain_text_to_note_html(str(payload["note_text"]))
            if not isinstance(note_html, str):
                raise RuntimeError("INVALID_REQUEST: note_html or note_text is required")
            item = {
                "itemType": "note",
                "note": note_html,
                "tags": normalize_tag_objects(payload.get("tags") or []),
            }
            if target.get("parent_item_key"):
                item["parentItem"] = str(target["parent_item_key"])

        status, body, headers = http_request(
            base=base, user_id=user_id, api_key=api_key,
            method="POST", route="/items", body=[item],
            headers={
                "If-Unmodified-Since-Version": str(before_library_version),
            },
        )
        result = {
            "http_status": status,
            "response": body,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }
        created_key = created_object_key(body)
        if created_key:
            result["created_item_key"] = created_key

    elif operation in EXTENDED_OPERATIONS:
        result, audit_details = execute_extended_operation(
            operation=operation,
            request=request,
            base=base,
            user_id=user_id,
            api_key=api_key,
            before_library_version=before_library_version,
            pdf_policy=pdf_upload_policy,
        )

    elif operation == "create_collection":
        name = str(payload.get("name") or "").strip()
        if not name:
            raise RuntimeError("INVALID_REQUEST: payload.name is required")
        collection: dict[str, Any] = {"name": name}
        parent = payload.get("parent_collection")
        if parent:
            collection["parentCollection"] = str(parent)
        status, body, headers = http_request(
            base=base, user_id=user_id, api_key=api_key,
            method="POST", route="/collections", body=[collection],
            headers={
                "If-Unmodified-Since-Version": str(before_library_version),
            },
        )
        result = {
            "http_status": status,
            "response": body,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }
        created_key = created_object_key(body)
        if created_key:
            result["created_collection_key"] = created_key

    else:
        raise RuntimeError(f"UNSUPPORTED_OPERATION: {operation}")

    after_library_version = current_library_version(base, user_id, api_key)
    receipt = {
        "request_id": request_id,
        "operation": operation,
        "status": "success",
        "destructive": destructive,
        "processed_at": utcnow().replace(microsecond=0).isoformat(),
        "before_library_version": before_library_version,
        "after_library_version": after_library_version,
        "result": result,
        "human_confirmation": request.get("human_confirmation"),
    }
    if audit_details is not None:
        if operation == "import_paper":
            receipt["import_audit"] = audit_details
        else:
            receipt["operation_audit"] = audit_details
    return receipt


def main() -> int:
    api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ZOTERO_API_KEY is not set", file=sys.stderr)
        return 2

    access = load_json(ACCESS_CONFIG)
    mirror = load_json(MIRROR_CONFIG)
    if os.environ.get("ZOTERO_USER_ID", "").strip():
        mirror["zotero_user_id"] = os.environ["ZOTERO_USER_ID"].strip()
    if os.environ.get("ZOTERO_API_BASE", "").strip():
        mirror["zotero_api_base"] = os.environ["ZOTERO_API_BASE"].strip()
    if not str(mirror.get("zotero_user_id") or "").isdigit():
        print(
            "ERROR: configure ZOTERO_USER_ID (repository variable) or "
            "config/mirror.json before writing",
            file=sys.stderr,
        )
        return 2
    import_policy = load_json(IMPORT_CONFIG)
    pdf_upload_policy = load_json(PDF_UPLOAD_CONFIG)
    PENDING.mkdir(parents=True, exist_ok=True)
    COMPLETED.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    pending = sorted(PENDING.glob("*.json"))
    if not pending:
        outcome = {
            "status": "no_pending_requests",
            "processed_at": utcnow().replace(microsecond=0).isoformat(),
        }
        write_json(LAST_RUN, outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 0

    if len(pending) > 1:
        outcome = {
            "status": "rejected",
            "reason": "MULTIPLE_PENDING_REQUESTS: process one write request per workflow run",
            "pending": [p.name for p in pending],
        }
        write_json(LAST_RUN, outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 3

    path = pending[0]
    request: dict[str, Any] | None = None
    try:
        request = load_json(path)
        if not isinstance(request, dict):
            raise RuntimeError("INVALID_REQUEST: request must be an object")
        receipt = execute_request(
            request,
            access,
            mirror,
            import_policy,
            pdf_upload_policy,
            api_key,
        )
        destination = COMPLETED / path.name
        write_json(destination, receipt)
        path.unlink()
        outcome = {
            "status": "success",
            "request_id": receipt["request_id"],
            "operation": receipt["operation"],
            "receipt": str(destination.relative_to(ROOT)),
        }
        write_json(LAST_RUN, outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        request_id = (
            str(request.get("request_id"))
            if isinstance(request, dict) and request.get("request_id")
            else path.stem
        )
        receipt = {
            "request_id": request_id,
            "status": "rejected",
            "processed_at": utcnow().replace(microsecond=0).isoformat(),
            "error": str(exc),
            "request": request,
        }
        if isinstance(exc, PartialWriteError):
            receipt["partial_result"] = exc.details
        destination = FAILED / path.name
        write_json(destination, receipt)
        path.unlink()
        outcome = {
            "status": "rejected",
            "request_id": request_id,
            "receipt": str(destination.relative_to(ROOT)),
            "error": str(exc),
        }
        write_json(LAST_RUN, outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
