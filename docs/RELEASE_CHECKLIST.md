# Public template and tagged-release checklist

## Public template publication — historical evidence

The reusable public repository was created on 2026-11-04 from an independent
Git root, rather than publishing the previous private development history.
The initial root commit was `274ad9089f1145e5116c36526fa0d13ec23c6221`.
The new upstream CI run
[41815575004](https://github.com/Charlie-Wang-03/zotero-mirror/actions/runs/41815575004)
completed successfully. These are **observations**, not proof that all
Zotero Web API paths are end-to-end verified.

Privacy and source-tree constraints remain active after publication:

- Never commit a real `library/**` snapshot or write receipts to public upstream.
- Keep only synthetic fixtures; no API keys, account identifiers, real notes,
  restricted full text, or private development history.
- A real mirror instance must be **Private** and start `read_only`.
- Changes touching Zotero write behavior need version-guard and post-write
  verification review in addition to the offline suite.

## Before creating a tagged Release

- [ ] Confirm maintainer approval for the tag and Release.
- [ ] Identify the exact target commit and check its public-source CI.
- [ ] Run `python scripts/validate_project.py` and inspect the resulting diff.
- [ ] Review all modified files, Git history and packaged artifacts for private
      content, licenses, generated data and accidental credentials.
- [ ] Check README and `docs/VALIDATION.md` accurately distinguish synthetic
      tests, past isolated canary tests and genuinely verified live paths.
- [ ] Confirm defaults remain `read_only`, destructive writes disabled,
      real-library workflows private-only and recurring sync opt-in.
- [ ] Confirm no user-instance credentials or data are included in artifacts.
- [ ] Only then create the tag and Release, clearly listing limitations.
- [ ] Verify the published tag, source archive and public URL independently.

## Evidence boundaries

The previous isolated private canary validated First Run plus two
create/read/patch/delete cycles. It did **not** establish complete
end-to-end validation of PDF uploads, annotations, Saved Searches,
or the full request-queue/receipt orchestration. See
[Validation and limitations](VALIDATION.md).
