# Troubleshooting

## First Run is unavailable

Confirm that GitHub Actions is enabled for the repository and that the
`.github/workflows/first-run.yml` workflow exists on the default branch.

## First Run says the repository is not private

Real Zotero mirrors are not allowed in public repositories. Change the instance
visibility to Private before retrying.

This is a hard runtime boundary shared by First Run, Instance Preflight, Sync,
Write, and Manage Zotero Access Mode.

## First Run says to use the default branch

Rerun **First Run** from the repository's default branch. Bootstrap commits the
trusted `library/` mirror to that branch.

## Read-only key unexpectedly has write permission

Create a new dedicated Zotero API key with write permission disabled, replace
`ZOTERO_API_KEY_READONLY`, and rerun **First Run** or **Instance Preflight**.

The project intentionally rejects an over-privileged key in the read-only slot.

## Key belongs to a different user

Check `ZOTERO_USER_ID` against the numeric User ID shown on Zotero's API Keys
page. Both optional write and required read-only keys must belong to that same
user.

## Missing notes or files permission

Edit or replace the Zotero key so that it can read personal-library notes and
files. Rerun **First Run**.

## Sync workflow is skipped

First confirm that First Run has succeeded. Then verify:

```text
ZOTERO_MIRROR_ENABLED=true
```

GitHub Actions treats an unset value as disabled.

## Write workflow is skipped

Verify:

```text
ZOTERO_MIRROR_ENABLED=true
ZOTERO_WRITE_ENABLED=true
```

Then run **Instance Preflight** with `check_write=true`.

## WRITE_MODE_DISABLED or WRITE_MODE_EXPIRED

Run **Manage Zotero Access Mode** and open a new time-bounded `read_write`
session.

## GitHub-hosted job has zero steps

If a run finishes before any step receives a runner, the failure is outside the
Python validation layer. Check GitHub Actions account/repository availability,
usage, billing, and policy settings before debugging the scripts themselves.
