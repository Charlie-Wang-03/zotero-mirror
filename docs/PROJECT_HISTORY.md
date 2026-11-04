# Project decisions

This document records only generic product lifecycle information. It contains
no private research identifiers or credentials.

- **2026-09:** Clean-room Python implementation extracted into an
  independent Git source tree; generic configuration and synthetic fixtures
  prepared.
- **2026-09:** Private-instance onboarding and First Run template workflow
  developed.
- **2026-11-04:** Private canary tests confirmed initial read-only sync and
  two isolated create/read/patch/delete workflows.
- **2026-11-04:** The earlier discontinuation decision was superseded. The
  reusable template was published from a clean independent Git root as a
  public repository; this does not by itself constitute a tagged release.

Public release must use a clean Git root. The historical private development
repository is not itself a public release artifact.
