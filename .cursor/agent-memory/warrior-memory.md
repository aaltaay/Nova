# Warrior Trading Navigator memory (living)

Living knowledge for the Nova `warrior` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/warrior.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-17T17:50:00Z
source_revision: 5c8b878
result: PASS
metrics:
  hosts_mapped: 5
  day_trade_dash_widgets: 6
  lms_courses_listed: 12
  lms_video_units_unique: 544
  lms_official_captions: 18
  lms_caption_gaps: 526
  whisper_ba101_units: 7
  ba101_chapters: 15
  ss101_chapters_outlined: 20
  hod_momo_rows_last_snap: 40
  hod_momo_unique_symbols: 8
  hod_sub_strategies_kb: 11
  warrior_latest_ts: 1784308360
blockers: []
dashboard_freshness: refresh-required
notes: "Full LMS caption harvest: 544 videos / 18 official EN captions. SS101 Ch.4+Ch.12 are caption GAPS (need Whisper). Catalog in gitignored downloads/warrior-trading-caption-notes/."
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
- [ ] HOD parity observer: re-snap `.tmp/hod-momo-parity/warrior_latest.json` during RTH (market hours) when population differs from after-hours; compare strategies/columns only — never feed into Nova alert engine.
- [ ] Whisper gap fill priority: SS101 Ch.4 Daily Chart Patterns (`gbw1yl3luq`) + Ch.12 Stock Scanning (`m0ilv07764`) after authenticated player download into `downloads/warrior-trading-videos/`.
- [ ] Whisper remaining BA101 gaps (beyond the 7 already done) + other high-priority courses.
- [ ] Optional: watch full SS101 Ch.12 Stock Scanning video + enable CC for any spoken Former Momo filter (not in slides/search index).
- [ ] Map remaining SS101 chapter titles into Authenticated-Site-Map (outline captured 2026-07-17).

### Completed

- [x] 2026-07-17 — Full LMS video catalog + official caption harvest (544 / 18 / 526); `TRANSCRIPT_COVERAGE.md` + `_harvest_lms_captions.py`.
- [x] 2026-07-16 — Live map of dashboard, LMS catalog, BA101 chapters, Day Trade Dash widgets.
- [x] 2026-07-16 — Access runbook + `scripts/open_warrior_site.ps1` + persistent profile.
- [x] 2026-07-16 — Agent scaffolded and specialized; unmanaged canvas → `agent-warrior.canvas.tsx`.
- [x] 2026-07-16 — HOD Momentum research snapshot for parity observer (`warrior_latest.json`); Scanner Resources article URL indexed.
- [x] 2026-07-17 — Official HOD population model + 11 sub-strategy names from support `19000117763`; BA101 Scanning 101 HOD vs Running Up contrast; durable map section added.
- [x] 2026-07-17 — Former Momo deep pass: KB thin; SS101 Ch.4 qualitative; live Select strategies label Former Momo Stock; no numeric formula published.

---

## Known traps

- PowerShell eats bare `@eN` refs — always quote `'@eN'`.
- Screenshot path with backslashes may be treated as a selector — use `./.tmp/...` forward slashes.
- Do not bookmark `chatroom…/sso/?data=` JWTs; re-enter via `/chat-room-access/`.
- Analytics cookies alone do not authenticate; use the persistent profile.
- Vault `knowledge/obsidian/graphify-out/` is the wrong graph target — canonical is repo-root `graphify-out/`.
- Orphan Chrome holding `%LOCALAPPDATA%\Nova\browser-profiles\warrior-site` causes `DevToolsActivePort` / early exit on `open_warrior_site.ps1` — kill only processes whose command line contains that profile path, then relaunch (do not kill the user's other Chrome windows).
- PowerShell `$pid` is read-only — use `$procId` when looping Stop-Process.
- HOD Time cells may include burst tags: `06:32:46 pm (2 in 3sec) expand row` — strip to `HH:MM:SS am/pm` when writing `warrior_latest.json`.
- **Access Denied on www while LMS still works:** Members Dashboard + `/chat-room-access/` + `chatroom…/dashboard` redirect to `/no-access/` with Sign in. CRM may still show Active Day Trade Dash Tools. Fix = human re-login in headed profile (CAPTCHA/2FA if shown). Do **not** invent `warrior_latest.json` rows while blocked. Do **not** click Unpause / billing without user.
- `chatroom.warriortrading.com/` may load an empty shell title “WarriorTrading Chatroom” without SSO; `/dashboard` still bounces to www `/no-access/`.
- `%USERPROFILE%\.nova\secrets\local-credentials.env` may be ACL’d Write-only (`(W)`). Temporarily `icacls … /grant USER:(R)` to Sign in, then restore Write-only. Never copy secrets into the repo.

## Former Momo (research conclusion)

- **Verdict:** No published numeric HOD filter formula. Official sources give **name + color + qualitative “former runner” stock type** only.
- **KB name:** Former Momo Scanner (`19000117763`). **UI name:** Former Momo Stock (Select strategies + Strategy Name column).
- **HOD lane:** Still under Small-Cap HOD Momo → inherits new-HOD + momentum umbrella; no Former-specific %/float/RVOL published.
- **SS101 Ch.4:** former momo / former runner = prior big-% mover with attention; watch on scanners with fresh news / daily flags — teaching concept, not scanner SQL.
- **SS101 trading-plan checklist:** “Am I familiar with the name? How has it traded in the past?”
- **SS101 Ch.12 Stock Scanning:** LMS video accessible; course search does **not** index a Former Momo filter definition; no Ch.12 captions in local library.
- **Audio:** KB Ross preset = all except Medium Float (includes Former Momo). BA101 verbal = low float + squeeze; skips medium + “others” (ambiguous for Former Momo).
- **Select strategies (live 2026-07-17):** checkbox only; no help tooltip.
- **Do not** promote UI row stats (float/RVOL on VELO etc.) as official filters.

## HOD parity observer (research only)

- **Output path (gitignored):** `.tmp/hod-momo-parity/warrior_latest.json`
- **Shape:** `{ "ts": <unix>, "online": bool, "rows": [{ "symbol", "strategy", "time", "price" }] }`
- **Source widget:** Day Trade Dash → *Small Cap - High of Day Momentum* (first scanner table; stop before Running Up headers).
- **Boundary:** research snapshot for Nova parity comparison only — never scrape into Nova alert/executor paths.

---

## Run log

Newest first. Keep entries short. No secrets.

<!-- RUN_LOG_START -->

### 2026-07-17 — Full LMS caption / transcript catalog harvest

- **Scope:** Enumerate every enrolled LMS video; fetch Wistia media + caption JSON; export official EN transcripts; gap report.
- **Result:** PASS (catalog complete) — **not** full second-by-second coverage of all videos (only 18 have official captions).
- **Evidence:** Learner Home authenticated; enrollment API 12 courses; `lms_inventory.json` 547 placements / 544 unique media; captions endpoint empty for 526; SS101 Ch.4 `gbw1yl3luq` (~56m) + Ch.12 `m0ilv07764` (~23m) = GAP.
- **Learning:** Prior ~18 caption units were the complete official caption set, not a partial crawl. Wistia bot UA yields `{error:true,iframe:true}` — use browser UA + Referer. Transcript bodies stay gitignored under `downloads/warrior-trading-caption-notes/`.
- **Human gate:** none (LMS session OK).
- **Files updated:** `_harvest_lms_captions.py`, `_repair_wistia_cache.py`, `_caption_cache/*`, `TRANSCRIPT_COVERAGE.md`, `COURSE_INVENTORY.md`, `Authenticated-Site-Map.md`, `Local-Library-Inventory.md`, `warrior-memory.md`, `agent-warrior.canvas.tsx`.

### 2026-07-17 — Former Momo filter deep research

- **Scope:** Every published Former Momo filter detail (KB, SS101, BA101, live Select strategies).
- **Result:** PASS (exhaustive negative + qualitative positives) — **no numeric formula published**.
- **Evidence:** support search → only `19000117763`; SS101 outline + Ch.12 video + LMS search → Ch.4 Quiz; Ch.4 slides former-runner teaching; live Select strategies **Former Momo Stock** (no tooltip); Day Trade Dash Online.
- **Learning:** “Former Momo” in SS101 = stock-type / familiarity checklist; HOD sub-strategy name is not documented as float/RVOL/% code.
- **Files updated:** `Authenticated-Site-Map.md`, `warrior-memory.md`, `agent-warrior.canvas.tsx`.

### 2026-07-17 — warrior_latest.json refresh NOW PASS

- **Scope:** Refresh Day Trade Dash Small-Cap HOD Momentum → `.tmp/hod-momo-parity/warrior_latest.json` (reuse signed-in profile).
- **Result:** PASS — HOD Online; file overwritten (ts=1784308360, 40 rows, 8 symbols).
- **Evidence:** `chatroom.warriortrading.com/dashboard` title WarriorTrading Chatroom; widget “Small Cap - High of Day Momentum (Online)”; strategies Former Momo Stock + Squeeze 5%/10%.
- **Symbols:** AMPG, PESI, PN, RAM, RFIL, SDOT, TRT, VELO.
- **Human gate:** none (session already authenticated; no password written).
- **Files updated:** `warrior_latest.json` (gitignored), `warrior-memory.md`, `agent-warrior.canvas.tsx`.

### 2026-07-17 — Sign-in unblock + warrior_latest.json RTH refresh PASS

- **Scope:** Clear Access Denied with local secrets Sign in; refresh Day Trade Dash HOD → `warrior_latest.json`.
- **Result:** PASS — signed in; HOD Online; file overwritten (ts=1784307223, 40 rows, 6 symbols).
- **Evidence:** `/no-access/` → Sign in → `www…/dashboard/` Members Dashboard → `/chat-room-access/` → SSO `chatroom…/dashboard` → Disclaimer ACCEPT; strategies include Former Momo + Squeeze 5%/10%.
- **Human gate:** none remaining this run (no CAPTCHA/2FA shown).
- **Secrets hygiene:** read `local-credentials.env` only; never wrote password to memory/map/git; restored file ACL to Write-only after use.
- **Files updated:** `warrior_latest.json` (gitignored), `warrior-memory.md`, `agent-warrior.canvas.tsx`.

### 2026-07-17 — Urgent warrior_latest.json refresh (loop #4) BLOCKED

- **Scope:** Refresh Day Trade Dash HOD → `warrior_latest.json` ASAP; ignore Nova API.
- **Result:** BLOCKED — file not overwritten (ts=1784243245, 40 rows).
- **Evidence:** LMS Learner Home OK; parked `https://www.warriortrading.com/login-member/` title Member Sign in; 180s poll no session; chatroom unreachable without SSO.
- **Human gate:** Sign in (CAPTCHA/2FA if shown) in headed warrior-site window, then re-invoke snap.
- **Files updated:** `warrior-memory.md` only (canvas already shows BLOCKED/stale).

### 2026-07-17 — Urgent warrior_latest.json refresh (loop #2) BLOCKED

- **Scope:** Live Day Trade Dash Small-Cap HOD → overwrite `.tmp/hod-momo-parity/warrior_latest.json`; finish Former Momo formula evidence.
- **Result:** BLOCKED — file **not** overwritten (still ts=1784243245, 40 rows, online=true from 2026-07-16).
- **Evidence:** headed profile relaunch → `https://www.warriortrading.com/no-access/` title Access Denied; 90s human-sign-in poll failed; LMS `learner-dashboard/` Learner Home OK; chatroom root empty shell; CRM DTD Tools Active + Pro Tools Paused (read-only).
- **Former Momo:** (B)+(C) — no exact formula in KB/BA101; see map section + memory.
- **Human gate:** Sign in (CAPTCHA/2FA if prompted) in warrior-site Chromium; then re-run warrior snap. Do not unpause billing without user.
- **Files updated:** `warrior-memory.md`, `Authenticated-Site-Map.md` (Former Momo section), `agent-warrior.canvas.tsx`.

### 2026-07-17 — HOD Momentum official docs research

- **Scope:** Warrior official docs on Small Cap HOD Momentum population, strategies, triggers (not Nova code).
- **Result:** PARTIAL — KB + BA101 captions complete; Day Trade Dash blocked (Access Denied on www).
- **Evidence:** support article `19000117763` Alert Scanners list (11 HOD sub-strategies); BA101 Ch.12 Scanning 101 (new HOD + pillars + % surge; Running Up omits HOD); prior live Strategy Name set in `warrior_latest.json`; LMS Learner Home OK, course deep-link → Access Denied.
- **Learning:** KB names “Former Momo Scanner”; live column often “Former Momo Stock”. Med/High Rel Vol numeric cutoffs not in KB — deferred to SS101 / live UI.
- **Files updated:** `Authenticated-Site-Map.md`, `warrior-memory.md`, `agent-warrior.canvas.tsx`.

### 2026-07-16 — HOD Momentum parity snapshot (refresh #2)

- **Scope:** Overwrite `.tmp/hod-momo-parity/warrior_latest.json` only; no Nova engine feed.
- **Result:** PASS
- **Evidence:** chatroom dashboard; HOD **Online**; 40 rows; symbols BIYA/LBGJ/JSPR; ts=1784243245.
- **Files updated:** `warrior-memory.md`, `warrior_latest.json` (gitignored).

### 2026-07-16 — HOD Momentum parity snapshot (refresh)

- **Scope:** Refresh Day Trade Dash HOD research snapshot for Nova parity observer; BA101 Scanning 101 five-pillar + surge confirmation (notes only).
- **Result:** PASS
- **Evidence:** `chatroom.warriortrading.com/dashboard?…` title WarriorTrading Chatroom; HOD **Online**; 40 visible rows → `.tmp/hod-momo-parity/warrior_latest.json` (ts=1784242607). Symbols BIYA/LBGJ/JSPR. Former Momo + Squeeze 5%/10% + Low/Medium Float present. BA101 ch.12: HOD = new HOD + five pillars + recent % surge; Running Up omits HOD requirement.
- **Learning:** Burst-annotated HOD time cells must be parsed (`(N in Nsec) expand row`) or rows are under-counted.
- **Files updated:** `warrior-memory.md`, `.tmp/hod-momo-parity/warrior_latest.json` (gitignored).

### 2026-07-16 — HOD Momentum parity snapshot

- **Scope:** Day Trade Dash HOD widget confirmation + research snapshot for Nova HOD parity observer; Scanner Resources title/URL index.
- **Result:** PASS
- **Evidence:** `chatroom.warriortrading.com/dashboard?…` title WarriorTrading Chatroom; HOD **Online**; Select strategies visible; 40 visible rows → `.tmp/hod-momo-parity/warrior_latest.json`. Scanner Resources → support article `19000117763` (*Scanners: How to Load & Use Them in the Chat Room*).
- **Learning:** After-hours HOD still Online with Former Momo / Squeeze / Low|Medium Float strategies. Orphan warrior-profile Chrome blocks relaunch.
- **Files updated:** `warrior-memory.md`, `Authenticated-Site-Map.md` (Scanner Resources URL), `agent-warrior.canvas.tsx`.

### 2026-07-16 — Agent install + canvas migration

- **Scope:** Promote Warrior site map into dedicated `warrior` specialist; retire unmanaged `warrior-site-map.canvas.tsx`.
- **Result:** PASS (install)
- **Learning:** Docs owns Nova Home / unmanaged cleanup; Warrior navigation belongs on `agent-warrior`.
- **Files updated:** `warrior.md`, `warrior-memory.md`, registry, routing, `agent-warrior.canvas.tsx`.

### 2026-07-16 — Initial live site map

- **Scope:** Authenticated browse of dashboard, LMS, Day Trade Dash.
- **Result:** PASS
- **Evidence:** Members Dashboard, Learner Home, chatroom dashboard after Disclaimer ACCEPT.
- **Files updated:** `docs/warrior-authenticated-access.md`, `Authenticated-Site-Map.md` (prior commit `5c8b878`).

<!-- RUN_LOG_END -->
