# Contributing

Contributions, review and bug reports are welcome.

## Privacy and reproducibility

Never commit real Zotero library exports, full-text papers, personal notes,
annotations, write receipts, account IDs, or API keys. Use the synthetic
fixtures under `examples/synthetic-library/`.

Do not include real Zotero keys or real library data in CI logs or issue
descriptions. Public pull requests should use mocked Web API requests or
synthetic fixtures.

## Change workflow and local checks

For non-trivial changes, use a focused branch and pull request. Inspect the
diff and run the same canonical offline check as upstream CI:

```bash
python scripts/validate_project.py
```

Python 3.13 and its standard library are sufficient. This command compiles the
source and exercises synthetic/privacy/onboarding validators without contacting
Zotero or using any credentials. Tests requiring a configured private library
(e.g. import-classification reconciliation or post-write readback) are **not**
part of this upstream suite. Do not interpret a green offline result as live
end-to-end acceptance.

The public-tree validator intentionally ignores transient Python bytecode
caches while rejecting unexpected private-data paths and binary artifacts.
Do not run the upstream public-tree validator on a real private instance.

## Changes to writes

Preserve fail-closed behavior, expected-version checks, distinct read/write
credentials, request receipts, and read-only post-write verification.

Native Zotero Duplicate Merge is Desktop-only and must not be implemented as
an unsafe approximate merge.
