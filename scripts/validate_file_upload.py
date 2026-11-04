#!/usr/bin/env python3
"""Offline regression checks for the Zotero Storage upload path."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import zotero_features as zf


class FakeResponse:
    def __init__(self, status: int):
        self.status = status
    def __enter__(self) -> "FakeResponse":
        return self
    def __exit__(self, *args: Any) -> None:
        return None
    def read(self) -> bytes:
        return b""


def expect_error(fn: Any, marker: str) -> None:
    try:
        fn()
    except RuntimeError as exc:
        if marker not in str(exc):
            raise AssertionError(f"expected {marker!r}, got {exc!r}") from exc
        return
    raise AssertionError(f"expected RuntimeError containing {marker!r}")


def main() -> int:
    capabilities = json.loads(
        (ROOT / "config" / "capabilities.json").read_text(encoding="utf-8")
    )
    policy = json.loads(
        (ROOT / "config" / "pdf_upload_policy.json").read_text(encoding="utf-8")
    )
    cap = capabilities["capabilities"]["pdf_storage_upload"]
    assert cap["verdict"] == "SUPPORTED_BY_WEB_API"
    assert cap["enabled"] is True
    assert int(policy["max_bytes"]) > 0

    parent = {
        "title": "Synthetic Operator Paper",
        "DOI": "10.48550/arXiv.9999.99999",
        "url": "https://arxiv.org/abs/9999.99999",
    }
    audit = zf.validate_pdf_identity(
        parent,
        "https://arxiv.org/pdf/9999.99999",
        {
            "verified": True,
            "arxiv_id": "9999.99999",
            "version_alignment": "canonical arXiv record",
        },
    )
    assert "arxiv" in audit["matches"]

    expect_error(
        lambda: zf.validate_pdf_identity(
            parent,
            "https://example.org/wrong.pdf",
            {
                "verified": True,
                "doi": "10.0000/wrong",
                "version_alignment": "checked",
            },
        ),
        "PDF_IDENTITY_MISMATCH",
    )
    expect_error(
        lambda: zf._validate_public_https_url(
            "http://example.org/paper.pdf", resolve=False
        ),
        "UNSAFE_PDF_URL",
    )
    expect_error(
        lambda: zf._validate_public_https_url(
            "https://localhost/paper.pdf", resolve=False
        ),
        "UNSAFE_PDF_URL",
    )

    form_calls: list[dict[str, Any]] = []
    def fake_form_request(**kwargs: Any) -> tuple[int, Any, dict[str, str]]:
        form_calls.append(kwargs)
        if len(form_calls) == 1:
            return 200, {
                "url": "https://upload.example.org/",
                "contentType": "application/octet-stream",
                "prefix": "PRE",
                "suffix": "POST",
                "uploadKey": "UPLOAD-KEY",
            }, {}
        return 204, None, {"Zotero-Library-Version": "99"}

    captured: dict[str, Any] = {}
    def fake_urlopen(request: Any, timeout: int = 0) -> FakeResponse:
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["content_type"] = request.headers.get("Content-type")
        return FakeResponse(201)

    pdf = {
        "bytes": b"%PDF-test",
        "md5": "0" * 32,
        "filename": "paper.pdf",
        "size": 9,
        "mtime": 123,
    }
    with mock.patch.object(zf, "_form_request", side_effect=fake_form_request), \
         mock.patch.object(zf, "_validate_public_https_url"), \
         mock.patch.object(zf.urllib.request, "urlopen", side_effect=fake_urlopen):
        result = zf.upload_storage_file(
            base="https://api.zotero.org",
            user_id="1",
            api_key="REDACTED",
            attachment_key="ABCDEFGH",
            pdf=pdf,
        )

    assert captured["data"] == b"PRE%PDF-testPOST"
    assert form_calls[0]["headers"]["If-None-Match"] == "*"
    assert form_calls[1]["fields"] == {"upload": "UPLOAD-KEY"}
    assert form_calls[1]["headers"]["If-None-Match"] == "*"
    assert result["status"] == "uploaded"
    assert result["registered"] is True

    existing_calls: list[dict[str, Any]] = []
    def fake_existing_form(**kwargs: Any) -> tuple[int, Any, dict[str, str]]:
        existing_calls.append(kwargs)
        if len(existing_calls) == 1:
            return 200, {
                "url": "https://upload.example.org/",
                "contentType": "application/octet-stream",
                "prefix": "PRE",
                "suffix": "POST",
                "uploadKey": "UPLOAD-KEY-2",
            }, {}
        return 204, None, {"Zotero-Library-Version": "100"}

    with mock.patch.object(zf, "_form_request", side_effect=fake_existing_form), \
         mock.patch.object(zf, "_validate_public_https_url"), \
         mock.patch.object(zf.urllib.request, "urlopen", side_effect=fake_urlopen):
        existing_result = zf.upload_storage_file(
            base="https://api.zotero.org",
            user_id="1",
            api_key="REDACTED",
            attachment_key="ABCDEFGH",
            pdf=pdf,
            previous_md5="1" * 32,
        )

    assert existing_calls[0]["headers"]["If-Match"] == "1" * 32
    assert existing_calls[1]["headers"]["If-Match"] == "1" * 32
    assert existing_result["status"] == "uploaded"
    assert existing_result["registered"] is True

    print(json.dumps({"status": "VALID", "checks": 13}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
