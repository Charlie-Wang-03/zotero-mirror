#!/usr/bin/env python3
"""Mirror a Zotero personal library into deterministic, AI-friendly files.

Read-only with respect to Zotero. The script uses only Python's standard library.
It mirrors metadata, notes, attachment metadata, annotations, and any full-text
content already synchronized to zotero.org. It never uploads or modifies Zotero.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

API_BASE = os.environ.get("ZOTERO_API_BASE", "https://api.zotero.org").rstrip("/")
USER_ID = os.environ.get("ZOTERO_USER_ID", "").strip()
API_KEY = os.environ.get("ZOTERO_API_KEY", "").strip()
OUTPUT_DIR = Path(os.environ.get("ZOTERO_OUTPUT_DIR", "library"))
PAGE_SIZE = 100
USER_AGENT = "zotero-mirror/2.0 (+https://github.com/Charlie-Wang-03/zotero-mirror)"
NON_BIB_TYPES = {"attachment", "note", "annotation"}


class PlainTextHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "br", "li", "ul", "ol", "blockquote", "pre",
        "h1", "h2", "h3", "h4", "h5", "h6", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts))
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n[ \t]+", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def note_html_to_text(value: str) -> str:
    parser = PlainTextHTMLParser()
    parser.feed(value or "")
    parser.close()
    return parser.text()


def request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    allow_404: bool = False,
) -> tuple[bytes | None, Any]:
    if not API_KEY:
        raise RuntimeError("ZOTERO_API_KEY is required")
    if not USER_ID or not USER_ID.isdigit():
        raise RuntimeError("ZOTERO_USER_ID must be configured as a numeric Zotero user ID")

    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{query}"

    req = urllib.request.Request(
        url,
        headers={
            "Zotero-API-Key": API_KEY,
            "Zotero-API-Version": "3",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )

    retries = 5
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                body = response.read()
                headers = response.headers
                backoff = headers.get("Backoff")
                if backoff:
                    try:
                        time.sleep(float(backoff))
                    except ValueError:
                        pass
                return body, headers
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_404:
                return None, exc.headers
            retry_after = exc.headers.get("Retry-After")
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                delay = float(retry_after) if retry_after else 2**attempt
                time.sleep(delay)
                continue
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Zotero API request failed: HTTP {exc.code}: {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"Zotero API request failed: {exc}") from exc

    raise RuntimeError("Zotero API request failed after retries")


def request_json(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    allow_404: bool = False,
) -> tuple[Any | None, Any]:
    body, headers = request(path, params, allow_404=allow_404)
    if body is None:
        return None, headers
    return json.loads(body.decode("utf-8")), headers


def fetch_json_pages(
    path: str,
    params: dict[str, Any] | None = None,
) -> tuple[list[Any], int | None]:
    base = dict(params or {})
    start = 0
    rows: list[Any] = []
    library_version: int | None = None

    while True:
        page_params = {**base, "start": start, "limit": PAGE_SIZE}
        page, headers = request_json(path, page_params)
        if not isinstance(page, list):
            raise RuntimeError(f"Expected list response from {path}")

        version_header = headers.get("Last-Modified-Version")
        if version_header and str(version_header).isdigit():
            library_version = int(version_header)

        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        start += len(page)

    return rows, library_version


def fetch_bibtex_pages(path: str) -> str:
    start = 0
    chunks: list[str] = []

    while True:
        body, headers = request(
            path,
            {"start": start, "limit": PAGE_SIZE, "format": "bibtex"},
        )
        assert body is not None
        text = body.decode("utf-8").strip()
        if text:
            chunks.append(text)

        total_header = headers.get("Total-Results")
        total = int(total_header) if total_header and str(total_header).isdigit() else None
        start += PAGE_SIZE

        if total is not None:
            if start >= total:
                break
        elif not text:
            break

    return "\n\n".join(chunks).strip() + ("\n" if chunks else "")


def year_from_item(data: dict[str, Any], meta: dict[str, Any]) -> str | None:
    parsed = str(meta.get("parsedDate") or "")
    match = re.search(r"\b(\d{4})\b", parsed)
    if match:
        return match.group(1)
    raw = str(data.get("date") or "")
    match = re.search(r"\b(\d{4})\b", raw)
    return match.group(1) if match else None


def normalize_creators(creators: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for creator in creators or []:
        entry = {"creatorType": str(creator.get("creatorType") or "")}
        if creator.get("name"):
            entry["name"] = str(creator["name"])
        else:
            if creator.get("firstName"):
                entry["firstName"] = str(creator["firstName"])
            if creator.get("lastName"):
                entry["lastName"] = str(creator["lastName"])
        result.append(entry)
    return result


def normalize_tags(tags: list[dict[str, Any]]) -> list[str]:
    values = {str(tag.get("tag") or "").strip() for tag in tags or []}
    return sorted(value for value in values if value)


def build_collection_maps(
    raw_collections: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    by_key: dict[str, dict[str, Any]] = {}
    names: dict[str, str] = {}

    for collection in raw_collections:
        data = collection.get("data") or {}
        key = str(collection.get("key") or data.get("key") or "")
        if not key:
            continue
        by_key[key] = data
        names[key] = str(data.get("name") or key)

    paths: dict[str, str] = {}

    def resolve(key: str, stack: tuple[str, ...] = ()) -> str:
        if key in paths:
            return paths[key]
        if key in stack:
            return names.get(key, key)
        data = by_key.get(key)
        if not data:
            return names.get(key, key)
        name = names.get(key, key)
        parent = data.get("parentCollection")
        value = (
            f"{resolve(str(parent), stack + (key,))} / {name}"
            if parent
            else name
        )
        paths[key] = value
        return value

    for key in by_key:
        resolve(key)

    return names, paths


def parse_bibtex_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"@\w+\s*\{\s*([^,\s]+)", value)
    return match.group(1).strip() if match else None


def infer_arxiv_id(data: dict[str, Any]) -> str | None:
    candidates = [
        str(data.get("DOI") or ""),
        str(data.get("url") or ""),
        str(data.get("extra") or ""),
    ]
    patterns = [
        r"10\.48550/arXiv\.([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
        r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
    ]
    for candidate in candidates:
        for pattern in patterns:
            match = re.search(pattern, candidate, flags=re.IGNORECASE)
            if match:
                return match.group(1)
    return None


def build_web_resolution(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    doi = str(data.get("DOI") or "").strip()
    source_url = str(data.get("url") or "").strip()
    arxiv_id = infer_arxiv_id(data)

    result: dict[str, Any] = {
        "exactTitleQuery": f'"{title}"' if title else None,
        "preferredDeepReadingOrder": [
            "canonical publisher/proceedings page resolved from DOI or official URL",
            "canonical arXiv/OpenReview/proceedings PDF when applicable",
            "author/institutional open-access copy",
            "mirrored Zotero indexed full text as fallback",
        ],
    }
    if doi:
        result["doi"] = doi
        result["doiUrl"] = f"https://doi.org/{doi}"
    if arxiv_id:
        result["arxivId"] = arxiv_id
        result["arxivAbsUrl"] = f"https://arxiv.org/abs/{arxiv_id}"
        result["arxivPdfUrl"] = f"https://arxiv.org/pdf/{arxiv_id}"
    if source_url:
        result["sourceUrl"] = source_url

    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def normalize_item(
    item: dict[str, Any],
    collection_names: dict[str, str],
    collection_paths: dict[str, str],
) -> dict[str, Any]:
    data = item.get("data") or {}
    meta = item.get("meta") or {}
    collection_keys = sorted(str(x) for x in (data.get("collections") or []))

    fields = [
        "title", "itemType", "date", "publicationTitle", "proceedingsTitle",
        "bookTitle", "university", "publisher", "place", "volume", "issue",
        "pages", "DOI", "ISBN", "ISSN", "url", "abstractNote", "language",
        "rights", "shortTitle", "archive", "archiveLocation", "libraryCatalog",
        "extra", "dateAdded", "dateModified",
    ]

    result: dict[str, Any] = {
        "key": str(item.get("key") or data.get("key") or ""),
        "version": int(item.get("version") or data.get("version") or 0),
        "year": year_from_item(data, meta),
        "creators": normalize_creators(data.get("creators") or []),
        "tags": normalize_tags(data.get("tags") or []),
        "collections": collection_keys,
        "collectionNames": sorted(
            {collection_names.get(key, key) for key in collection_keys}
        ),
        "collectionPaths": sorted(
            {
                collection_paths.get(key, collection_names.get(key, key))
                for key in collection_keys
            }
        ),
    }

    for field in fields:
        value = data.get(field)
        if value not in (None, "", [], {}):
            result[field] = value

    if meta.get("creatorSummary"):
        result["creatorSummary"] = meta["creatorSummary"]
    if meta.get("parsedDate"):
        result["parsedDate"] = meta["parsedDate"]

    web_resolution = build_web_resolution(data)
    if web_resolution:
        result["webResolution"] = web_resolution

    bibtex_key = parse_bibtex_key(item.get("bibtex"))
    if bibtex_key:
        result["bibtexKey"] = bibtex_key

    relations = data.get("relations")
    if relations:
        result["relations"] = relations

    return result


def classify_note(text: str) -> str:
    if text.startswith("chartero#"):
        return "plugin_chartero"
    if re.match(r'^[A-Z0-9]{8}\n\{"readingTime":', text):
        return "plugin_reading_time"
    if text.startswith("Welcome to Better Notes"):
        return "plugin_better_notes_guide"
    if text.startswith("Comment:"):
        return "source_comment"
    return "ai_relevant"


def normalize_note(
    item: dict[str, Any],
    parent_titles: dict[str, str],
) -> dict[str, Any]:
    data = item.get("data") or {}
    note_html = str(data.get("note") or "")
    note_text = note_html_to_text(note_html)
    parent = data.get("parentItem") or None
    return {
        "key": str(item.get("key") or data.get("key") or ""),
        "version": int(item.get("version") or data.get("version") or 0),
        "parentItem": parent,
        "parentTitle": parent_titles.get(str(parent)) if parent else None,
        "category": classify_note(note_text),
        "noteText": note_text,
        "noteHtml": note_html,
        "tags": normalize_tags(data.get("tags") or []),
        "dateAdded": data.get("dateAdded") or None,
        "dateModified": data.get("dateModified") or None,
    }


def normalize_attachment(
    item: dict[str, Any],
    parent_titles: dict[str, str],
) -> dict[str, Any]:
    data = item.get("data") or {}
    parent = data.get("parentItem") or None
    fields = [
        "title", "linkMode", "contentType", "charset", "filename", "url",
        "accessDate", "note", "md5", "mtime", "dateAdded", "dateModified",
    ]
    result: dict[str, Any] = {
        "key": str(item.get("key") or data.get("key") or ""),
        "version": int(item.get("version") or data.get("version") or 0),
        "parentItem": parent,
        "parentTitle": parent_titles.get(str(parent)) if parent else None,
        "tags": normalize_tags(data.get("tags") or []),
    }
    for field in fields:
        value = data.get(field)
        if value not in (None, "", [], {}):
            result[field] = value
    return result


def normalize_annotation(
    item: dict[str, Any],
    attachment_map: dict[str, dict[str, Any]],
    item_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data = item.get("data") or {}
    attachment_key = str(data.get("parentItem") or "")
    attachment = attachment_map.get(attachment_key) or {}
    parent_item = attachment.get("parentItem")
    parent_title = item_map.get(str(parent_item), {}).get("title") if parent_item else None

    fields = [
        "annotationType", "annotationText", "annotationComment",
        "annotationColor", "annotationPageLabel", "annotationSortIndex",
        "annotationPosition", "annotationAuthorName", "dateAdded", "dateModified",
    ]
    result: dict[str, Any] = {
        "key": str(item.get("key") or data.get("key") or ""),
        "version": int(item.get("version") or data.get("version") or 0),
        "attachmentKey": attachment_key or None,
        "parentItem": parent_item,
        "parentTitle": parent_title,
        "tags": normalize_tags(data.get("tags") or []),
    }
    for field in fields:
        value = data.get(field)
        if value not in (None, "", [], {}):
            result[field] = value
    return result


def normalize_collection(collection: dict[str, Any], path: str | None) -> dict[str, Any]:
    data = collection.get("data") or {}
    return {
        "key": str(collection.get("key") or data.get("key") or ""),
        "version": int(collection.get("version") or data.get("version") or 0),
        "name": str(data.get("name") or ""),
        "path": path,
        "parentCollection": data.get("parentCollection") or None,
    }


def normalize_search(search: dict[str, Any]) -> dict[str, Any]:
    data = search.get("data") or {}
    return {
        "key": str(search.get("key") or data.get("key") or ""),
        "version": int(search.get("version") or data.get("version") or 0),
        "name": str(data.get("name") or ""),
        "conditions": data.get("conditions") or [],
    }


def normalize_tag(tag: dict[str, Any]) -> dict[str, Any]:
    meta = tag.get("meta") or {}
    result: dict[str, Any] = {"tag": str(tag.get("tag") or "")}
    if tag.get("type") is not None:
        result["type"] = int(tag["type"])
    if "numItems" in meta:
        result["numItems"] = meta["numItems"]
    return result


def creator_display(creators: list[dict[str, str]]) -> str:
    values: list[str] = []
    for creator in creators:
        if creator.get("name"):
            values.append(creator["name"])
        else:
            value = " ".join(
                x for x in (
                    creator.get("firstName", ""),
                    creator.get("lastName", ""),
                )
                if x
            ).strip()
            if value:
                values.append(value)
    if not values:
        return "Unknown creator"
    if len(values) <= 3:
        return ", ".join(values)
    return f"{', '.join(values[:3])}, et al."


def markdown_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().replace("|", "\\|")


def render_catalog(items: list[dict[str, Any]]) -> str:
    ordered = sorted(
        items,
        key=lambda item: (
            -(int(item["year"]) if str(item.get("year") or "").isdigit() else 0),
            str(item.get("title") or "").casefold(),
            item["key"],
        ),
    )
    lines = [
        "# Zotero Library Catalog",
        "",
        "Generated from the Zotero Web API. Zotero is the canonical source of truth.",
        "",
    ]
    for item in ordered:
        title = markdown_inline(str(item.get("title") or "(untitled)"))
        creators = markdown_inline(creator_display(item.get("creators") or []))
        year = item.get("year") or "n.d."
        details = [f"{creators} ({year})"]
        if item.get("DOI"):
            details.append(f"DOI: {markdown_inline(str(item['DOI']))}")
        if item.get("bibtexKey"):
            details.append(f"BibTeX: `{item['bibtexKey']}`")
        if item.get("collectionPaths"):
            details.append(
                "Collections: " + "; ".join(
                    markdown_inline(x) for x in item["collectionPaths"]
                )
            )
        if item.get("tags"):
            details.append("Tags: " + ", ".join(markdown_inline(x) for x in item["tags"]))
        lines.append(
            f"- **{title}** — {'; '.join(details)} — Zotero key: `{item['key']}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_web_sources(
    items: list[dict[str, Any]],
    attachments_by_parent: dict[str, list[dict[str, Any]]],
) -> str:
    ordered = sorted(
        items,
        key=lambda item: str(item.get("title") or "").casefold(),
    )
    lines = [
        "# Web Resolution Index",
        "",
        "Use Zotero metadata to identify the paper, then resolve a canonical/current",
        "web source for deep reading. Prefer Web PDF for visual/equation/layout-aware",
        "reading; use mirrored Zotero indexed full text as search/fallback.",
        "",
    ]
    for item in ordered:
        title = markdown_inline(str(item.get("title") or "(untitled)"))
        web = item.get("webResolution") or {}
        parts = [f"Zotero key: `{item['key']}`"]
        if web.get("doi"):
            parts.append(f"DOI: `{web['doi']}`")
        if web.get("arxivId"):
            parts.append(f"arXiv: `{web['arxivId']}`")
        if web.get("sourceUrl"):
            parts.append(f"item source: {web['sourceUrl']}")
        direct_urls = sorted({
            str(att.get("url"))
            for att in attachments_by_parent.get(item["key"], [])
            if att.get("url") and att.get("contentType") == "application/pdf"
        })
        if direct_urls:
            parts.append("PDF source candidate: " + direct_urls[0])
            if len(direct_urls) > 1:
                parts.append(f"+{len(direct_urls) - 1} additional PDF-source URL(s)")
        lines.append(f"- **{title}** — " + "; ".join(parts))
    return "\n".join(lines).rstrip() + "\n"


def render_notes(notes: list[dict[str, Any]]) -> str:
    ordered = sorted(
        notes,
        key=lambda note: (
            str(note.get("parentTitle") or "").casefold(),
            note["key"],
        ),
    )
    lines = [
        "# AI-Relevant Zotero Notes",
        "",
        "Machine-generated plugin state and imported source comments are excluded here.",
        "See `notes_all.json` for the complete normalized note inventory.",
        "",
    ]
    if not ordered:
        lines.append("_No AI-relevant notes found._")
        return "\n".join(lines) + "\n"

    for note in ordered:
        title = markdown_inline(str(note.get("parentTitle") or "(standalone note)"))
        lines.extend([
            f"## {title}",
            "",
            f"- Note key: `{note['key']}`",
            f"- Parent item: `{note.get('parentItem') or 'none'}`",
            "",
        ])
        text = str(note.get("noteText") or "").strip()
        if text:
            lines.extend([f"> {line}" if line else ">" for line in text.splitlines()])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_annotations(annotations: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ann in annotations:
        key = str(ann.get("parentItem") or "standalone")
        grouped.setdefault(key, []).append(ann)

    lines = [
        "# Zotero PDF Annotations",
        "",
        "Highlights/comments synchronized from Zotero. Zotero remains the source of truth.",
        "",
    ]
    if not annotations:
        lines.append("_No synchronized annotations found._")
        return "\n".join(lines) + "\n"

    def parent_title(group: list[dict[str, Any]]) -> str:
        for ann in group:
            if ann.get("parentTitle"):
                return str(ann["parentTitle"])
        return "(standalone attachment)"

    for parent_key, group in sorted(
        grouped.items(),
        key=lambda kv: (parent_title(kv[1]).casefold(), kv[0]),
    ):
        lines.extend([
            f"## {markdown_inline(parent_title(group))}",
            "",
            f"- Parent item: `{parent_key}`",
            "",
        ])
        for ann in sorted(
            group,
            key=lambda x: (
                str(x.get("annotationSortIndex") or ""),
                str(x.get("key") or ""),
            ),
        ):
            page = ann.get("annotationPageLabel") or "?"
            atype = ann.get("annotationType") or "annotation"
            lines.append(f"### Page {page} · {atype} · `{ann['key']}`")
            lines.append("")
            text = str(ann.get("annotationText") or "").strip()
            comment = str(ann.get("annotationComment") or "").strip()
            if text:
                lines.extend([f"> {line}" if line else ">" for line in text.splitlines()])
                lines.append("")
            if comment:
                lines.append(f"**Comment:** {comment}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_collections_index(
    items: list[dict[str, Any]],
    collections: list[dict[str, Any]],
) -> str:
    members: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for path in item.get("collectionPaths") or []:
            members.setdefault(path, []).append(item)

    lines = ["# Collections Index", ""]
    for collection in collections:
        path = str(collection.get("path") or collection.get("name") or "")
        group = members.get(path, [])
        lines.extend([f"## {path}", "", f"{len(group)} bibliographic items.", ""])
        for item in sorted(group, key=lambda x: str(x.get("title") or "").casefold()):
            lines.append(
                f"- {markdown_inline(str(item.get('title') or '(untitled)'))} "
                f"(`{item['key']}`)"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_classification_context(
    items: list[dict[str, Any]],
    collections: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> str:
    members: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for path in item.get("collectionPaths") or []:
            members.setdefault(path, []).append(item)

    lines = [
        "# Zotero Classification Context",
        "",
        "Generated from the current library taxonomy. Use this before importing a",
        "new paper. Prefer existing collections/tags; avoid creating taxonomy",
        "sprawl. Low-confidence imports should use the configured inbox fallbacks.",
        "",
        "## Collection taxonomy",
        "",
    ]

    for collection in collections:
        path = str(collection.get("path") or collection.get("name") or "")
        group = members.get(path, [])
        examples = sorted(
            (str(x.get("title") or "(untitled)") for x in group),
            key=str.casefold,
        )[:3]
        lines.append(
            f"- `{collection['key']}` — **{markdown_inline(path)}** — "
            f"{len(group)} item(s)"
        )
        if examples:
            lines.append(
                "  - examples: "
                + "; ".join(markdown_inline(x) for x in examples)
            )

    lines.extend([
        "",
        "## Existing structured tags",
        "",
    ])
    structured = [
        tag for tag in tags
        if str(tag.get("tag") or "").startswith(
            ("method/", "domain/", "task/", "status/", "/")
        )
    ]
    for tag in sorted(
        structured,
        key=lambda x: (
            -int(x.get("numItems") or 0),
            str(x.get("tag") or "").casefold(),
        ),
    ):
        lines.append(
            f"- `{tag.get('tag')}` — {int(tag.get('numItems') or 0)} item(s)"
        )

    lines.extend([
        "",
        "## Common source/domain tags",
        "",
    ])
    common = [
        tag for tag in tags
        if tag not in structured and int(tag.get("numItems") or 0) >= 2
    ]
    for tag in sorted(
        common,
        key=lambda x: (
            -int(x.get("numItems") or 0),
            str(x.get("tag") or "").casefold(),
        ),
    )[:40]:
        lines.append(
            f"- `{tag.get('tag')}` — {int(tag.get('numItems') or 0)} item(s)"
        )

    lines.extend([
        "",
        "## Import defaults",
        "",
        "- Add `/unread` unless the human explicitly says the paper is already read.",
        "- Reuse existing tags automatically; do not silently invent new tag vocabularies.",
        "- Prefer existing content/role/project collections.",
        "- If classification confidence is low: use `Inbox / Unclassified`.",
        "- If metadata confidence is low: use `Inbox / Metadata Review`.",
        "- Do not create new collections during import unless the human explicitly requests it.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def render_recent(items: list[dict[str, Any]], limit: int = 50) -> str:
    ordered = sorted(
        items,
        key=lambda x: str(x.get("dateAdded") or ""),
        reverse=True,
    )[:limit]
    lines = ["# Recently Added Zotero Items", ""]
    for item in ordered:
        lines.append(
            f"- {item.get('dateAdded') or '?'} — "
            f"**{markdown_inline(str(item.get('title') or '(untitled)'))}** "
            f"(`{item['key']}`)"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_reading_queue(items: list[dict[str, Any]]) -> str:
    unread = [item for item in items if "/unread" in (item.get("tags") or [])]
    ordered = sorted(
        unread,
        key=lambda x: (
            -(int(x["year"]) if str(x.get("year") or "").isdigit() else 0),
            str(x.get("title") or "").casefold(),
        ),
    )
    lines = ["# Zotero Reading Queue", "", "Items tagged `/unread`.", ""]
    for item in ordered:
        lines.append(
            f"- **{markdown_inline(str(item.get('title') or '(untitled)'))}** "
            f"({item.get('year') or 'n.d.'}) — `{item['key']}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_quality_report(items: list[dict[str, Any]]) -> str:
    missing_abstract = [x for x in items if not x.get("abstractNote")]
    missing_year = [x for x in items if not x.get("year")]
    missing_doi = [
        x for x in items
        if x.get("itemType") in {"journalArticle", "conferencePaper", "preprint"}
        and not x.get("DOI")
    ]

    doi_groups: dict[str, list[dict[str, Any]]] = {}
    title_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        doi = str(item.get("DOI") or "").strip().lower()
        if doi:
            doi_groups.setdefault(doi, []).append(item)
        title = re.sub(r"\W+", "", str(item.get("title") or "").casefold())
        if title:
            title_groups.setdefault(title, []).append(item)
    dup_doi = [g for g in doi_groups.values() if len(g) > 1]
    dup_title = [g for g in title_groups.values() if len(g) > 1]

    def listing(rows: list[dict[str, Any]], max_items: int = 100) -> list[str]:
        return [
            f"- {markdown_inline(str(x.get('title') or '(untitled)'))} (`{x['key']}`)"
            for x in rows[:max_items]
        ] or ["- None"]

    lines = [
        "# Zotero Metadata Quality Report",
        "",
        "Read-only diagnostic. Fixes, if desired, must be made in Zotero.",
        "",
        f"## Missing abstracts ({len(missing_abstract)})",
        "",
        *listing(missing_abstract),
        "",
        f"## Missing years ({len(missing_year)})",
        "",
        *listing(missing_year),
        "",
        f"## Missing DOI on article/conference/preprint records ({len(missing_doi)})",
        "",
        *listing(missing_doi),
        "",
        f"## Duplicate DOI groups ({len(dup_doi)})",
        "",
    ]
    if dup_doi:
        for group in dup_doi:
            lines.append("- " + " | ".join(f"{x.get('title')} (`{x['key']}`)" for x in group))
    else:
        lines.append("- None")
    lines.extend(["", f"## Duplicate normalized-title groups ({len(dup_title)})", ""])
    if dup_title:
        for group in dup_title:
            lines.append("- " + " | ".join(f"{x.get('title')} (`{x['key']}`)" for x in group))
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def stable_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def write_if_changed(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
    path.write_bytes(content)
    return True


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def delete_stale_files(directory: Path, keep_names: set[str]) -> list[str]:
    deleted: list[str] = []
    if not directory.exists():
        return deleted
    for path in directory.iterdir():
        if path.is_file() and path.name not in keep_names:
            path.unlink()
            deleted.append(str(path))
    return deleted


def build_fulltext_mirror(
    base_path: str,
    attachments: list[dict[str, Any]],
    item_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    versions_obj, headers = request_json(f"{base_path}/fulltext", {"since": 0})
    versions = versions_obj if isinstance(versions_obj, dict) else {}

    index_path = OUTPUT_DIR / "fulltext" / "index.json"
    previous: dict[str, Any] = {}
    if index_path.exists():
        try:
            previous_obj = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(previous_obj, dict):
                previous = previous_obj.get("attachments") or {}
        except Exception:
            previous = {}

    attachment_map = {x["key"]: x for x in attachments}
    index_entries: dict[str, Any] = {}
    changed: list[str] = []
    keep_files: set[str] = {"index.json"}

    for key, raw_version in sorted(versions.items()):
        version = int(raw_version)
        attachment = attachment_map.get(key) or {}
        parent_key = attachment.get("parentItem")
        parent = item_map.get(str(parent_key)) if parent_key else None
        title = str((parent or {}).get("title") or attachment.get("title") or key)
        filename = f"{key}.md"
        keep_files.add(filename)
        target = OUTPUT_DIR / "fulltext" / filename
        prev = previous.get(key) or {}

        needs_fetch = int(prev.get("version") or -1) != version or not target.exists()
        if needs_fetch:
            obj, _ = request_json(
                f"{base_path}/items/{key}/fulltext",
                allow_404=True,
            )
            if not isinstance(obj, dict):
                continue
            content = str(obj.get("content") or "")
            lines = [
                f"# Full Text — {title}",
                "",
                f"- Attachment key: `{key}`",
                f"- Parent item: `{parent_key or 'none'}`",
                f"- Full-text version: `{version}`",
            ]
            for metric in ("indexedPages", "totalPages", "indexedChars", "totalChars"):
                if obj.get(metric) is not None:
                    lines.append(f"- {metric}: `{obj[metric]}`")
            lines.extend(["", "## Extracted text", "", content, ""])
            if write_if_changed(target, "\n".join(lines).encode("utf-8")):
                changed.append(str(target))

            entry = {
                "version": version,
                "file": f"fulltext/{filename}",
                "attachmentKey": key,
                "parentItem": parent_key,
                "parentTitle": (parent or {}).get("title"),
                "contentType": attachment.get("contentType"),
                "filename": attachment.get("filename"),
                "indexedPages": obj.get("indexedPages"),
                "totalPages": obj.get("totalPages"),
                "indexedChars": obj.get("indexedChars"),
                "totalChars": obj.get("totalChars"),
            }
        else:
            entry = dict(prev)
            entry["version"] = version
            entry["file"] = f"fulltext/{filename}"

        index_entries[key] = entry

    deleted = delete_stale_files(OUTPUT_DIR / "fulltext", keep_files)
    index = {
        "libraryVersion": int(headers.get("Last-Modified-Version"))
        if headers.get("Last-Modified-Version") and str(headers.get("Last-Modified-Version")).isdigit()
        else None,
        "attachments": index_entries,
    }
    return index, changed, deleted


def render_paper_page(
    item: dict[str, Any],
    notes_by_parent: dict[str, list[dict[str, Any]]],
    annotations_by_parent: dict[str, list[dict[str, Any]]],
    attachments_by_parent: dict[str, list[dict[str, Any]]],
    fulltext_index: dict[str, Any],
) -> str:
    key = item["key"]
    lines = [
        f"# {item.get('title') or '(untitled)'}",
        "",
        f"- Zotero item key: `{key}`",
        f"- Type: `{item.get('itemType') or '?'}`",
        f"- Year: `{item.get('year') or 'n.d.'}`",
        f"- Creators: {creator_display(item.get('creators') or [])}",
    ]
    if item.get("bibtexKey"):
        lines.append(f"- BibTeX key: `{item['bibtexKey']}`")
    if item.get("DOI"):
        lines.append(f"- DOI: `{item['DOI']}`")
    if item.get("url"):
        lines.append(f"- URL: {item['url']}")
    if item.get("collectionPaths"):
        lines.append("- Collections: " + "; ".join(item["collectionPaths"]))
    if item.get("tags"):
        lines.append("- Tags: " + ", ".join(item["tags"]))

    web = item.get("webResolution") or {}
    lines.extend([
        "",
        "## Web Deep-Reading Resolution",
        "",
        "Preferred protocol: identify this Zotero record first, resolve a canonical/current",
        "web source, verify version alignment, and prefer the Web PDF for deep reading.",
        "Use the mirrored Zotero indexed full text primarily for retrieval and fallback.",
        "",
    ])
    if web.get("doiUrl"):
        lines.append(f"- DOI resolver: {web['doiUrl']}")
    if web.get("arxivId"):
        lines.append(f"- arXiv ID: `{web['arxivId']}`")
        lines.append(f"- arXiv abstract: {web.get('arxivAbsUrl')}")
        lines.append(f"- arXiv PDF: {web.get('arxivPdfUrl')}")
    if web.get("sourceUrl"):
        lines.append(f"- Zotero source URL: {web['sourceUrl']}")
    if web.get("exactTitleQuery"):
        lines.append(f"- Exact-title fallback query: {web['exactTitleQuery']}")
    lines.extend([
        "- Version check: compare title, authors, DOI/arXiv/OpenReview/proceedings identity,",
        "  venue, date, and version before treating a Web PDF as the same research object.",
        "",
    ])

    abstract = str(item.get("abstractNote") or "").strip()
    lines.extend(["", "## Abstract", "", abstract or "_No abstract in Zotero._", ""])

    notes = notes_by_parent.get(key, [])
    lines.extend(["## My Zotero Notes", ""])
    if notes:
        for note in notes:
            lines.append(f"### Note `{note['key']}`")
            lines.append("")
            lines.append(str(note.get("noteText") or "").strip())
            lines.append("")
    else:
        lines.extend(["_No AI-relevant note mirrored._", ""])

    annotations = annotations_by_parent.get(key, [])
    lines.extend(["## PDF Annotations", ""])
    if annotations:
        for ann in sorted(
            annotations,
            key=lambda x: (
                str(x.get("annotationSortIndex") or ""),
                str(x.get("key") or ""),
            ),
        ):
            page = ann.get("annotationPageLabel") or "?"
            lines.append(
                f"### Page {page} · {ann.get('annotationType') or 'annotation'} · `{ann['key']}`"
            )
            lines.append("")
            text = str(ann.get("annotationText") or "").strip()
            comment = str(ann.get("annotationComment") or "").strip()
            if text:
                lines.extend([f"> {line}" if line else ">" for line in text.splitlines()])
                lines.append("")
            if comment:
                lines.extend([f"**Comment:** {comment}", ""])
    else:
        lines.extend(["_No synchronized annotations mirrored._", ""])

    lines.extend(["## Attachments and Full Text", ""])
    attachments = attachments_by_parent.get(key, [])
    if attachments:
        full_entries = fulltext_index.get("attachments") or {}
        for att in attachments:
            parts = [f"`{att['key']}`"]
            if att.get("filename"):
                parts.append(str(att["filename"]))
            if att.get("contentType"):
                parts.append(str(att["contentType"]))
            if att.get("url"):
                parts.append(f"source URL: {att['url']}")
            ft = full_entries.get(att["key"])
            if ft:
                parts.append(f"full text: `library/{ft['file']}`")
            lines.append("- " + " — ".join(parts))
    else:
        lines.append("_No attachment metadata mirrored._")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if not API_KEY:
        print("ERROR: ZOTERO_API_KEY is not set.", file=sys.stderr)
        return 2

    base_path = f"/users/{USER_ID}"

    top_raw, v_items = fetch_json_pages(
        f"{base_path}/items/top",
        {"format": "json", "include": "data,bibtex"},
    )
    notes_raw, v_notes = fetch_json_pages(
        f"{base_path}/items",
        {"format": "json", "include": "data", "itemType": "note"},
    )
    attachments_raw, v_attachments = fetch_json_pages(
        f"{base_path}/items",
        {"format": "json", "include": "data", "itemType": "attachment"},
    )
    annotations_raw, v_annotations = fetch_json_pages(
        f"{base_path}/items",
        {"format": "json", "include": "data", "itemType": "annotation"},
    )
    collections_raw, v_collections = fetch_json_pages(
        f"{base_path}/collections",
        {"format": "json", "include": "data"},
    )
    tags_raw, v_tags = fetch_json_pages(
        f"{base_path}/tags",
        {"format": "json"},
    )
    searches_raw, v_searches = fetch_json_pages(
        f"{base_path}/searches",
        {"format": "json", "include": "data"},
    )
    bibtex = fetch_bibtex_pages(f"{base_path}/items/top")

    collection_names, collection_paths = build_collection_maps(collections_raw)

    top_normalized = [
        normalize_item(x, collection_names, collection_paths)
        for x in top_raw
    ]
    items = sorted(
        [x for x in top_normalized if x.get("itemType") not in NON_BIB_TYPES],
        key=lambda x: x["key"],
    )
    misc_top = sorted(
        [x for x in top_normalized if x.get("itemType") in NON_BIB_TYPES],
        key=lambda x: x["key"],
    )
    item_map = {x["key"]: x for x in items}
    parent_titles = {
        **{item["key"]: str(item.get("title") or "(untitled)") for item in items},
        **{item["key"]: str(item.get("title") or "(untitled)") for item in misc_top},
    }

    attachments = sorted(
        (normalize_attachment(x, parent_titles) for x in attachments_raw),
        key=lambda x: x["key"],
    )
    attachment_map = {x["key"]: x for x in attachments}

    annotations = sorted(
        (normalize_annotation(x, attachment_map, item_map) for x in annotations_raw),
        key=lambda x: x["key"],
    )

    notes_all = sorted(
        (normalize_note(x, parent_titles) for x in notes_raw),
        key=lambda x: x["key"],
    )
    notes_relevant = [
        note for note in notes_all
        if note["category"] == "ai_relevant"
    ]

    collections = sorted(
        (
            normalize_collection(
                x,
                collection_paths.get(
                    str(x.get("key") or (x.get("data") or {}).get("key") or "")
                ),
            )
            for x in collections_raw
        ),
        key=lambda x: (x["path"] or x["name"]).casefold(),
    )
    tags = sorted(
        (normalize_tag(x) for x in tags_raw if x.get("tag")),
        key=lambda x: x["tag"].casefold(),
    )
    saved_searches = sorted(
        (normalize_search(x) for x in searches_raw),
        key=lambda x: (x["name"].casefold(), x["key"]),
    )

    fulltext_index, fulltext_changed, fulltext_deleted = build_fulltext_mirror(
        base_path,
        attachments,
        item_map,
    )

    notes_by_parent: dict[str, list[dict[str, Any]]] = {}
    for note in notes_relevant:
        if note.get("parentItem"):
            notes_by_parent.setdefault(str(note["parentItem"]), []).append(note)

    annotations_by_parent: dict[str, list[dict[str, Any]]] = {}
    for ann in annotations:
        if ann.get("parentItem"):
            annotations_by_parent.setdefault(str(ann["parentItem"]), []).append(ann)

    attachments_by_parent: dict[str, list[dict[str, Any]]] = {}
    for att in attachments:
        if att.get("parentItem"):
            attachments_by_parent.setdefault(str(att["parentItem"]), []).append(att)

    payloads: dict[str, bytes] = {
        "items.json": stable_json_bytes(items),
        "top_level_misc.json": stable_json_bytes(misc_top),
        "notes.json": stable_json_bytes(notes_relevant),
        "notes_all.json": stable_json_bytes(notes_all),
        "attachments.json": stable_json_bytes(attachments),
        "annotations.json": stable_json_bytes(annotations),
        "collections.json": stable_json_bytes(collections),
        "tags.json": stable_json_bytes(tags),
        "saved_searches.json": stable_json_bytes(saved_searches),
        "references.bib": bibtex.encode("utf-8"),
        "catalog.md": render_catalog(items).encode("utf-8"),
        "web_sources.md": render_web_sources(
            items, attachments_by_parent
        ).encode("utf-8"),
        "notes.md": render_notes(notes_relevant).encode("utf-8"),
        "annotations.md": render_annotations(annotations).encode("utf-8"),
        "collections.md": render_collections_index(items, collections).encode("utf-8"),
        "classification_context.md": render_classification_context(
            items, collections, tags
        ).encode("utf-8"),
        "recent.md": render_recent(items).encode("utf-8"),
        "reading_queue.md": render_reading_queue(items).encode("utf-8"),
        "quality_report.md": render_quality_report(items).encode("utf-8"),
        "fulltext/index.json": stable_json_bytes(fulltext_index),
    }

    versions = [
        v for v in (
            v_items, v_notes, v_attachments, v_annotations,
            v_collections, v_tags, v_searches,
        )
        if v is not None
    ]
    note_categories: dict[str, int] = {}
    for note in notes_all:
        category = str(note["category"])
        note_categories[category] = note_categories.get(category, 0) + 1

    manifest = {
        "schemaVersion": 4,
        "zoteroUserId": USER_ID,
        "libraryVersion": max(versions) if versions else None,
        "counts": {
            "bibliographicItems": len(items),
            "topLevelMisc": len(misc_top),
            "notesRelevant": len(notes_relevant),
            "notesAll": len(notes_all),
            "noteCategories": dict(sorted(note_categories.items())),
            "attachments": len(attachments),
            "annotations": len(annotations),
            "fulltextAttachments": len((fulltext_index.get("attachments") or {})),
            "collections": len(collections),
            "tags": len(tags),
            "savedSearches": len(saved_searches),
        },
        "sha256": {
            name: sha256_hex(content)
            for name, content in sorted(payloads.items())
        },
    }
    payloads["manifest.json"] = stable_json_bytes(manifest)

    changed: list[str] = list(fulltext_changed)
    deleted: list[str] = list(fulltext_deleted)
    for name, content in payloads.items():
        if write_if_changed(OUTPUT_DIR / name, content):
            changed.append(str(OUTPUT_DIR / name))

    paper_dir = OUTPUT_DIR / "papers"
    keep_papers: set[str] = set()
    for item in items:
        filename = f"{item['key']}.md"
        keep_papers.add(filename)
        content = render_paper_page(
            item,
            notes_by_parent,
            annotations_by_parent,
            attachments_by_parent,
            fulltext_index,
        ).encode("utf-8")
        if write_if_changed(paper_dir / filename, content):
            changed.append(str(paper_dir / filename))
    deleted.extend(delete_stale_files(paper_dir, keep_papers))

    print(
        json.dumps(
            {
                "status": "ok",
                "user_id": USER_ID,
                "library_version": manifest["libraryVersion"],
                "counts": manifest["counts"],
                "changed_count": len(changed),
                "deleted_count": len(deleted),
                "changed_sample": changed[:25],
                "deleted_sample": deleted[:25],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
