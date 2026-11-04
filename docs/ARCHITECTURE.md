# Architecture

```text
Zotero Desktop / Web Library
        |
        | Zotero Sync + Web API
        v
private repository created from zotero-mirror
        |
        +-- read-only mirror workflow
        +-- deterministic library projection
        +-- audit / consistency guards
        +-- optional guarded write workflow
        |
        v
AI clients / research automation
```

## Trust model

Zotero is canonical. GitHub is an AI-friendly projection and audit layer.

Read-only synchronization and write authority use separate credentials. Writes
are explicit, time-bounded, version-guarded, receipted, and followed by a
read-only verification pass.

## Public infrastructure versus private data

The reusable upstream contains code, configuration defaults, documentation, and
synthetic fixtures only. Real deployments should normally be private because
their generated mirror can contain personal research memory and copyrighted
full text.
