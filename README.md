# zotero-mirror

[简体中文](README.zh-CN.md)

**Private-by-default Zotero ↔ GitHub mirror for AI-assisted research workflows.**

> **Public source template.** This repository contains reusable code and synthetic
> fixtures, not anyone's Zotero library. It is an unofficial community project,
> not affiliated with Zotero, and **not** a Zotero Desktop extension.

Zotero remains the canonical library. A private repository created from this
template maintains a versioned, AI-readable projection of metadata, notes,
annotations, attachment metadata and indexed full text.

## Get started

[Use this template](https://github.com/Charlie-Wang-03/zotero-mirror/generate) to create a **private repository** for your own library. No local clone is required for the normal setup.

```text
Use this template
→ create a Private repository
→ add the ZOTERO_USER_ID repository variable
→ add the ZOTERO_API_KEY_READONLY secret
→ run First Run
→ inspect library/STATUS.md
→ set ZOTERO_MIRROR_ENABLED=true
```

For ordinary private instances, no local clone is required. The GitHub Actions
workflows use Python's standard library.

**Do not put a real Zotero library in a public repository.**

See [Quickstart](docs/QUICKSTART.md),
[Configuration](docs/CONFIGURATION.md), and
[Template deployment](docs/TEMPLATE_DEPLOYMENT.md).

## Capabilities and boundaries

| Feature | Status |
| --- | --- |
| Read-only Zotero library mirror | Implemented; private First Run verified |
| Library-version and count reconciliation | Implemented; private First Run verified |
| Time-bounded, version-guarded writes | Implemented; isolated create/read/patch/delete verified |
| PDF Storage upload | Implemented; offline regression coverage |
| Annotation writes with trusted PDF geometry | Partial / constrained |
| Annotation-linked rich notes | Partial; generated HTML semantics vary |
| Saved Search metadata CRUD | Implemented; API does not execute search results |
| Native Duplicate Merge | Not supported by Zotero Web API; Desktop-only |

A previous private, isolated canary exercise verified an actual First Run and
two create/read/patch/delete cycles. This does **not** establish full
end-to-end validation of every write-queue, PDF upload, annotation or Saved
Search path. See [Validation and limitations](docs/VALIDATION.md).

## Trust and safety

- Private instance repositories are enforced by runtime checks.
- Sync uses a dedicated key **without** write permission.
- Write capability requires a separate key, explicit feature flag and a
  time-bounded `read_write` session.
- `config/access_mode.json` defaults to `read_only` and
  `allow_destructive=false`.
- Writes use version guards and audited request/receipt infrastructure.
- Public upstream includes **no** real library snapshot, notes, PDFs,
  personal identifiers, write receipts or API keys.
- Public-template regression checks are intentionally skipped in private
  instances; each operational workflow performs its own checks.

## Validate the public source

With Python 3.13 and no third-party packages:

```bash
python scripts/validate_project.py
```

This runs offline syntax, privacy-boundary, onboarding and synthetic feature
checks. It does **not** test a live Zotero account or establish full end-to-end
write capability. See [Validation and limitations](docs/VALIDATION.md).

## Project documentation

- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Contributing](CONTRIBUTING.md)

Licensed under the [MIT License](LICENSE).
