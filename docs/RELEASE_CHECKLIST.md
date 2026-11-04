# v0.1.0 public release checklist

**Public publication is blocked until every gate is satisfied.**

## Source and history

- [ ] Prepare generic source tree, safe defaults, documentation and MIT license.
- [ ] Confirm `library/` and `write_requests/` contain only README placeholders.
- [ ] Confirm example annotations and saved searches are synthetic.
- [ ] Scan all source files for secrets, user IDs, personal tags, paper titles,
      production repository identifiers and copyrighted full-text content.
- [ ] Verify public upstream CI succeeds, including negative/synthetic tests.
- [ ] Confirm no repo-owned secret values are copied to the release.
- [ ] Create **a new repository with an independent initial commit** from the
      clean source tree. **Do not convert the historic private development repo
      to Public.** Its prior Git commits and workflow logs are not part of
      the release artifact.
- [ ] Check the new repository contains one new root commit, only the expected
      default branch, and no inherited development history or workflow logs.
- [ ] Scan the new public candidate's entire reachable history before making
      it Public.

## Deployment behavior

- [ ] Public template repo runs no live Zotero operation by default.
- [ ] First Run refuses a public *instance* and checks private, default branch,
      user identity, read-only key and strict snapshot consistency.
- [ ] Sync requires explicit `ZOTERO_MIRROR_ENABLED=true`.
- [ ] Scheduled sync is available to generated private instances.
- [ ] Optional writes require a separate read-write key and a short-lived
      session; destructive writes remain disabled by default.
- [ ] Public-upstream CI is skipped in generated private instances.
- [ ] README documents unsupported/native-Desktop-only operations.
- [ ] No secret values, personal identifiers, or real library snapshots in
      GitHub Actions logs or fixtures.

## Publication

- [ ] Set repository visibility to Public **only after clean-root audit**.
- [ ] Keep GitHub Template repository enabled.
- [ ] Enable appropriate security reporting and community settings.
- [ ] Tag and document the initial release only after all gates pass.
- [ ] Independently verify the public URL without authentication.

## Evidence boundaries

The previous private canary validated read-only First Run and two isolated
create/read/patch/delete cycles. It did **not** validate every feature or
full request-queue/receipt orchestration. Do not overstate coverage in a
public announcement.
