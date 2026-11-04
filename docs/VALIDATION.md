# Validation and limitations

## Evidence from private canary testing

The private instance's initial First Run completed successfully, including
credential validation, version-stable snapshot reconciliation, strict
consistency checks and writing the mirror into its private Git repository.

Two separately triggered isolated write tests successfully exercised:

- distinct read-only and read-write API credentials;
- temporary synthetic item creation and read-only readback;
- expected item-version enforcement;
- item patch and read-only readback;
- strict mirror refresh;
- guarded cleanup of the same temporary item;
- absence from the active mirror after cleanup.

The temporary canary repository and its dedicated API keys were removed as
part of test teardown. We do not ship any associated user data or identifiers.

## What these results do not prove

- The entire GitHub request-queue, receipt and post-write orchestration was
  not covered by the isolated write smoke test.
- PDF Storage upload and Saved Search paths have offline regression checks;
  do not infer that every account or PDF type is supported.
- PDF annotation writes remain limited by exact trusted geometry; the product
  does not infer page rectangles from natural-language queries.
- Generated rich annotation notes offer partial Zotero jump-back semantics,
  not a verified native server-side "Add Note from Annotations" endpoint.
- Native duplicate merging is not supported over the Zotero Web API.

## Offline upstream validation

From a source checkout with Python 3.13 (no third-party packages):

```bash
python scripts/validate_project.py
```

This is the same entry point as **Upstream CI**. The offline suite checks:

- all Python scripts compiling under the configured Python version;
- rejection of real library files and credential-like content;
- generic documentation and onboarding contracts;
- synthetic PDF upload, Saved Search, annotation and rich-note regressions;
- release-readiness structural checks.

The regression workflow is scoped to the canonical source repository and is
intentionally skipped in generated private user instances.

**Scope:** this command does not need network access, Zotero credentials,
or real library data. It does not run instance-specific `validate_import.py`
(which needs `library/items.json`, collections and tags) or make live Zotero
writes. `validate_post_write.py` is a separate runtime verifier for a
configured instance; a skipped verification is not a pass of that operation.

Green CI means these reproducible checks passed, **not** that a real user
completed onboarding or that every API-dependent feature is live-verified.
