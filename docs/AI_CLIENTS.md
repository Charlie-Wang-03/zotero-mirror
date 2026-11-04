# AI client usage

The private GitHub repository is the AI-facing layer. Zotero remains canonical.

## Recommended contract

When connecting an AI coding or research client to the instance:

1. grant access to the **private repository**;
2. do not provide Zotero API keys in chat;
3. instruct the client to read `AGENTS.md`;
4. keep normal sessions read-only;
5. let repository workflows handle credentialed Zotero operations.

## Human-facing prompts

Users should not need to know Zotero item keys or request JSON.

Examples:

```text
What did I write about this paper?
Give me the next five unread papers on this topic.
Import this paper and classify it.
Store the canonical PDF in Zotero.
Turn these annotations into a note.
```

The AI layer resolves identifiers and expands the audited workflow internally.

## Write requests

For clients capable of modifying GitHub, the standard write surface is the
audited queue under `write_requests/pending/`.

The client should create at most one pending request per transaction and rely on
the repository workflow for credentials, version guards, receipts, and
read-only post-write verification.
