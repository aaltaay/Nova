# Deferred log (agent-maintained -- MANDATORY)

This file is the **shared parking lot for work we already know about and did not do**. Known bugs found mid-task. Features the human asked for that got parked because they are too big, need an ADR, or were the wrong job for that session.

**Mandatory for every agent** in this project (parent sessions and all Nova specialists). Rule: `.cursor/rules/deferred-log.mdc`. Finding a real bug (or parking a real feature) and walking away with no entry here is a constitution violation -- same severity as skipping `PROBLEM_LOG.md` after a real fix. Lifecycle footers must declare `deferred_log=<D-NNN>|none|skipped|n/a`.

This is **not** `PROBLEM_LOG.md` (that is closed: symptom / cause / fix). This is **not** `Nova-Roadmap-Status.md` (that is product NEXT / phases L-Z). This is **not** an agent-memory Backlog (those are specialist scratchpads; they are not the SSOT).

Ranked list without reading the whole file:

```text
py -3 tools/deferred_log.py status
py -3 tools/deferred_log.py next-id
```

Every new chat also sees open P0/P1 items in the session-start fleet brief.

## How to triage (so a human can decide)

| Field | What it answers |
|-------|-----------------|
| **Kind** | `bug` (wrong today) / `feature` (wanted, not built) / `decision` (blocked on a human call) |
| **Severity** | `P0` desk-broken, wrong money, trading safety, cannot operate. `P1` daily-use wrong (a column, a number, a control the operator uses every session). `P2` edge session / annoying / honesty gap that is not silent-wrong-money. `P3` polish. |
| **Effort** | `S` hours in one session. `M` a full session, shape is known. `L` architectural / multi-session / needs an ADR. |
| **Why parked** | Doing other work / too big for this task / needs an ADR / blocked on a human decision. Never "didn't feel like it." |
| **Blast radius** | What else is lying or missing while this stays open. |
| **Unblock** | The one decision or missing piece that lets an agent start. |
| **Next** | One concrete first step, not a design essay. |
| **Evidence** | How we know it is real (endpoint, screenshot, log line). No entry without this. |

Pull into a session when: severity is P0, or the human names the ID, or you are already in that module and Effort is S. Do **not** silently expand the current task into an L item -- write it here and finish what you were asked.

## How agents update this file

1. **When:** You found a real bug and did not fix it this session; or the human asked for a feature you parked; or you fully diagnosed a root cause and deferred the patch. Search this file first -- extend an existing ID rather than duplicating.
2. **Where (open):** Prepend a new `## D-NNN` section **immediately below** the `<!-- OPEN_START -->` marker. IDs are durable. Get the next one with `py -3 tools/deferred_log.py next-id`. Never reuse an ID.
3. **Where (done):** Cut the whole `##` section from Open into Closed (below `<!-- CLOSED_START -->`), set **Status:** `done`, add **Closed:** date plus **Related:** PROBLEM_LOG / CHANGELOG / task-log. Do not delete history.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## D-NNN -- Short descriptive title

- **Status:** open
- **Kind:** bug | feature | decision
- **Severity:** P0 | P1 | P2 | P3
- **Effort:** S | M | L
- **Domain:** market-feed | news | execution | hod-momo | ...
- **User-visible:** yes | no
- **Logged:** YYYY-MM-DD
- **Why parked:** One or two sentences. Name the task you were in.
- **Blast radius:** What else is wrong or missing while this stays open.
- **Unblock:** The decision or missing piece that lets an agent start.
- **Next:** One concrete first step.
- **Evidence:** Endpoint, log line, or screenshot that proves it.
- **Keywords:** comma, separated, terms, for, search
```

**Status values:** `open` (actionable) | `blocked` (waiting on Unblock) | `parked` (explicitly not this month) | `wontfix` (human said no) | `done` (belongs in Closed).

<!-- OPEN_START -->

## D-002 -- Afterhours Gap % equals Change %, not the open-vs-prior-close gap

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** The Gainers/Losers `reprice_mover_row` path now derives `gap_percent` from the IBKR session-open tick (tick 14). The afterhours reprice path (`ibkr_bridge.apply_l1_quote` afterhours branch / `_ah_discovery`) was not migrated in that same change, and the evening session was already on the afterhours table so we could not E2E the gainer gap at the same time.
- **Blast radius:** Afterhours Gap % on every row is a lie whenever the session move is not equal to the overnight gap. An operator can treat a +50% runner as a +50% gapper.
- **Unblock:** None -- shape is known. Do it in a session that can see a live afterhours roster.
- **Next:** Thread `open_price` through the afterhours L1 reprice the same way `discovery.reprice_mover_row` does; do not reuse `change_pct` as gap. Add a regression that an AH row with open != last keeps a real gap.
- **Evidence:** 2026-08-26 live OKTG: Gap % showed `+53.29%` (same as Change %) while open vs prior close was `-2.50%`.
- **Keywords:** afterhours, gap_percent, change_pct, OKTG, _ah_discovery, apply_l1_quote, tick 14, reprice_mover_row

## D-001 -- Scanner NEWS column is dead under discovery=ibkr

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** news
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Found while filling Gap % / RVOL / Float / Short Int. / Mkt Cap on IBKR movers. Every writer of `has_news` / `newest_headline_at` is still on the Alpaca-era movers/discovery runners, which early-return when `discovery=ibkr`. Fixing it is a new periodic job, not a one-line decorate, and that session was already shipping L1 + fundamentals.
- **Blast radius:** Gappers / Gainers / Losers / Afterhours NEWS column is empty every session. Catalysts elsewhere are unrelated -- this is the scanner table badge.
- **Unblock:** None on the human side. Do not write news flags into a frozen roster cache (ADR 008). Decorate at read time, same as `mover_enrich_view.decorate_rows`.
- **Next:** Periodic job over current roster symbols (the same set `mover_enrich_hooks.on_mover_roster_commit` already gathers), reuse Alpaca `_check_news`, stamp `has_news` / `newest_headline_at` at `routes/scan._strip_blocked`, `scanner_push.broadcast_roster_replace`, and `_snapshot_payload`.
- **Evidence:** 2026-08-26 live `/api/movers` Gainers rows carried neither `has_news` nor `newest_headline_at` (keys absent, not null). `scanner_runners/movers.py` returns immediately when discovery is ibkr.
- **Keywords:** has_news, newest_headline_at, NEWS column, discovery=ibkr, scanner_runners, mover_enrich_view, Alpaca news, ADR 008

<!-- OPEN_END -->

<!-- CLOSED_START -->

<!-- CLOSED_END -->
