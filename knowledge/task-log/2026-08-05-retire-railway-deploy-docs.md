# 2026-08-05 -- Retire Railway from live deploy docs

- **Status:** completed
- **Agents:** parent
- **Domain:** docs
- **Related:** `CHANGELOG.md` §2026-08-05 -- Deploy docs: backend local-only, Railway retired

## Task

Update stalled docs that still claimed Railway (or any cloud host) for the Nova backend. User confirmed backend has no cloud host right now.

## Goal

Agents and humans reading live docs assume local / Desktop API only; CI no longer pretends to deploy to Railway.

## Why it mattered

Stale constitution/README/CI caused wrong infra advice (e.g. Terraform framed around Railway) and risked agents trying cloud deploy paths that no longer exist.

## What we changed

- `AGENTS.md` §4 / §8 + maintenance log: Railway removed; backend local-only; Vercel optional for static UI
- `README.md` Deploy section aligned
- `.env.example`, `frontend/.env.example`, chart API comment, security agent, `commit-push-deploy.mdc`
- `.github/workflows/deploy.yml`: renamed to CI; removed Railway deploy job
- `railway.toml*` marked DEPRECATED; Railway prebuild script comments updated to legacy/no-op

## How it works now

- API: `Run Nova.bat`, Desktop sidecar, or local uvicorn on `127.0.0.1:8000`
- Optional hosted UI: Vercel static only (must have a reachable API if not localhost)
- GitHub Actions: test/build/audit only -- no backend cloud deploy
- Historical CHANGELOG / PROBLEM_LOG Railway entries remain as history

## Why this approach

- Corrected live SoT docs first (highest agent leverage) instead of a full archaeology rewrite of old log entries
- Removed the CI deploy job (active lie) rather than leaving a skip-if-no-token Railway path
- Kept deprecated `railway.toml` files with banners instead of deleting immediately -- low risk if an old dashboard still points at them; easy follow-up delete
- Did not invent a new cloud backend; documented the real local-first posture

## Verification

- Grep/review of live docs and workflow: no remaining "Backend: Railway" claim in `AGENTS.md` / `README.md`
- Workflow file ends at agent-contract job (no Deploy to Railway job)

## Follow-ups

- Delete deprecated `railway.toml*` and rename/remove `check-railway-api-base.mjs` when no env still sets `RAILWAY_*`
- Confirm whether Vercel frontend is still in active use; if not, retire that claim the same way

## Keywords

Railway, deploy, docs, local-only, Vercel, CI, AGENTS.md, backend hosting
