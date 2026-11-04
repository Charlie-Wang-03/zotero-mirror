# Configuration

`zotero-mirror` uses GitHub repository variables for non-secret instance
identity and GitHub Actions secrets for credentials.

For normal hosted deployment, users do **not** need to edit JSON config files.

## Minimal first-run configuration

Before **First Run**, configure only:

### Repository variable

| Name | Purpose |
| --- | --- |
| `ZOTERO_USER_ID` | Numeric Zotero Web API user ID |

### Repository secret

| Name | Required permissions |
| --- | --- |
| `ZOTERO_API_KEY_READONLY` | library + notes + files; **no write** |

First Run verifies this key against Zotero's `/keys/current` endpoint and then
builds the first trusted mirror.

## Enable ongoing synchronization

After First Run succeeds, add:

| Name | Value |
| --- | --- |
| `ZOTERO_MIRROR_ENABLED` | `true` |

This enables manual and scheduled **Sync Zotero** jobs.

Keeping this switch off until bootstrap succeeds prevents scheduled sync from
racing ahead of initial validation.

## Optional read-write mode

Add write support only after the read-only mirror is healthy.

### Additional variable

| Name | Value |
| --- | --- |
| `ZOTERO_WRITE_ENABLED` | `true` |

### Additional secret

| Name | Required permissions |
| --- | --- |
| `ZOTERO_API_KEY_READWRITE` | library + notes + files + write |

The read-only and read-write keys must both belong to the configured
`ZOTERO_USER_ID`.

Enabling `ZOTERO_WRITE_ENABLED` does **not** permanently enable writes.
`config/access_mode.json` still defaults to `read_only`. Run
**Instance Preflight** with `check_write=true`, then use
**Manage Zotero Access Mode** to open a 15–120 minute write session.

That workflow never enables destructive writes.

## Config files

The committed files are safe defaults and policy surfaces:

- `config/mirror.json` — API base and mirror behavior; no user ID is shipped;
- `config/access_mode.json` — current time-bounded access state;
- `config/import_policy.json` — conservative import/classification behavior;
- `config/pdf_upload_policy.json` — PDF acquisition and identity safeguards;
- `config/capabilities.json` — machine-readable capability boundaries.

Repository variables override instance identity where supported.

## Why two keys?

The separation is deliberate:

```text
routine sync / post-write verification
        ↓
ZOTERO_API_KEY_READONLY

explicit mutation
        ↓
ZOTERO_API_KEY_READWRITE
```

Before any mutation, the write workflow verifies **both** keys. A broken or
missing read-only verification path therefore fails before the mutation starts.
