# Contributing to Nova

Nova is a local-first Interactive Brokers workstation. Changes that touch trading, market data, or delivery must stay inside the project constitution.

## Before you open a pull request

1. Read [AGENTS.md](AGENTS.md). That file is the law for feed ownership, order gates, and modularity.
2. Copy `.env.example` to `.env`. Never commit `.env`, tokens, or account numbers.
3. Keep new modules under 400 lines. Do not add product logic to `backend/main.py` or `frontend/src/App.tsx`.
4. Do not enable or implement `auto_live`. Unattended live trading is rejected in code.

## How to land a change

- Start from a clean `origin/master` tip on a new focused branch. Do not pile a change on a dirty local worktree.
- Work on that focused branch. Open a ready (non-draft) pull request against `master`.
- Fill every section of [`.github/pull_request_template.md`](.github/pull_request_template.md). **Why this approach** and **Verified by** are required.
- Use `Closes #NNN` only when the entire issue is done. Use `Refs #NNN` for partial work.
- GitHub Actions merges ready pull requests when gating CI is green. Draft or the `do-not-merge` label holds a pull request.

## Verification

Run what the change can break:

```text
pytest backend/ -q
ruff check backend
cd frontend && npm run lint && npm test -- --run && npm run build
python3 tools/doc_invariants.py
```

Desktop installer changes also need the **Desktop pack** GitHub Actions job (`Nova-Setup-vNNN.exe` and `Nova-Portable-vNNN.exe`).

## Security

Report vulnerabilities through [GitHub Security Advisories](https://github.com/aaltaay/Nova/security/advisories/new). Do not open a public issue with exploit details or credentials. See [SECURITY.md](SECURITY.md).
