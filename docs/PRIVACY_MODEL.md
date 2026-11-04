# Privacy model

The project separates **public infrastructure** from **private instance data**.

## Reusable upstream may contain

- generic Python implementation;
- GitHub Actions workflows;
- capability and policy defaults;
- documentation;
- synthetic fixtures and regression tests.

## Reusable upstream must not contain

- a real Zotero user ID;
- API keys or other credentials;
- generated `library/**` data;
- personal notes or annotations;
- full-text papers;
- real write receipts;
- production item, attachment, annotation, or note identifiers.

`scripts/validate_public_tree.py` enforces the structural part of this
contract in CI.


## Runtime enforcement

The privacy rule is not documentation-only.

For a configured real instance:

- **Instance Preflight** rejects a public repository;
- **Sync Zotero** refuses to mirror real library data in a public repository;
- **Zotero Write** refuses mutations in a public repository;
- **Manage Zotero Access Mode** refuses to open write mode in a public repository.

This means skipping the recommended onboarding sequence does not bypass the
private-deployment boundary.


## Public release history boundary

A public Git repository exposes not only its current tree but also the
reachable commit history and possibly historical Actions logs. A clean
`main` tree is not sufficient to publish a former private development repo.

The public release must be generated as a new Git root containing only audited
source files. It must not inherit private development commits or any real
instance history.
