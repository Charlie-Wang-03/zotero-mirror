# Access modes

Write capability has two independent gates.

## Gate 1 — instance write feature

Repository variable:

```text
ZOTERO_WRITE_ENABLED=true
```

and secret:

```text
ZOTERO_API_KEY_READWRITE
```

must exist.

This only means the instance is capable of guarded writes.

## Gate 2 — time-bounded session

The default repository state is:

```text
mode = read_only
allow_destructive = false
```

To open a write session:

1. open **Actions → Manage Zotero Access Mode**;
2. choose `read_write`;
3. choose 15, 30, 60, or 120 minutes;
4. run the workflow.

The workflow commits a timestamped expiry to `config/access_mode.json`.

After the expiry, `zotero_write.py` rejects new writes even if
`ZOTERO_WRITE_ENABLED=true`.

To close the session early, run the workflow again with `read_only`.

## Destructive operations

The onboarding workflow **never** sets `allow_destructive=true`.

Destructive operations require the repository's separate destructive gate and
confirmation semantics. They are not part of normal P1 onboarding.

Native Zotero Duplicate Merge remains Desktop-only and must not be simulated by
moving children and deleting a duplicate.
