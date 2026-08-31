# 2026-08-31 -- Public marketing page for nova.altaystudio.com

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / productization
- **Related:** `CHANGELOG.md` §2026-08-31 Public domain · `Nova-Roadmap-Status.md` History 2026-08-31 · Phase J local-first

## Task

Replace the public domain that was serving the Vite trading SPA with a static front page: custom CSS, product features, real desk screenshots, and the Nova-public GitHub link. Use Higgsfield art where possible.

## Goal

`nova.altaystudio.com` tells the product story and points at source. It does not pretend to be a hosted scanner.

## Why it mattered

Hosting the app on Vercel implied a live cloud desk. Nova is local-first (IB Gateway on the operator PC). A marketing page matches Phase J and stops visitors from hitting a backend-unreachable SPA.

## What we changed

- Added `site/` (HTML, CSS, JS, screenshots, vercel.json)
- Pointed live docs (`AGENTS.md` §4/§8, `README.md` Deploy, `frontend/.env.example`, `commit-push-deploy.mdc`) at the marketing page
- Primary CTA is https://github.com/aaltaay/Nova-public

## How it works now

Vercel Root Directory must be `site` (static, no build). The scanner still runs via `Run Nova.bat` or Desktop. This domain has no API.

## Why this approach

**HTML + CSS in-repo** instead of a Higgsfield-hosted Worker: the user named `nova.altaystudio.com` and asked for a front page, not a second product on a Higgsfield subdomain. **Real screenshots** instead of fake UI generations: the ask was screenshots vs hosting the app. **Higgsfield plates deferred:** MCP session expired after re-auth (`FNF API GET /mcp/workspaces` 401); reconnecting the Higgsfield connector is required before generated hero/section art can land in `site/assets/`. CSS spotlight, grid, and a hue-rotated existing `hero-bg.png` close the atmosphere gap until then.

Rejected: swapping `frontend/index.html` (would break the local desk), hosting a Higgsfield scroll-scrub film as the canonical URL (wrong domain, heavier than asked).

## Verification

Local static server `py -3 -m http.server 4177` in `site/` (assets HTTP 200). Playwright: h1 at (115, 224), lightbox opens, GitHub CTA `https://github.com/aaltaay/Nova-public`, Features nav. `py -3 tools/doc_invariants.py` OK.

## Follow-ups

Reconnect Higgsfield MCP and drop generated plates into `site/assets/`. In Vercel, set Root Directory to `site` or the old SPA keeps shipping on git push.

## Keywords

marketing, landing, vercel, nova.altaystudio.com, Nova-public, local-first, site/
