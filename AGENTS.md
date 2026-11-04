# AGENTS.md

Repository-level contract for coding agents, reviewers and maintainers.

## Product boundary

`zotero-mirror` is reusable, private-by-default infrastructure.

The reusable source repository must never contain any real user's Zotero
library, full-text corpus, notes, annotations, write receipts, credentials,
account identifiers or private production Git history.

A configured Zotero mirror must live in a **private repository**.
Zotero remains the canonical source of truth.

## Safety invariants

1. Default mode is `read_only`.
2. Use separate read-only and read-write credentials. Never print them.
3. The read-only key must not carry write permission.
4. Both keys must belong to the configured Zotero user.
5. First Run and live sync/write workflows reject public instance repositories.
6. Writes require a separate opt-in and a non-expired read-write session.
7. Destructive writes remain disabled by default and require explicit consent.
8. Reject missing or stale expected item versions.
9. Check write receipts and refresh through the read-only key.
10. Reject uncertain annotation geometry, identity, or duplicate matches.
11. Never simulate native Duplicate Merge using destructive patch/move/delete.

## User onboarding

```text
Use this template
→ Private repository
→ ZOTERO_USER_ID and ZOTERO_API_KEY_READONLY
→ First Run
→ verified private library/
→ ZOTERO_MIRROR_ENABLED=true
```

Optional writes require a separate read-write key and a short-lived session.
Do not ask users to paste API keys into chat or commit them to source.

## Public release hygiene

Before public distribution, run the complete upstream CI, validate every
tracked source path and all reachable commits, and publish from a **new clean
Git root**. Do not change a historical private development repository to
Public. GitHub may expose its entire commit history and Actions logs.

Do not copy production `library/**`, personal receipts, nonpublic test
records or original production history into the distributable source tree.

## Development flow

```text
generic change
→ synthetic regression tests
→ public-tree privacy validator
→ upstream CI
→ release checklist
→ independent clean-root publication
```

Upstream-only `validate_public_tree.py` is not a correctness validator for a
configured private instance, where legitimate `library/**` is expected.

## Annotation boundary

Creating a Zotero PDF annotation requires exact trusted page geometry.
Never invent rectangles solely from text matches.
