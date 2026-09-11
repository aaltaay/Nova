# Security Policy

## Supported versions

Only the latest commit on `master` is supported. Desktop builds are published as GitHub Release assets on tag `vNNN`. Older tags are historical.

## Reporting a vulnerability

Use [GitHub Security Advisories](https://github.com/aaltaay/Nova/security/advisories/new) for this repository.

Do not open a public GitHub issue for an undisclosed vulnerability. Do not attach `.env` files, API keys, session cookies, or brokerage account identifiers.

Include:

- Affected component and version (`git rev-parse --short HEAD` or the `vNNN` tag)
- Steps to reproduce
- Impact (data exposure, order placement, local process control)
- A proof of concept you can share safely

## Authentication model

Nova is a local-first workstation. The API is not a hosted trading backend.

- Bind the API to loopback (`NOVA_API_HOST=127.0.0.1`). That is the supported default.
- When `NOVA_API_KEY` is set, mutating `/api/*` routes require the `X-Nova-Api-Key` header.
- Binding to a public interface (`0.0.0.0`) requires `NOVA_API_KEY`. Do not expose the API to the internet.
- `POST /api/config` always requires a configured `NOVA_API_KEY`, including on loopback. CORS only limits browser origins; any local process can still call `127.0.0.1:8000` and rewrite Alpaca keys / feed settings into `.env`. The Desktop sidecar provisions the key and sends it. Vite Settings needs the same value as `VITE_NOVA_API_KEY` or `localStorage.nova_api_key`. Config writes log the changed key names at INFO; secret values are never logged.

See `.env.example` for configuration. Secrets belong in `.env` only. `.env` is gitignored and must stay that way.

## Credentials and git history

A `.env` with Alpaca news keys was present in early commits (April 2026) and removed from the tree on 2026-07-10. Those keys were revoked before this repository was published. Treat any credential found in history as burned. Create new keys in the vendor console; never restore a historical `.env`.

No GitHub personal access tokens, OpenAI keys, Finnhub keys, R2 secrets, or IBKR passwords are in the current tree.

## Trading safety

- Scanner prices, charts, Level 2, and Time & Sales come from Interactive Brokers only.
- Alpaca is news and listing metadata, not a price feed.
- Orders go through `backend/ibkr/` and `execution.service.execute` only.
- Spend requires `IBKR_ENABLED` and `IBKR_ORDERS_ENABLED`. Live money also requires `IBKR_LIVE_TRADING_CONFIRMED`.
- `auto_live` is rejected in code. Do not patch that gate out.

## Security program

- [`security/findings-registry.json`](security/findings-registry.json) -- SEC-001 through SEC-008
- [`security/tooling.md`](security/tooling.md) -- pip-audit, Semgrep, Gitleaks, OSV-Scanner
- [`tools/security_audit.py`](tools/security_audit.py) -- local audit helper
- CI runs Gitleaks, OSV-Scanner, Semgrep, and the builtin audit on every pull request
