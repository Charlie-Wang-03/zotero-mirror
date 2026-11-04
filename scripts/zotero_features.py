#!/usr/bin/env python3
"""Audited Zotero Web API feature helpers.

Executable capabilities:
- Zotero Storage PDF upload
- native Saved Search CRUD
- PARTIAL_RICH_NOTE generation from existing highlight/underline annotations
- controlled annotation creation from exact trusted geometry
- controlled annotation-comment updates

Deliberately absent:
- duplicate merge (native merge is a Desktop operation)
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from typing import Any


EXTENDED_OPERATIONS = {
    "upload_pdf",
    "create_saved_search",
    "patch_saved_search",
    "delete_saved_search",
    "create_annotation_note",
    "create_annotation",
    "patch_annotation_comment",
}

SEARCH_OPERATORS: dict[str, set[str]] = {
    "joinMode": {"any", "all"},
    "recursive": {"true", "false"},
    "collection": {"is", "isNot"},
    "savedSearch": {"is", "isNot"},
    "tag": {"is", "isNot", "contains", "doesNotContain"},
    "title": {
        "is", "isNot", "contains", "doesNotContain", "beginsWith",
        "isEmpty", "isNotEmpty",
    },
    "creator": {
        "is", "isNot", "contains", "doesNotContain",
        "isEmpty", "isNotEmpty",
    },
    "year": {"is", "isNot", "contains", "doesNotContain"},
    "date": {
        "is", "isNot", "isBefore", "isAfter", "isInTheLast",
        "contains", "doesNotContain", "beginsWith", "isEmpty", "isNotEmpty",
    },
    "itemType": {"is", "isNot"},
    "fulltextContent": {"contains", "doesNotContain"},
    "annotationText": {"contains", "doesNotContain"},
    "annotationComment": {"contains", "doesNotContain"},
    "annotationType": {"is", "isNot"},
    "annotationColor": {"is", "isNot"},
    "numAnnotations": {"is", "isNot", "isLessThan", "isGreaterThan"},
    "resultLevel": {"item", "attachment", "note", "annotation"},
    "groupStart": {"true"},
    "groupEnd": {"true"},
}


class PartialWriteError(RuntimeError):
    """Failure after a remote Zotero object has already been created."""

    def __init__(self, message: str, details: dict[str, Any]):
        super().__init__(message)
        self.details = details


def _json_request(
    *,
    base: str,
    user_id: str,
    api_key: str,
    method: str,
    route: str,
    body: Any | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    url = f"{base.rstrip('/')}/users/{user_id}{route}"
    payload = None
    merged = {
        "Zotero-API-Key": api_key,
        "Zotero-API-Version": "3",
        "User-Agent": "zotero-mirror-features/1.0",
        "Accept": "application/json",
    }
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        merged["Content-Type"] = "application/json"
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=payload, headers=merged, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            status = int(response.status)
            response_headers = {k: v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"ZOTERO_HTTP_{exc.code}: {detail}") from exc
    parsed: Any = None
    if raw:
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = text
    return status, parsed, response_headers


def _form_request(
    *,
    base: str,
    user_id: str,
    api_key: str,
    route: str,
    fields: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    url = f"{base.rstrip('/')}/users/{user_id}{route}"
    payload = urllib.parse.urlencode(
        {k: str(v) for k, v in fields.items()}
    ).encode("utf-8")
    merged = {
        "Zotero-API-Key": api_key,
        "Zotero-API-Version": "3",
        "User-Agent": "zotero-mirror-features/1.0",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=payload, headers=merged, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            status = int(response.status)
            response_headers = {k: v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"ZOTERO_FILE_HTTP_{exc.code}: {detail}") from exc
    parsed: Any = None
    if raw:
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = text
    return status, parsed, response_headers


def _get_object(base: str, user_id: str, api_key: str, route: str) -> dict[str, Any]:
    status, body, _ = _json_request(
        base=base,
        user_id=user_id,
        api_key=api_key,
        method="GET",
        route=route,
    )
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"Unexpected Zotero object response for {route}")
    return body


def _require_version(obj: dict[str, Any], expected: Any, label: str) -> int:
    actual = int(obj.get("version") or (obj.get("data") or {}).get("version") or -1)
    if expected is None:
        raise RuntimeError(
            f"STALE_WRITE_GUARD_MISSING: expected {label} version is required"
        )
    if int(expected) != actual:
        raise RuntimeError(
            f"STALE_WRITE_REJECTED: expected {label} version {expected}, "
            f"current is {actual}"
        )
    return actual


def _created_key(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for name in ("successful", "success"):
        bucket = body.get(name)
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


def validate_saved_search(name: Any, conditions: Any) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise RuntimeError("INVALID_SAVED_SEARCH: name is required")
    if not isinstance(conditions, list) or not conditions:
        raise RuntimeError(
            "INVALID_SAVED_SEARCH: non-empty conditions list is required"
        )

    clean: list[dict[str, str]] = []
    group_depth = 0
    for raw in conditions:
        if not isinstance(raw, dict):
            raise RuntimeError(
                "INVALID_SAVED_SEARCH: each condition must be an object"
            )
        condition = str(raw.get("condition") or "").strip()
        operator = str(raw.get("operator") or "").strip()
        allowed = SEARCH_OPERATORS.get(condition)
        if allowed is None:
            raise RuntimeError(f"UNSUPPORTED_SEARCH_CONDITION: {condition}")
        if operator not in allowed:
            raise RuntimeError(
                f"UNSUPPORTED_SEARCH_OPERATOR: {condition}/{operator}"
            )

        if condition == "groupStart":
            group_depth += 1
        elif condition == "groupEnd":
            group_depth -= 1
            if group_depth < 0:
                raise RuntimeError("INVALID_SAVED_SEARCH: unbalanced groupEnd")

        value = raw.get("value", "")
        clean.append({
            "condition": condition,
            "operator": operator,
            "value": str(value if value is not None else ""),
        })

    if group_depth:
        raise RuntimeError("INVALID_SAVED_SEARCH: unbalanced groups")
    return {"name": clean_name, "conditions": clean}


def _normalize_doi(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(
        r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    return text.casefold() or None


def _arxiv_id(value: Any) -> str | None:
    text = str(value or "")
    patterns = [
        r"10\.48550/arXiv\.([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
        r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(
                r"v\d+$", "", match.group(1), flags=re.IGNORECASE
            ).casefold()
    return None


def _normalize_title(value: Any) -> str:
    return re.sub(r"[^\w]+", "", str(value or "").casefold(), flags=re.UNICODE)


def validate_pdf_identity(
    parent_data: dict[str, Any],
    source_url: str,
    identity: Any,
) -> dict[str, Any]:
    if not isinstance(identity, dict) or identity.get("verified") is not True:
        raise RuntimeError("PDF_IDENTITY_UNVERIFIED")

    matches: list[str] = []
    parent_doi = _normalize_doi(parent_data.get("DOI"))
    supplied_doi = _normalize_doi(identity.get("doi"))
    if parent_doi and supplied_doi and parent_doi == supplied_doi:
        matches.append("doi")

    parent_arxiv = (
        _arxiv_id(parent_data.get("DOI"))
        or _arxiv_id(parent_data.get("url"))
        or _arxiv_id(parent_data.get("extra"))
    )
    supplied_arxiv = _arxiv_id(identity.get("arxiv_id")) or _arxiv_id(source_url)
    if parent_arxiv and supplied_arxiv and parent_arxiv == supplied_arxiv:
        matches.append("arxiv")

    parent_title = _normalize_title(parent_data.get("title"))
    supplied_title = _normalize_title(identity.get("title"))
    if (
        parent_title
        and supplied_title
        and parent_title == supplied_title
        and identity.get("authors_verified") is True
    ):
        matches.append("title+authors")

    if not matches:
        raise RuntimeError(
            "PDF_IDENTITY_MISMATCH: no verified identifier aligns with target item"
        )

    alignment = str(identity.get("version_alignment") or "").strip()
    if not alignment:
        raise RuntimeError("PDF_VERSION_ALIGNMENT_MISSING")

    return {"matches": matches, "version_alignment": alignment}


def _validate_public_https_url(url: str, *, resolve: bool) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise RuntimeError("UNSAFE_PDF_URL: an absolute HTTPS URL is required")
    if parsed.username or parsed.password:
        raise RuntimeError("UNSAFE_PDF_URL: credentials in URLs are forbidden")

    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost":
        raise RuntimeError("UNSAFE_PDF_URL: localhost is forbidden")
    if not resolve:
        return

    port = parsed.port or 443
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise RuntimeError("UNSAFE_PDF_URL: hostname did not resolve")
    for info in infos:
        address = info[4][0].split("%", 1)[0]
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise RuntimeError(f"UNSAFE_PDF_URL: non-public address {ip}")


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_public_https_url(newurl, resolve=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def acquire_public_pdf(source_url: str, policy: dict[str, Any]) -> dict[str, Any]:
    _validate_public_https_url(source_url, resolve=True)
    max_bytes = int(policy.get("max_bytes", 104857600))
    allowed_types = {
        str(x).casefold() for x in policy.get("allowed_content_types", [])
    }

    opener = urllib.request.build_opener(_PublicRedirectHandler())
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "zotero-mirror-pdf/1.0",
            "Accept": "application/pdf,application/octet-stream;q=0.9",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=120) as response:
            final_url = response.geturl()
            _validate_public_https_url(final_url, resolve=True)

            source_content_type = str(
                response.headers.get("Content-Type") or ""
            ).split(";", 1)[0].strip().casefold()
            if source_content_type not in allowed_types:
                raise RuntimeError(
                    "PDF_MIME_REJECTED: " + (source_content_type or "missing")
                )

            raw_name = ""
            disposition = str(response.headers.get("Content-Disposition") or "")
            match = re.search(
                r'filename\*?=(?:UTF-8\'\')?"?([^";]+)',
                disposition,
                flags=re.IGNORECASE,
            )
            if match:
                raw_name = urllib.parse.unquote(match.group(1).strip())
            if not raw_name:
                raw_name = urllib.parse.unquote(
                    PurePosixPath(urllib.parse.urlsplit(final_url).path).name
                )

            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise RuntimeError(
                        f"PDF_TOO_LARGE: exceeds {max_bytes} bytes"
                    )
                chunks.append(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"PDF_DOWNLOAD_HTTP_{exc.code}") from exc

    data = b"".join(chunks)
    if not data or b"%PDF-" not in data[:1024]:
        raise RuntimeError("PDF_MAGIC_REJECTED")

    filename = re.sub(
        r"[^A-Za-z0-9._() -]+", "_", raw_name or "paper.pdf"
    ).strip(" .") or "paper.pdf"
    if not filename.casefold().endswith(".pdf"):
        filename += ".pdf"

    return {
        "bytes": data,
        "source_url": source_url,
        "final_url": final_url,
        "content_type": "application/pdf",
        "source_content_type": source_content_type,
        "filename": filename,
        "size": len(data),
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime": int(time.time() * 1000),
    }


def upload_storage_file(
    *,
    base: str,
    user_id: str,
    api_key: str,
    attachment_key: str,
    pdf: dict[str, Any],
    previous_md5: str | None = None,
) -> dict[str, Any]:
    route = f"/items/{attachment_key}/file"
    precondition_headers = (
        {"If-Match": previous_md5}
        if previous_md5
        else {"If-None-Match": "*"}
    )
    status, authorization, _ = _form_request(
        base=base,
        user_id=user_id,
        api_key=api_key,
        route=route,
        fields={
            "md5": pdf["md5"],
            "filename": pdf["filename"],
            "filesize": pdf["size"],
            "mtime": pdf["mtime"],
        },
        headers=precondition_headers,
    )
    if status != 200 or not isinstance(authorization, dict):
        raise RuntimeError("FILE_UPLOAD_AUTH_INVALID")
    if authorization.get("exists") == 1:
        return {"status": "already_exists", "registered": True}

    required = {"url", "contentType", "prefix", "suffix", "uploadKey"}
    missing = sorted(required - set(authorization))
    if missing:
        raise RuntimeError("FILE_UPLOAD_AUTH_MISSING: " + ", ".join(missing))

    upload_url = str(authorization["url"])
    _validate_public_https_url(upload_url, resolve=True)
    binary_body = (
        str(authorization["prefix"]).encode("utf-8")
        + pdf["bytes"]
        + str(authorization["suffix"]).encode("utf-8")
    )
    request = urllib.request.Request(
        upload_url,
        data=binary_body,
        headers={
            "Content-Type": str(authorization["contentType"]),
            "User-Agent": "zotero-mirror-pdf/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            upload_status = int(response.status)
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"FILE_BINARY_UPLOAD_HTTP_{exc.code}: {detail}"
        ) from exc
    if upload_status != 201:
        raise RuntimeError(f"FILE_BINARY_UPLOAD_STATUS_{upload_status}")

    register_status, _, register_headers = _form_request(
        base=base,
        user_id=user_id,
        api_key=api_key,
        route=route,
        fields={"upload": authorization["uploadKey"]},
        headers=precondition_headers,
    )
    if register_status != 204:
        raise RuntimeError(f"FILE_REGISTER_STATUS_{register_status}")

    return {
        "status": "uploaded",
        "registered": True,
        "zotero_library_version": (
            register_headers.get("Zotero-Library-Version")
            or register_headers.get("Last-Modified-Version")
        ),
    }


def _minimal_csl(
    parent_data: dict[str, Any],
    user_id: str,
    item_key: str,
) -> dict[str, Any]:
    csl_type = {
        "journalArticle": "article-journal",
        "conferencePaper": "paper-conference",
        "preprint": "article",
        "book": "book",
        "bookSection": "chapter",
        "thesis": "thesis",
        "report": "report",
    }.get(str(parent_data.get("itemType") or ""), "article")
    result: dict[str, Any] = {
        "id": f"http://zotero.org/users/{user_id}/items/{item_key}",
        "type": csl_type,
        "title": str(parent_data.get("title") or ""),
    }

    authors: list[dict[str, str]] = []
    for creator in parent_data.get("creators") or []:
        if not isinstance(creator, dict):
            continue
        if creator.get("creatorType") not in {None, "", "author"}:
            continue
        if creator.get("name"):
            authors.append({"literal": str(creator["name"])})
            continue
        author: dict[str, str] = {}
        if creator.get("lastName"):
            author["family"] = str(creator["lastName"])
        if creator.get("firstName"):
            author["given"] = str(creator["firstName"])
        if author:
            authors.append(author)
    if authors:
        result["author"] = authors

    if parent_data.get("DOI"):
        result["DOI"] = str(parent_data["DOI"])
    if parent_data.get("url"):
        result["URL"] = str(parent_data["url"])

    year = re.search(r"\b(\d{4})\b", str(parent_data.get("date") or ""))
    if year:
        result["issued"] = {"date-parts": [[int(year.group(1))]]}
    return result


def _encode_json(value: Any) -> str:
    return urllib.parse.quote(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        safe="",
    )


def _annotation_position(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        position = value
    else:
        try:
            position = json.loads(str(value or ""))
        except json.JSONDecodeError as exc:
            raise RuntimeError("ANNOTATION_POSITION_INVALID") from exc
    if (
        not isinstance(position, dict)
        or not isinstance(position.get("pageIndex"), int)
    ):
        raise RuntimeError("ANNOTATION_POSITION_INVALID")
    return position


def build_partial_rich_note_html(
    *,
    annotations: list[dict[str, Any]],
    parent_data: dict[str, Any],
    parent_key: str,
    user_id: str,
) -> str:
    """Serialize existing highlights/underlines with Zotero navigation metadata."""
    parent_uri = f"http://zotero.org/users/{user_id}/items/{parent_key}"
    item_data = _minimal_csl(parent_data, user_id, parent_key)
    stored_citation_items = [{"uris": [parent_uri], "itemData": item_data}]
    schema_version = 10 if any(
        str((obj.get("data") or {}).get("annotationType") or "") == "underline"
        for obj in annotations
    ) else 9

    paragraphs: list[str] = []
    for obj in annotations:
        data = obj.get("data") or {}
        annotation_type = str(data.get("annotationType") or "")
        if annotation_type not in {"highlight", "underline"}:
            raise RuntimeError(
                "ANNOTATION_NOTE_UNSUPPORTED_TYPE: "
                f"{annotation_type}; only existing highlight/underline "
                "annotations are promoted with rich linkage"
            )

        text = str(data.get("annotationText") or "").strip()
        comment = str(data.get("annotationComment") or "").strip()
        if not text and not comment:
            continue

        attachment_key = str(data.get("parentItem") or "")
        annotation_key = str(obj.get("key") or data.get("key") or "")
        if not attachment_key or not annotation_key:
            raise RuntimeError("ANNOTATION_IDENTITY_INVALID")

        page_label = str(data.get("annotationPageLabel") or "")
        position = _annotation_position(data.get("annotationPosition"))
        citation_item = {"uris": [parent_uri], "locator": page_label}
        stored_annotation = {
            "attachmentURI": (
                f"http://zotero.org/users/{user_id}/items/{attachment_key}"
            ),
            "annotationKey": annotation_key,
            "color": str(data.get("annotationColor") or ""),
            "pageLabel": page_label,
            "position": position,
            "citationItem": citation_item,
        }
        citation = {"citationItems": [citation_item], "properties": {}}
        rich_text = (
            f'<span class="{html.escape(annotation_type)}" '
            f'data-annotation="{_encode_json(stored_annotation)}">'
            f'“{html.escape(text)}”</span>'
            if text
            else ""
        )
        citation_html = (
            '<span class="citation" '
            f'data-citation="{_encode_json(citation)}">'
            '<span class="citation-item">'
            f'p. {html.escape(page_label or "?")}'
            '</span></span>'
        )
        body = " ".join(part for part in (rich_text, citation_html) if part)
        if comment:
            body += "<br/>" + html.escape(comment)
        paragraphs.append("<p>" + body + "</p>")

    if not paragraphs:
        raise RuntimeError("ANNOTATION_NOTE_EMPTY")

    return (
        f'<div data-citation-items="{_encode_json(stored_citation_items)}" '
        f'data-schema-version="{schema_version}">'
        + "".join(paragraphs)
        + "</div>"
    )


def _build_annotation_item_from_source(
    *,
    attachment_key: str,
    source_annotation: dict[str, Any],
    annotation_type: str,
    comment: str,
    color: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an annotation item from already trusted geometry.

    This path deliberately does not derive coordinates from text.
    It copies exact page geometry and ordering metadata from one existing
    annotation on the same attachment.
    """
    source_data = source_annotation.get("data") or {}
    source_key = str(
        source_annotation.get("key") or source_data.get("key") or ""
    )
    if source_data.get("itemType") != "annotation" or not source_key:
        raise RuntimeError("ANNOTATION_PROBE_SOURCE_INVALID")
    if str(source_data.get("parentItem") or "") != attachment_key:
        raise RuntimeError("ANNOTATION_PROBE_SOURCE_PARENT_MISMATCH")

    position = _annotation_position(source_data.get("annotationPosition"))
    page_label = str(source_data.get("annotationPageLabel") or "").strip()
    sort_index = str(source_data.get("annotationSortIndex") or "").strip()
    if not page_label or not sort_index:
        raise RuntimeError("ANNOTATION_PROBE_SOURCE_POSITION_METADATA_MISSING")

    if annotation_type not in {"note", "underline", "highlight"}:
        raise RuntimeError(
            "ANNOTATION_CREATE_UNSUPPORTED_TYPE: "
            "only note/highlight/underline are allowed"
        )
    clean_comment = str(comment or "").strip()
    if not clean_comment:
        raise RuntimeError("ANNOTATION_PROBE_COMMENT_REQUIRED")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise RuntimeError("ANNOTATION_PROBE_COLOR_INVALID")

    item: dict[str, Any] = {
        "itemType": "annotation",
        "parentItem": attachment_key,
        "annotationType": annotation_type,
        "annotationComment": clean_comment,
        "annotationColor": color,
        "annotationPageLabel": page_label,
        "annotationSortIndex": sort_index,
        "annotationPosition": json.dumps(
            position, ensure_ascii=False, separators=(",", ":")
        ),
        "tags": [],
        "relations": {},
    }
    if annotation_type in {"highlight", "underline"}:
        source_text = str(source_data.get("annotationText") or "").strip()
        if not source_text:
            raise RuntimeError("ANNOTATION_PROBE_SOURCE_TEXT_MISSING")
        item["annotationText"] = source_text

    audit = {
        "contract_status": "UNDOCUMENTED_BUT_LIVE_VERIFIED_WEB_API_WRITE",
        "source_annotation_key": source_key,
        "geometry_source": "existing_synchronized_annotation",
        "page_label": page_label,
        "position": position,
        "sort_index": sort_index,
    }
    return item, audit


def execute_extended_operation(
    *,
    operation: str,
    request: dict[str, Any],
    base: str,
    user_id: str,
    api_key: str,
    before_library_version: int,
    pdf_policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    target = request.get("target") or {}
    payload = request.get("payload") or {}
    expected = request.get("expected") or {}

    if operation == "create_saved_search":
        search = validate_saved_search(
            payload.get("name"), payload.get("conditions")
        )
        status, body, headers = _json_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="POST",
            route="/searches",
            body=[search],
            headers={
                "If-Unmodified-Since-Version": str(before_library_version)
            },
        )
        if status != 200:
            raise RuntimeError(f"SAVED_SEARCH_CREATE_STATUS_{status}")
        key = _created_key(body)
        if not key:
            raise RuntimeError("SAVED_SEARCH_CREATE_KEY_MISSING")
        return ({
            "http_status": status,
            "created_search_key": key,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }, {"search": search})

    if operation == "patch_saved_search":
        key = str(target.get("search_key") or "")
        if not key:
            raise RuntimeError("INVALID_REQUEST: target.search_key is required")
        current = _get_object(base, user_id, api_key, f"/searches/{key}")
        version = _require_version(
            current, expected.get("search_version"), "search"
        )
        data = current.get("data") or {}
        search = validate_saved_search(
            payload.get("name", data.get("name")),
            payload.get("conditions", data.get("conditions")),
        )
        update = {"key": key, "version": version, **search}
        status, body, headers = _json_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="POST",
            route="/searches",
            body=[update],
        )
        if status != 200:
            raise RuntimeError(f"SAVED_SEARCH_PATCH_STATUS_{status}")
        return ({
            "http_status": status,
            "search_key": key,
            "response": body,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }, {"search": search})

    if operation == "delete_saved_search":
        key = str(target.get("search_key") or "")
        if not key:
            raise RuntimeError("INVALID_REQUEST: target.search_key is required")
        current = _get_object(base, user_id, api_key, f"/searches/{key}")
        _require_version(current, expected.get("search_version"), "search")
        route = "/searches?" + urllib.parse.urlencode({"searchKey": key})
        status, body, headers = _json_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="DELETE",
            route=route,
            headers={
                "If-Unmodified-Since-Version": str(before_library_version)
            },
        )
        if status != 204:
            raise RuntimeError(f"SAVED_SEARCH_DELETE_STATUS_{status}")
        return ({
            "http_status": status,
            "deleted_search_key": key,
            "response": body,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }, None)

    if operation == "create_annotation":
        attachment_key = str(target.get("attachment_key") or "")
        source_key = str(target.get("source_annotation_key") or "")
        if not attachment_key or not source_key:
            raise RuntimeError(
                "INVALID_REQUEST: target.attachment_key and "
                "target.source_annotation_key are required"
            )

        attachment = _get_object(
            base, user_id, api_key, f"/items/{attachment_key}"
        )
        _require_version(
            attachment,
            expected.get("attachment_version"),
            "attachment",
        )
        attachment_data = attachment.get("data") or {}
        if attachment_data.get("itemType") != "attachment":
            raise RuntimeError("ANNOTATION_PROBE_PARENT_NOT_ATTACHMENT")
        if str(attachment_data.get("contentType") or "") != "application/pdf":
            raise RuntimeError("ANNOTATION_PROBE_PARENT_NOT_PDF")

        source = _get_object(base, user_id, api_key, f"/items/{source_key}")
        _require_version(
            source,
            expected.get("source_annotation_version"),
            "source annotation",
        )

        annotation_type = str(payload.get("annotation_type") or "note")
        color = str(payload.get("color") or "#ffd400")
        item, audit = _build_annotation_item_from_source(
            attachment_key=attachment_key,
            source_annotation=source,
            annotation_type=annotation_type,
            comment=str(payload.get("comment") or ""),
            color=color,
        )
        status, body, headers = _json_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="POST",
            route="/items",
            body=[item],
            headers={
                "If-Unmodified-Since-Version": str(before_library_version)
            },
        )
        if status != 200:
            raise RuntimeError(f"ANNOTATION_PROBE_CREATE_STATUS_{status}")
        created_key = _created_key(body)
        if not created_key:
            raise RuntimeError("ANNOTATION_PROBE_CREATE_KEY_MISSING")

        return ({
            "http_status": status,
            "created_item_key": created_key,
            "attachment_key": attachment_key,
            "annotation_type": annotation_type,
            "annotation_comment": str(payload.get("comment") or "").strip(),
            "annotation_color": color,
            "source_annotation_key": source_key,
            "last_modified_version": headers.get("Last-Modified-Version"),
        }, audit)

    if operation == "patch_annotation_comment":
        annotation_key = str(target.get("annotation_key") or "")
        if not annotation_key:
            raise RuntimeError(
                "INVALID_REQUEST: target.annotation_key is required"
            )
        current = _get_object(
            base, user_id, api_key, f"/items/{annotation_key}"
        )
        current_version = _require_version(
            current,
            expected.get("annotation_version"),
            "annotation",
        )
        data = current.get("data") or {}
        if data.get("itemType") != "annotation":
            raise RuntimeError("TARGET_NOT_ANNOTATION")
        comment = str(payload.get("comment") or "").strip()
        if not comment:
            raise RuntimeError("ANNOTATION_COMMENT_REQUIRED")
        status, body, headers = _json_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="PATCH",
            route=f"/items/{annotation_key}",
            body={"annotationComment": comment},
            headers={
                "If-Unmodified-Since-Version": str(current_version)
            },
        )
        if status not in {200, 204}:
            raise RuntimeError(
                f"ANNOTATION_COMMENT_PATCH_STATUS_{status}"
            )
        return ({
            "http_status": status,
            "annotation_key": annotation_key,
            "annotation_comment": comment,
            "attachment_key": str(data.get("parentItem") or ""),
            "last_modified_version": headers.get("Last-Modified-Version"),
        }, {
            "contract_status":
                "UNDOCUMENTED_BUT_LIVE_VERIFIED_WEB_API_WRITE"
        })

    if operation == "create_annotation_note":
        parent_key = str(target.get("parent_item_key") or "")
        annotation_keys = [
            str(x)
            for x in (target.get("annotation_keys") or [])
            if str(x)
        ]
        if not parent_key or not annotation_keys:
            raise RuntimeError(
                "INVALID_REQUEST: target.parent_item_key and "
                "target.annotation_keys are required"
            )

        parent = _get_object(base, user_id, api_key, f"/items/{parent_key}")
        _require_version(
            parent, expected.get("parent_item_version"), "parent item"
        )
        parent_data = parent.get("data") or {}
        expected_versions = expected.get("annotation_versions") or {}
        annotations: list[dict[str, Any]] = []

        for key in annotation_keys:
            annotation = _get_object(
                base, user_id, api_key, f"/items/{key}"
            )
            data = annotation.get("data") or {}
            if data.get("itemType") != "annotation":
                raise RuntimeError(f"TARGET_NOT_ANNOTATION: {key}")
            _require_version(
                annotation, expected_versions.get(key), f"annotation {key}"
            )
            attachment_key = str(data.get("parentItem") or "")
            attachment = _get_object(
                base, user_id, api_key, f"/items/{attachment_key}"
            )
            attachment_data = attachment.get("data") or {}
            if str(attachment_data.get("parentItem") or "") != parent_key:
                raise RuntimeError(f"ANNOTATION_PARENT_MISMATCH: {key}")
            annotations.append(annotation)

        note_html = build_partial_rich_note_html(
            annotations=annotations,
            parent_data=parent_data,
            parent_key=parent_key,
            user_id=user_id,
        )
        note = {
            "itemType": "note",
            "parentItem": parent_key,
            "note": note_html,
            "tags": [],
        }
        status, body, headers = _json_request(
            base=base,
            user_id=user_id,
            api_key=api_key,
            method="POST",
            route="/items",
            body=[note],
            headers={
                "If-Unmodified-Since-Version": str(before_library_version)
            },
        )
        if status != 200:
            raise RuntimeError(f"ANNOTATION_NOTE_CREATE_STATUS_{status}")
        note_key = _created_key(body)
        if not note_key:
            raise RuntimeError("ANNOTATION_NOTE_CREATE_KEY_MISSING")

        return ({
            "http_status": status,
            "created_item_key": note_key,
            "parent_item_key": parent_key,
            "source_annotation_keys": annotation_keys,
            "richness": "PARTIAL_RICH_NOTE",
            "last_modified_version": headers.get("Last-Modified-Version"),
        }, {
            "richness": "PARTIAL_RICH_NOTE",
            "reason": (
                "The Web API writes note HTML, while Zotero documents no "
                "server-side Add Note from Annotations endpoint. The generated "
                "HTML mirrors the current Desktop data-annotation/data-citation "
                "structure and is not claimed FULL_NATIVE."
            ),
        })

    if operation == "upload_pdf":
        parent_key = str(target.get("parent_item_key") or "")
        source_url = str(payload.get("source_url") or "").strip()
        if not parent_key or not source_url:
            raise RuntimeError(
                "INVALID_REQUEST: target.parent_item_key and "
                "payload.source_url are required"
            )

        parent = _get_object(base, user_id, api_key, f"/items/{parent_key}")
        _require_version(
            parent, expected.get("parent_item_version"), "parent item"
        )
        parent_data = parent.get("data") or {}
        if parent_data.get("itemType") in {
            "attachment", "note", "annotation"
        }:
            raise RuntimeError("PDF_PARENT_NOT_BIBLIOGRAPHIC")

        identity_audit = validate_pdf_identity(
            parent_data, source_url, payload.get("identity")
        )
        pdf = acquire_public_pdf(source_url, pdf_policy)

        requested_name = str(payload.get("filename") or "").strip()
        if requested_name:
            requested_name = re.sub(
                r"[^A-Za-z0-9._() -]+", "_", requested_name
            ).strip(" .")
            if not requested_name.casefold().endswith(".pdf"):
                requested_name += ".pdf"
            pdf["filename"] = requested_name

        existing_attachment_key = str(target.get("attachment_key") or "")
        attachment_mode = "created"
        attachment_create_version: str | None = None
        attachment_version_before: int | None = None
        previous_md5: str | None = None

        if existing_attachment_key:
            current_attachment = _get_object(
                base, user_id, api_key, f"/items/{existing_attachment_key}"
            )
            attachment_version_before = _require_version(
                current_attachment,
                expected.get("attachment_version"),
                "attachment",
            )
            attachment_data = current_attachment.get("data") or {}
            if attachment_data.get("itemType") != "attachment":
                raise RuntimeError("PDF_TARGET_NOT_ATTACHMENT")
            if str(attachment_data.get("parentItem") or "") != parent_key:
                raise RuntimeError("PDF_ATTACHMENT_PARENT_MISMATCH")
            if str(attachment_data.get("linkMode") or "") not in {
                "imported_file", "imported_url"
            }:
                raise RuntimeError("PDF_ATTACHMENT_NOT_STORED_FILE")
            if str(attachment_data.get("contentType") or "") != "application/pdf":
                raise RuntimeError("PDF_ATTACHMENT_CONTENT_TYPE_MISMATCH")

            previous_md5 = str(attachment_data.get("md5") or "").strip()
            if not previous_md5:
                raise RuntimeError("PDF_EXISTING_MD5_MISSING")
            if (
                payload.get("require_existing_md5_match") is True
                and pdf["md5"] != previous_md5
            ):
                raise RuntimeError(
                    "PDF_EXISTING_MD5_MISMATCH: downloaded bytes differ from "
                    "the current stored attachment; refusing replacement"
                )
            if not requested_name and attachment_data.get("filename"):
                pdf["filename"] = str(attachment_data["filename"])

            attachment_key = existing_attachment_key
            attachment_mode = "existing"
        else:
            attachment = {
                "itemType": "attachment",
                "parentItem": parent_key,
                "linkMode": "imported_file",
                "title": str(payload.get("title") or pdf["filename"]),
                "accessDate": "",
                "url": pdf["final_url"],
                "note": "",
                "tags": [],
                "relations": {},
                "contentType": "application/pdf",
                "charset": "",
                "filename": pdf["filename"],
            }
            status, body, headers = _json_request(
                base=base,
                user_id=user_id,
                api_key=api_key,
                method="POST",
                route="/items",
                body=[attachment],
                headers={
                    "If-Unmodified-Since-Version": str(before_library_version)
                },
            )
            if status != 200:
                raise RuntimeError(f"ATTACHMENT_CREATE_STATUS_{status}")
            attachment_key = _created_key(body)
            if not attachment_key:
                raise RuntimeError("ATTACHMENT_CREATE_KEY_MISSING")
            attachment_create_version = headers.get("Last-Modified-Version")

        partial = {
            "parent_item_key": parent_key,
            "attachment_key": attachment_key,
            "attachment_mode": attachment_mode,
            "source_url": source_url,
            "final_url": pdf["final_url"],
            "content_type": "application/pdf",
            "size": pdf["size"],
            "checksum": {
                "md5": pdf["md5"],
                "sha256": pdf["sha256"],
            },
            "attachment_create_version": attachment_create_version,
            "attachment_version_before": attachment_version_before,
            "previous_md5": previous_md5,
        }
        try:
            upload_result = upload_storage_file(
                base=base,
                user_id=user_id,
                api_key=api_key,
                attachment_key=attachment_key,
                pdf=pdf,
                previous_md5=previous_md5,
            )
        except Exception as exc:
            if existing_attachment_key:
                raise RuntimeError(
                    f"PDF_EXISTING_UPLOAD_FAILURE: {exc}"
                ) from exc
            raise PartialWriteError(
                f"PDF_UPLOAD_PARTIAL_FAILURE: {exc}",
                {
                    **partial,
                    "upload_result": "failed",
                    "cleanup_required": True,
                },
            ) from exc

        return ({
            **partial,
            "upload_result": upload_result,
        }, {
            "identity": identity_audit,
            "provenance": payload.get("provenance") or {},
            "source_content_type": pdf["source_content_type"],
        })

    raise RuntimeError(f"UNSUPPORTED_EXTENDED_OPERATION: {operation}")
