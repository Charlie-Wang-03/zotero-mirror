# Configuration

Normal hosted deployment uses GitHub repository variables and Actions secrets,
so users do not need to commit account identifiers or credentials.

See:

- [Quickstart](../docs/QUICKSTART.md)
- [Configuration](../docs/CONFIGURATION.md)
- [Access modes](../docs/ACCESS_MODES.md)

Committed JSON files remain safe policy/default surfaces:

- `mirror.json`: no user ID is shipped;
- `access_mode.json`: defaults to `read_only`;
- `import_policy.json`: conservative generic import policy;
- `pdf_upload_policy.json`: public-PDF acquisition safeguards;
- `capabilities.json`: machine-readable capability boundaries.

Matching `*.example.json` files support local development and inspection.
