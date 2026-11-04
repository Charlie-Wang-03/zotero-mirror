# Security policy

## Private deployments

A real Zotero mirror may include personal notes, research metadata, reading
history, annotations, and copyrighted full text. Deploy into a **private**
repository. Do not publish a repository that has ever committed a real
`library/**` mirror, even if it has since removed those files.

The reusable source tree must contain no real Zotero identifiers, personal
research artifacts, credentials, or production history.

## API keys

Configure only in GitHub Actions repository **Secrets**:

- `ZOTERO_API_KEY_READONLY`: personal-library, notes and files access,
  write permission **disabled**.
- `ZOTERO_API_KEY_READWRITE`: optional; separate, least-privilege key
  for explicitly approved writes.

Never paste API keys into chat, pull requests, commits, issue comments, logs,
or generated reports.

## Runtime safety

First Run, Sync Zotero, Zotero Write and Manage Zotero Access Mode refuse
non-private instance repositories. A new private instance starts read-only.
Write access is opt-in, expires, and rejects stale item versions. Destructive
operations are disabled by default.

## Responsible disclosure

Do not report credential leaks or private-data vulnerabilities in a public
issue. Open a GitHub private security advisory when the feature is available,
or contact the repository owner privately.

This is community-maintained tooling, not an official Zotero service.
