# AGENTS.md

Repository-level contract for coding agents, reviewers and maintainers.

## Read first

- `README.md` for the public use case and capability limits;
- `docs/QUICKSTART.md` for private-instance onboarding;
- `docs/VALIDATION.md` and `SECURITY.md` when touching behavior or security;
- the relevant script or workflow for the task. Avoid loading unrelated docs.

The [Agentic Engineering Preferences](https://github.com/Charlie-Wang-03/agentic-engineering-preferences) are secondary maintainer defaults. Repository-local invariants and observed behavior take precedence.

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

The public template was created from an independent Git root. Keep this
upstream free of real Zotero instance data and private-history content.
Before future tags, exports or other external handoffs, inspect the changed
source, artifacts, reachable history and claims. A green offline CI result
is not proof of live Zotero operation or safe publication of private data.

Do not copy production `library/**`, private receipts, nonpublic test
records or private Git history into this repository.

## Local validation

```bash
python scripts/validate_project.py
```

This is the reproducible **offline upstream** validation command (Python 3.13,
standard library). It is also called by the upstream CI. Do not run this
public-tree validator on a configured private instance containing legitimate
`library/**` data; instance workflows have their own safety checks.

## Development flow

```text
generic change
→ local offline validation
→ focused branch / PR
→ upstream CI
→ inspect diff and safety boundaries
→ explicit approval before release or high-impact action
```

Upstream-only `validate_public_tree.py` is not a correctness validator for a
configured private instance, where legitimate `library/**` is expected.

## Annotation boundary

Creating a Zotero PDF annotation requires exact trusted page geometry.
Never invent rectangles solely from text matches.

## High-risk operations

Require explicit maintainer authorization for release/tag creation, repository
visibility or permission changes, branch protection or rulesets, force pushes,
history rewrites, credential operations, and destructive migrations. Never
execute a live Zotero write as part of upstream tests.

## Definition of done

Inspect the complete diff, run the relevant offline validation, verify that no
private data or credentials were introduced, keep README claims aligned with
evidence, and document any checks that were not performed. Prefer reversible
changes and do not auto-merge substantial agent-generated PRs.
