# First Run

**First Run** is the bootstrap workflow for a newly created private
`zotero-mirror` instance.

It exists so a user does not have to manually coordinate a preflight and a
separate first sync.

## Inputs

First Run intentionally has no form fields that accept secrets.

Before running it, configure:

```text
Repository variable:
ZOTERO_USER_ID

Repository secret:
ZOTERO_API_KEY_READONLY
```

Do not enable scheduled sync first.

## What it does

```text
verify private repository
→ verify default branch
→ verify Zotero user/key relationship
→ reject an over-privileged read-only key
→ build a fail-closed Zotero snapshot
→ strict mirror validation
→ commit only library/
→ write a GitHub Actions summary
```

It does not:

- use the read-write key;
- enable write mode;
- modify Zotero;
- enable scheduled sync;
- enable destructive operations.

## Success

A successful workflow writes a summary beginning with:

```text
zotero-mirror first run complete
```

The instance now has a trusted initial mirror.

The user can then set:

```text
ZOTERO_MIRROR_ENABLED=true
```

to enable normal manual and scheduled synchronization.

## Failure

If First Run fails, do not enable scheduled sync.

Fix the failing configuration or Zotero permission and rerun **First Run**.
The workflow is safe to rerun: it reconciles against the canonical Zotero
library and only commits a mirror that passes strict validation.

See [Troubleshooting](TROUBLESHOOTING.md).


## What happens to Upstream CI?

Creating an instance from the template may create a GitHub Actions run for the
copied **Upstream CI** workflow, but its job is scoped to the canonical
`Charlie-Wang-03/zotero-mirror` repository and is skipped in generated
instances.

That is expected. A private instance is allowed to contain real `library/**`
data after First Run, while the public upstream is not.
