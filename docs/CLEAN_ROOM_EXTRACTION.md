# P0 — Clean-room extraction

The reusable repository was initialized as a new Git root rather than as a fork
or history rewrite of a production mirror.

## Extracted

- mirror/snapshot logic;
- consistency guards;
- controlled write executor;
- PDF Storage protocol support;
- annotation and rich-note helpers;
- Saved Search support;
- offline validators;
- GitHub Actions workflow patterns.

## Rewritten or parameterized

- Zotero user identity;
- secret names;
- repository URLs and user agents;
- import fallback collections;
- workflow enablement;
- validation fixtures.

## Deliberately excluded

- all production `library/**` data;
- full-text corpus;
- personal notes and annotations;
- completed/failed write receipts;
- production acceptance evidence;
- production Git history and feature branches.

## P0 acceptance checklist

- independent Git root: PASS;
- no inherited production commits or branches: PASS;
- no generated library data: PASS;
- no real write receipts: PASS;
- no production Zotero user ID: PASS;
- no production paper/item/attachment/note identifiers in the reachable
  history: PASS;
- generic read-only/read-write secret names: PASS;
- synthetic annotation/rich-note fixtures: PASS;
- network workflows opt in through repository variables: PASS;
- public-tree privacy validator installed: PASS.

Release safety requires a newly generated independent Git root containing
only the audited template source tree. A historic private development
repository must not be changed directly to Public because its previous commit
history and workflow logs may reveal development-only information.
