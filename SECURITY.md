# Security Policy

## Reporting a vulnerability

If you discover a security issue in Nova, please report it responsibly:

- **Email:** `security@example.com` *(replace with your contact before production use)*
- **Do not** open a public GitHub issue for undisclosed vulnerabilities.

Include steps to reproduce, affected components, and any proof-of-concept you can share safely.

## Supported versions

This repository is under active development. Only the latest commit on the default branch receives ad-hoc review. Do not deploy to production without an independent security assessment.

## Authentication model

Nova is designed as a **local-first desktop workstation**:

- Mutating `/api/*` routes require the `X-Nova-Api-Key` header when `NOVA_API_KEY` is set in `.env`.
- When bound to loopback (`NOVA_API_HOST=127.0.0.1`), mutating routes are allowed without a key for single-operator desktop use.
- When bound to a public interface (`0.0.0.0`), `NOVA_API_KEY` is **required** for mutating routes.

See `.env.example` for configuration guidance.

## Security program

Structured findings, remediation history, and compensating controls live in:

- [`security/findings-registry.json`](security/findings-registry.json) — SEC-001 through SEC-008 with CVSS/CWE metadata
- [`security/schema.md`](security/schema.md) — registry schema
- [`security/tooling.md`](security/tooling.md) — pip-audit, semgrep, gitleaks, osv-scanner runbooks
- [`tools/security_audit.py`](tools/security_audit.py) — local audit helper

## Scope notes

- No live credentials, API keys, or brokerage account identifiers are committed.
- Optional modules (IBKR Gateway, Pinecone, R2 archive) require operator-supplied secrets via `.env` only.
