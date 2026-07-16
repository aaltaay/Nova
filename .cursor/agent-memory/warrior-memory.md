# Warrior Trading Navigator memory (living)

Living knowledge for the Nova `warrior` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/warrior.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-16T16:20:00Z
source_revision: 5c8b878
result: PASS
metrics:
  hosts_mapped: 5
  day_trade_dash_widgets: 6
  lms_courses_listed: 12
  ba101_chapters: 15
blockers: []
dashboard_freshness: refresh-required
notes: "Initial map landed in Authenticated-Site-Map.md; agent installed and canvas migrated to agent-warrior."
```

---

## How to continue improving

> Use the warrior subagent to navigate Warrior Trading

> Use the warrior subagent to map Day Trade Dash

> Improve the warrior agent — work the next backlog item in `.cursor/agent-memory/warrior-memory.md`.

Durable navigation facts → `warrior.md` and/or Obsidian `Authenticated-Site-Map.md`. Run history stays here.

---

## Backlog

- [ ] Map SS101 chapter index the same way as BA101.
- [ ] Inventory News Room stream join + layout presets under Settings → Layouts.
- [ ] Confirm Top Gainers full column set vs Gappers side-by-side.
- [ ] Document web simulator entry from dashboard links (read-only).
- [ ] Add Graphify query smoke: "Warrior Day Trade Dash widgets" after vault graph rebuild at repo-root `graphify-out/`.

### Completed

- [x] 2026-07-16 — Live map of dashboard, LMS catalog, BA101 chapters, Day Trade Dash widgets.
- [x] 2026-07-16 — Access runbook + `scripts/open_warrior_site.ps1` + persistent profile.
- [x] 2026-07-16 — Agent scaffolded and specialized; unmanaged canvas → `agent-warrior.canvas.tsx`.

---

## Known traps

- PowerShell eats bare `@eN` refs — always quote `'@eN'`.
- Screenshot path with backslashes may be treated as a selector — use `./.tmp/...` forward slashes.
- Do not bookmark `chatroom…/sso/?data=` JWTs; re-enter via `/chat-room-access/`.
- Analytics cookies alone do not authenticate; use the persistent profile.
- Vault `knowledge/obsidian/graphify-out/` is the wrong graph target — canonical is repo-root `graphify-out/`.

---

## Run log

Newest first. Keep entries short. No secrets.

<!-- RUN_LOG_START -->

### 2026-07-16 — Agent install + canvas migration

- **Scope:** Promote Warrior site map into dedicated `warrior` specialist; retire unmanaged `warrior-site-map.canvas.tsx`.
- **Result:** PASS (install)
- **Learning:** Nova Agent owns Nova Home / unmanaged cleanup; Warrior navigation belongs on `agent-warrior`.
- **Files updated:** `warrior.md`, `warrior-memory.md`, registry, routing, `agent-warrior.canvas.tsx`.

### 2026-07-16 — Initial live site map

- **Scope:** Authenticated browse of dashboard, LMS, Day Trade Dash.
- **Result:** PASS
- **Evidence:** Members Dashboard, Learner Home, chatroom dashboard after Disclaimer ACCEPT.
- **Files updated:** `docs/warrior-authenticated-access.md`, `Authenticated-Site-Map.md` (prior commit `5c8b878`).

<!-- RUN_LOG_END -->
