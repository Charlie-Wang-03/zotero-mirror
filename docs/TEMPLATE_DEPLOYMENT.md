# Template deployment

The intended product distribution is:

```text
public zotero-mirror template
        ↓ Use this template
new private repository
        ↓
user-specific Zotero mirror
```

## Template, not fork

A real Zotero mirror should be created with **Use this template**, not by making
a normal public fork.

A template instance is an independent repository and can be made Private. It
also starts with its own repository history instead of acting as a contribution
fork of the upstream project.

Forks remain appropriate for contributors working on `zotero-mirror` itself.

## Required visibility

Real instances must be **Private**.

This is enforced at runtime by:

- First Run;
- Instance Preflight;
- Sync Zotero;
- Zotero Write;
- Manage Zotero Access Mode.

The distributable upstream can be public because it contains only code,
documentation, policy defaults, and synthetic fixtures and has a fresh clean
Git root. Never expose a historical private development repository simply by
changing its visibility.

## Template-safe defaults

A newly generated instance starts with:

```text
zotero_user_id = ""
mode = read_only
allow_destructive = false
no credentials
no generated library
no write receipts
scheduled sync disabled until ZOTERO_MIRROR_ENABLED=true
```

The first user-specific data is generated only after a private instance passes
the First Run safety checks.


## Upstream CI does not become instance CI

The template necessarily copies the upstream workflow files into the new
repository, but the public-product regression suite is scoped to the canonical
upstream repository.

In generated private instances, **Upstream CI** is skipped. This is deliberate:
after First Run, a valid private instance contains real `library/**` data and
may temporarily enter `read_write` mode, both of which would violate the
public-upstream invariants by design.

Instance correctness is enforced instead by the operational workflows
themselves:

- First Run;
- Sync Zotero;
- Instance Preflight;
- Zotero Write;
- Manage Zotero Access Mode.

This separation prevents a healthy private mirror from being falsely reported
as a contaminated public source tree.
