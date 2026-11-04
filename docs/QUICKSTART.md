# Quickstart

Goal: create a **private, read-only Zotero mirror in about 10–15 minutes**.
Normal deployment requires no local clone.

## 1. Create a private repository from the template

In the public `zotero-mirror` GitHub repository:

1. click **Use this template**;
2. choose **Create a new repository**;
3. set visibility to **Private**;
4. keep the default branch as `main`.

Do not use a public fork for a real Zotero library. A public repository cannot
be retroactively made safe by deleting a committed mirror: its Git history may
still expose that data.

See [Template deployment](TEMPLATE_DEPLOYMENT.md) for the reason.

## 2. Create a dedicated read-only Zotero API key

Open Zotero's API Keys page:

<https://www.zotero.org/settings/keys>

Create a dedicated key for this mirror with:

- personal library access;
- notes access;
- file access;
- **write access disabled**.

The key is a secret. Never paste it into a repository file, issue, commit, or
chat transcript.

The same Zotero page also shows the numeric **User ID** used by the Web API.

## 3. Add one variable and one secret

In the private repository, open:

**Settings → Secrets and variables → Actions**

Create this repository variable:

| Variable | Value |
| --- | --- |
| `ZOTERO_USER_ID` | your numeric Zotero user ID |

Create this repository secret:

| Secret | Value |
| --- | --- |
| `ZOTERO_API_KEY_READONLY` | the dedicated read-only Zotero key |

Do **not** set `ZOTERO_MIRROR_ENABLED` yet.

## 4. Run First Run

Open:

**Actions → First Run → Run workflow**

Run it from the default branch.

**First Run** combines the initial read-only checks and the first mirror build:

- repository visibility must be Private;
- the key must belong to `ZOTERO_USER_ID`;
- library, notes, and file access must be present;
- the read-only key must not have write permission;
- the Zotero snapshot must reconcile consistently;
- the generated mirror must pass strict validation;
- only then is `library/` committed.

This includes the read-only checks exposed separately by **Instance Preflight**,
which remains available as a diagnostic workflow.

When the run succeeds, its GitHub Actions summary shows the next step.

## 5. Enable ongoing sync

Only after **First Run** succeeds, create this repository variable:

| Variable | Value |
| --- | --- |
| `ZOTERO_MIRROR_ENABLED` | `true` |

Now **Sync Zotero** can run manually and on its three-hour schedule.

Inspect:

- `library/STATUS.md`;
- `library/sync_report.json`;
- generated paper, note, annotation, attachment, and full-text indexes.

A healthy mirror reports `CONSISTENT`.

## 6. Connect an AI client

Grant your AI client access to the **private instance repository**, not to your
Zotero API key.

Ask the client to read `AGENTS.md` before operating on the repository.

Examples:

- "What did I write about this paper?"
- "Find my unread papers on neural operators."
- "Audit this claim against my library."

## Optional: enable guarded writes

Only after the read-only mirror is healthy, continue with
[Configuration](CONFIGURATION.md#optional-read-write-mode) and
[Access modes](ACCESS_MODES.md).

The intended progression is:

```text
private template instance
→ First Run
→ verified read-only mirror
→ scheduled sync
→ optional separate read-write key
→ optional time-bounded write session
```
