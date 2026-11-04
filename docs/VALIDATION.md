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

## GitHub Actions runtime and supply-chain boundary

All six upstream/template workflows use immutable commit pins for GitHub's
`actions/checkout` **v7.0.1** (`3d3c42e5aac5ba805825da76410c181273ba90b1`)
and `actions/setup-python` **v7.1.0**
(`6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`). Their upstream release tags were
resolved against the official `actions/checkout` and `actions/setup-python`
repositories on 2026-11-04. Both use Node.js 24 and document a minimum
GitHub Actions Runner version of **2.327.1**; checkout notes that authenticated
Git operations from Docker container actions require at least **2.329.0**.
The last inspected GitHub-hosted `ubuntu-24.04` runner was **2.338.2**.

The offline documentation contract checks these pins across all six workflow
files; upstream CI executes those checks. The GitHub-hosted CI job additionally
checks out this repository and sets up Python using these pinned actions.
**Private template-instance** workflows use the same versions but are not
executed against a live Zotero account by upstream CI. In particular, the
First Run, scheduled sync, mode-change and credentialed write/commit/push paths
have not been rerun against a real private Zotero instance with these exact
Action versions. Earlier real First Run, sync and isolated write tests remain
valid historical functional evidence. A new private canary is optional, not
a mandatory gate for this narrowly scoped dependency update.
