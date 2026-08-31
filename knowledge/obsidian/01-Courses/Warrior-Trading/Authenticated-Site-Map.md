---
title: Warrior Trading authenticated site map
date: 2026-07-16
status: current
tags: [warrior-trading, site-map, day-trade-dash, lms, access]
---

# Warrior Trading — Authenticated Site Map

Durable navigation map for future agent questions.  
**Owning agent:** `warrior` — invoke “Use the warrior subagent to navigate Warrior Trading” · dashboard `agent-warrior.canvas.tsx`.  
Access runbook: `docs/warrior-authenticated-access.md`.  
Local downloads inventory: [[Local-Library-Inventory]].

**Mapped live:** 2026-07-16 with a headed persistent browser profile.  
**Scope:** page hierarchy, controls, widget layout, material *locations*.  
**Not in scope:** bulk copies of paid videos/transcripts/articles; Warrior market-data scraping into Nova.

## Hosts

| Host | Role |
|------|------|
| `www.warriortrading.com` | Marketing site + member dashboard hub |
| `lms.warriortrading.ai` | Education portal (Open edX-style LMS) |
| `chatroom.warriortrading.com` | Day Trade Dash / chat platform |
| `support.warriortrading.com` | Member support portal / knowledge base |
| `secure.warriortrading.com` | CRM: orders, billing, password, shipping |

## Entry & auth

| Step | URL / behavior |
|------|----------------|
| Unauthenticated dashboard | Redirects to `/no-access/` with Sign-in form + Access Denied options |
| Cookie banner | OneTrust: Accept / Reject / Do Not Sell |
| Successful login | `https://www.warriortrading.com/dashboard/` — **Member's Dashboard** |
| Sign out | `/logout.php` |
| Session persistence | Local Chrome profile under `%LOCALAPPDATA%\Nova\browser-profiles\warrior-site` |

Popups seen: cookie consent; chatroom **Disclaimer** (ACCEPT / DECLINE) on Day Trade Dash entry.

---

## A. Member's Dashboard

**URL:** `https://www.warriortrading.com/dashboard/`  
**Title:** Members Dashboard / heading *Member's Dashboard*

### Account / CRM (left / top links)

| Label | Destination |
|-------|-------------|
| My Orders & Memberships | `secure.warriortrading.com/crm/members/sales` |
| Contact Info | `…/shippinginfo` |
| Billing & Credit Card | `…/billinginfo` |
| Update Website Password | `…/mypassword.aspx` |
| Search the Member Support Portal | `support.warriortrading.com/` |
| Member Renewal & Information Page | `/member-renewal-information/` |

### Community / Day Trade Dash / Simulator

| Label | Destination | Notes |
|-------|-------------|-------|
| How to Use the Platform | Support folder `19000101389` | Chat, stream, news, scanners, charts, web sim |
| **Click Here to Enter** | `/chat-room-access/?invalidation=…` | Gateway into Day Trade Dash |
| Streaming & Audio Hours | Support article live schedule | |
| Chat Room Rules | `/chat-room-rules/` | |
| How-To Guide | Same support folder as above | |
| Contact Support Team | Support contact article | |
| Web-Based Simulator info | Support folder `19000178514` | |
| Simulator activation / renewal | Support + renewal anchors | |

### Education

| Label | Destination |
|-------|-------------|
| Onboarding for New Members | `/welcome-to-warrior-trading/` |
| What's New: Content Updates | Support article `19000114894` |
| **View Courses in Education Portal** | `/learning-portal` → redirects to `lms.warriortrading.ai/learner-dashboard/` |
| Education portal FAQ | `/member-faq/` |

### Mentors & resources

| Label | Destination |
|-------|-------------|
| Join or View Schedule (Mentor Sessions) | `/trading-course-chat/` (Pro) |
| Mentor Topic Suggestions | `/mentor-suggestion-box/` |
| Day Trading Terminology | `/day-trading-terminology/` |
| News Room and Squawk | Support article `19000131769` |
| Scanner Resources | Support article `19000117763` — *Scanners: How to Load & Use Them in the Chat Room* (`support.warriortrading.com/support/solutions/articles/19000117763-scanners-how-to-load-use-them-in-the-wt-chat-room`) |
| Day Trade Dash Charting Resources | Support folder `19000171870` |
| Accessing the Live Stream | Support Day Trade Dash sign-in article |
| eSignal Resources (Pro) | `/vwap-installation-instructions-for-esignal/` → may land on layout install page |
| Excel Trade Sheets | `/excel-trade-sheet/` |
| Member Support Portal home | `support.warriortrading.com/support/home` |

---

## B. Chat room gateway

**URL:** `https://www.warriortrading.com/chat-room-access/`  
**Title:** Live Trading Room Access

Key actions:

- **Click here to Enter the Platform** → SSO handoff to `chatroom.warriortrading.com/sso/?data=…` then dashboard
- FAQ links: Rooms and Hours, personalizing profile, sort chat feed, adjust layout, market-data agreements, scanners, charts, news room
- System requirements / custom features / chat rules links

**Do not bookmark SSO `?data=` JWTs** — re-enter from this gateway when expired.

---

## C. Day Trade Dash (chatroom)

**URL pattern:** `https://chatroom.warriortrading.com/dashboard?hash=…&userId=…&sourceCode=WT`  
**Title:** WarriorTrading Chatroom  
**First gate:** Disclaimer modal → ACCEPT

### Sidebar (left)

| Section | Items (observed) |
|---------|------------------|
| Rooms | Small Cap; Large Cap / Options / Swing; Support; Lounge / General / Broker; Pro Mentor; Live Classes |
| Tools | Scanners (status light); Scanner History; My Watchlist; Charting; News Room (+ JOIN STREAM when applicable); Stock Quote |
| Settings | Layouts; Save all Windows; Alert Volume; Profile; Help |
| Footer | Profile / stream thumbnail area |

Room open/closed buttons appear for each room (Chat Room is Open / Closed).

### Default widget grid (mapped layout)

```
┌─────────────────────────────┬──────────────────────┐
│ Small Cap - High of Day     │ Charting (TradingView)│
│ Momentum (Online)           │                      │
├─────────────────────────────┤                      │
│ Running Up (Online)         ├──────────────────────┤
├──────────────┬──────────────┤ Stock Quote + News   │
│ Top Gappers  │ Top Gainers  │ + stats              │
│ (often Offline│ (Online)    │                      │
│  after open) │              │                      │
└──────────────┴──────────────┴──────────────────────┘
```

Each widget: title bar with Online/Offline (and last-updated for gappers), gear/settings, close/pop-out controls.

### Scanner columns

**HOD Momentum & Running Up** (same column set):

| Column |
|--------|
| Time |
| Symbol / News |
| Price |
| Volume |
| Float |
| Relative Volume (Daily Rate) |
| Relative Volume (5 min %) |
| Gap (%) |
| Change From Close (%) |
| Short Interest |
| Strategy Name |

HOD also exposes **Select strategies** (bell / strategy checklist for audio + visibility).  
Running Up may show burst annotations such as `(3 in 5sec)` and flame/news icons on symbols.

### Small Cap HOD Momentum — population model (official)

Primary KB: support article `19000117763` — *Scanners: How to Load & Use Them in the Chat Room*  
(`https://support.warriortrading.com/support/solutions/articles/19000117763-scanners-how-to-load-use-them-in-the-wt-chat-room`)

Teaching companion: LMS **BA101 — Day Trading: The Basics → Chapter 12: Scanning 101**  
(Deeper per-strategy color/usage also pointed by KB to **Day Trading: Strategies & Scaling** / SS101.)

| Fact | Official statement (paraphrase) |
|------|----------------------------------|
| Scanner class | **Alert scanner** (≈1s updates; optional chime) — not a 30s Top List |
| Appearance rule | **New high-of-day** *plus* **above-average momentum** matching a sub-strategy |
| Not traditional HOD | Does **not** alert on every HOD print (would flood); needs momentum threshold over a time window |
| Timing nuance | Alert may fire slightly after the HOD print (e.g. within next minute) once momentum confirms |
| Premarket / AH | Fewer alerts expected when volume is thin |
| vs Running Up | Running Up = quick % moves **without** requiring a new HOD (can alert earlier) |

**BA101 Scanning 101 teaching model (Ross):** new HOD + five pillars of stock selection + recent % surge (“moved at least x% in the last few minutes”). Scanners cast a slightly wider net than strict five-pillar; trader still checks pillars after the alert.

**Five pillars (BA101 Ch.3 — What Makes a Strong Stock):** volatility (≥~10% up preferred), price (best ~$2–$20), relative volume (~5×), breaking news, supply/float (under ~20M shares). Exact HOD sub-strategy numeric cutoffs are not fully published in the KB list below.

### Small Cap HOD Momentum — desired outcomes (Warrior teaching)

**Primary outcome (one sentence):** Surface small-cap names that are printing a **new high of day with confirming momentum** (not every HOD tick), so the trader can **hunt real-time volatility** with scanners doing discovery and the human still doing pillar/chart/L2 risk checks before any entry.

Published care-abouts (paraphrase; research index only — do not invent filter formulas):

1. **Discovery of stocks that are already moving** — prefer “first to see a squeeze” over “first to every headline” (BA101 Ch.12).
2. **Lighten workload** — scanners search the market; trader manages risk (BA101 Ch.12).
3. **New HOD + momentum window** — alert class, not flood-every-HOD; may fire slightly after the print once momentum confirms (KB `19000117763`).
4. **Recent % surge** — teaching model includes “moved at least x% in the last few minutes” alongside new HOD (BA101 Ch.12; exact universal `x` not a published single formula for all sub-strategies).
5. **Slightly wider net than strict five pillars** — then **human pillar check after the alert** (BA101 Ch.12; reinforced SS101 Ch.12 “cast a wider net”).
6. **Sub-strategy lanes + significance** — color/audio distinguish Squeeze / Low-Float-High-RVOL (brighter) vs less-significant lanes; Ross audio = all except Medium Float (KB `19000117763`, BA101 Ch.12).
7. **Pair with Running Up** — HOD requires new HOD; Running Up can warn earlier on curls before HOD (BA101 Ch.12; SS101 Ch.12 names both as primary alert scans).
8. **Post-alert workflow** — click → news → intraday near highs → daily resistance → L2/T&S → borrow/SSR/spreads → familiar pattern (often first pullback) (BA101 Ch.12).
9. **Timing context** — top/bottom of hour for news-driven surges; thinner PM/AH → fewer alerts expected (BA101 Ch.12; KB).
10. **Enable momo setups, not replace them** — HOD breakout / micro-pullback / first-pullback still require human justification; HOD entry is high-risk (SS101 HOD Breakout / Intro to Momo).
11. **Former-runner familiarity** — qualitative “do I know this name / how has it traded?” when Former Momo appears — not a coded %/float formula (SS101 Ch.4 / trading-plan checklist; KB list membership only).

**Explicit non-outcomes (Warrior teaches against or does not claim):** auto-order on alert; overfitting / reverse-engineering “holy grail” filters from backtests; alerting every HOD print; social media as primary discovery system; published numeric Former Momo formula; Medium Float as Ross’s preferred chime set.

### Small Cap HOD Momentum — Select strategies inventory (KB)

Documented under **Alert Scanners → Small-Cap - High of Day Momentum (HOD Momo)** as sub-scanners:

1. Low Float - Med Rel Vol  
2. Low Float - High Rel Vol  
3. Low Float - High Rel Vol - Price $20+  
4. Low Float Volatility Hunter - HOD breakout  
5. Former Momo Scanner *(live Strategy Name column often shows **Former Momo Stock**)*  
6. Medium Float - Med Rel Vol - Price $20+  
7. Medium Float - High Rel Vol - Price $20+  
8. Medium Float - High Rel Vol - Price under $20  
9. Squeeze Alert - Up 10% in 10min  
10. Squeeze Alert - Up 5% in 5min  
11. Squeeze Alert - 52wk Breakout  

Related sibling alert scanners (separate widgets, not HOD sub-strategies): Penny HOD Momentum (&lt;$2), Running Up, Running Down, Large Cap HOD, Halt, Ross's 5 Pillar Alert.

**Ross audio preset (KB):** select all HOD strategies **except Medium Float** scanners.

**Live Strategy Name column (research snap 2026-07-16, after-hours):** Former Momo Stock; Squeeze Alert - Up 10% in 10min; Squeeze Alert - Up 5% in 5min; Low Float - High Rel Vol; Medium Float - High Rel Vol - Price under $20.

### Former Momo Stock — published evidence (2026-07-17 deep pass)

**Verdict:** Warrior does **not** publish a numeric filter formula for the HOD sub-strategy. “Former Momo” is a **named HOD alert lane** + a **qualitative stock-type** in SS101. Do not invent float/RVOL/% thresholds for Nova parity from the name alone.

| Source | What it says about Former Momo |
|--------|--------------------------------|
| Support `19000117763` Alert Scanners | Lists **Former Momo Scanner** under Small-Cap HOD Momo — **no % / float / RVOL / lookback formula** |
| Same article — Strategy column | Colors differ by strategy; “for more on these strategies” → **SS101 Strategies & Scaling** |
| Same article — Ross audio preset | Select **all** HOD strategies **except Medium Float** (implies Former Momo **included** in Ross’s chime set) |
| Support search `"Former Momo"` | Only substantive hit is article `19000117763` (list membership); no dedicated Former Momo KB article |
| BA101 Ch.12 Scanning 101 | Color guide: “former Momo scanners” = one **green** horizontal shade; significance ranked below bright Squeeze-10% / Low-Float-High-RVOL colors |
| BA101 Ch.12 audio prefs (Ross) | Enables **low float** + **squeeze** audio; skips **medium float** and “these others” (Former Momo not named explicitly) |
| SS101 Ch.4 Daily Chart Patterns (slides) | **Former momo stock / former runner** = recent big-% mover that drew volume & attention; watch if it hits scanners with **fresh news**; daily flags on former runners; **not** a coded HOD filter table |
| SS101 LMS search `"Former Momo"` | Hits **Chapter 4 Quiz** only (not Ch.12 Stock Scanning text index) |
| SS101 Ch.12 Stock Scanning (LMS) | Video unit *SS25 - Chapter 12 Stock Scanning…*; no published slide text in search index defining Former Momo filters; local `ss-14` PDF in “Chapter 12” folder is trading-plan content (LMS Ch.14 numbering) |
| SS101 trading-plan slides (`ss-14`) | Checklist line: **“Former Momo Stock: Am I familiar with the name? How has it traded in the past?”** (gap-scanner analysis questions — not scanner code) |
| Live Select strategies (2026-07-17) | Checkbox label **Former Momo Stock** (not KB “Scanner”); **no tooltip/help text** with filters |
| Live row observation (not a rule) | e.g. VELO tagged Former Momo Stock with ~13.86M float & daily RVOL ~0.7 while alerting — inconsistent with Low-Float/High-RVOL lanes; **do not treat as official formula** |

**Label map:** KB `Former Momo Scanner` ↔ UI/column `Former Momo Stock`.

**Top Gappers:**

| Column |
|--------|
| Gap (%) |
| Symbol / News |
| Price |
| Volume |
| Float |
| Relative Volume (Daily Rate) |
| Relative Volume (5 min %) |
| Change From Close (%) |
| ATR (Rate) |
| Short Interest |

Gappers show a time window in the title (e.g. `09:25:00 - 09:30:00`) and often go **Offline** after the open window with “Last updated …”.

**Top Gainers:** similar to gappers but primary metric is change-from-close; title shows a rolling window while Online.

### Charting widget

- TradingView-powered (`Charts Powered by TradingView`)
- Symbol search, timeframes (1m / 5m / 15m / 1h / D observed), indicators, refresh
- Drawing toolbar; save chart / manage layouts / chart settings
- Clicking a scanner symbol syncs chart + quote (observed VIR selected while scanners showed other names until click)

### Stock Quote widget

- Company name, exchange, sector
- Last / change / change%
- News Headline block (More)
- Stats grid: Float, Volume, Rel Vol Daily, Rel Vol 5m, Gap%, Change from Close, 52w high/low, Market Cap, Short Interest, etc.

### Interaction notes for future UI parity (Nova)

- Multi-widget simultaneous scanners (not tab-exclusive)
- Symbol click → chart + quote linkage
- Online/Offline honesty on scanner windows
- Strategy-colored / banded rows; green/red for change direction
- Layouts + Save all Windows (named workspace persistence)
- News Room is a separate tool with live stream join

Nova today: one scanner/HOD tab + side quote column. Architectural path: workspace Phase 8 multi-panel dashboard (plan file `modular_panel_workspace_phases_*.plan.md`). Data for Nova remains IBKR/Alpaca — do not scrape Warrior feeds.

---

## D. Education portal (LMS)

**Entry:** `/learning-portal` → `https://lms.warriortrading.ai/learner-dashboard/`  
**Title:** Learner Home  
**Nav:** Courses · Help · Account menu

### My Courses (enrolled Learner Home, reconfirmed 2026-08-28)

| Course | Code |
|--------|------|
| 1. Day Trading: The Basics | BA101 |
| 2. Day Trading: Strategies & Scaling | SS101 |
| 3. Live Trading Archives | LTA |
| 4. Trader Rehab | RH101 |
| _Platform Demos & Layouts_ | DE101 |
| _Trading Psychology: Developing the Trader's Mindset_ | PSY101 |
| Algo Scalping Strategy | AS101 |
| Day Trading in an IRA | IRA101 |
| Member Interviews | INT101 |
| { Grad Course: High Volatility Momentum Trading (Jess) } | HVM101 |
| { Grad Course: Momentum Trading with Thinkorswim (Danny) } | TOS101 |
| ~ Grad Course: Scalping Small Cap Momentum (Max) ~ | SCAL101 |

**Not enrolled on this account** (visible via `/api/courses/v1/courses/` but `enrollment_required`):

| Course | Code | Notes |
|--------|------|-------|
| Swing & Options Trading | SWOP101 | Blocker for Swing offline harvest until LMS enrollment |
| *Getting Started | Go | |
| 0. Your Warrior Pro Special Access | MBG | |
| _Mentoring Sessions_ | MS26 | |
| Warrior Pro Preview / Test / DELETE stubs | WPPrev / Test / WPP | Ignore |

Course home URL pattern:  
`https://lms.warriortrading.ai/learning/course/course-v1:WarriorTrading+{CODE}+{YEAR}/home`  
Example: `…+BA101+2026/home`. SWOP year is `2020`.

LMS entry: Members Dashboard → **View Courses in Education Portal** → `https://www.warriortrading.com/learning-portal` (no trailing slash; trailing slash 404'd 2026-08-28).

### BA101 — Day Trading: The Basics (chapter index)

Course tools: Course · Progress · Dates · Search · Bookmarks · Handouts iframe · Launch tour.

Chapters (each with Quiz + Quiz Answers where listed):

1. Becoming a Day Trader  
2. Opening a Trading Account  
3. Picking Stocks for Day Trading  
4. Introduction to Fundamental Analysis  
5. Introduction to Technical Analysis  
6. Trading Platform Walk-Through  
7. Level 1 Market Depth and Order Entry  
8. Level 2 Market Depth and Order Entry  
9. Order Entry Window  
10. Hot Keys and Hot Buttons  
11. Stock Halts  
12. Scanning 101  
13. The Psychology of Trading  
14. Preparing to Start Trading  
15. Day Trading Strategy & Trading Plan, The learning Path, and What's Next  
16. End of Course  

Local slide/video mirrors: see [[Local-Library-Inventory]] under `downloads/warrior-trading-*`.

### LMS video / caption inventory (2026-08-28)

Full catalog harvest for **enrolled** courses only (titles + Wistia media-ids; transcript bodies stay under gitignored `downloads/warrior-trading-caption-notes/`):

| Metric | Count |
|--------|------:|
| Unique video units (12 enrolled courses) | 572 |
| Official English caption tracks | 24 |
| Caption gaps (need Whisper / local video) | 548 |
| Local MP4s under `downloads/warrior-trading-videos/` | 581 (100% of catalog media; extras are orphans/superseded) |

Course codes enrolled: BA101, SS101, LTA, RH101, DE101, PSY101, AS101, IRA101, INT101, HVM101, TOS101, SCAL101.

Delta vs 2026-07-17: +28 unique units (all LTA; 289 → 317). Prior 19 catalog gaps re-downloaded 2026-08-28.

**Swing blocker:** `SWOP101` exists in the LMS course catalog but this membership is **not enrolled** (`course_access.error_code=enrollment_required`). Do not auto-enroll / purchase -- human must enroll Swing & Options (or confirm Pro course entitlement unlocks it), then re-run harvest.

**Priority Whisper gaps (no official captions; mp4s now on disk):**

- SS101 · Part 1: Daily Chart Patterns -- media `gbw1yl3luq` (~3341s)
- SS101 · Stock Scanning (Day Trade Dash Scanner) -- media `m0ilv07764` (~1369s)

Re-run: `downloads/warrior-trading-caption-notes/_harvest_lms_captions.py` · gap report: `TRANSCRIPT_COVERAGE.md` · offline mp4 download via `_download_and_whisper_gaps.py` helpers.

---

## E. Other member material pages

| Page | URL | Notes |
|------|-----|-------|
| Welcome / onboarding | `/welcome-to-warrior-trading/` | New-member orientation |
| Member FAQ / updates | `/member-faq/` | Portal update notes |
| Excel Trade Sheets | `/excel-trade-sheet/` | Starter + Pro templates |
| Mentor sessions | `/trading-course-chat/` | Pro-gated schedule |
| eSignal resources | eSignal VWAP / layout install pages | Pro |
| Terminology | `/day-trading-terminology/` | Glossary |
| Support home | `support.warriortrading.com/support/home` | Tickets + KB |

Marketing footer still present on many member pages (webinar, Pro, chat room product pages, etc.) — not the primary authenticated workflow.

---

## F. Popup / blocker catalog

| Popup | When | Action |
|-------|------|--------|
| OneTrust cookie bar | First site visit | Accept Cookies (or Reject) |
| Access Denied + Sign in | Unauthenticated `/dashboard/` | Sign in |
| Chatroom Disclaimer | Enter Day Trade Dash | ACCEPT to proceed |
| LMS Launch tour | Course home | Dismiss / skip if not needed |
| CAPTCHA / 2FA | Login edge cases | Human completes in headed window |

---

## G. Repeatable paths (cheat sheet)

```text
Login → /dashboard/
  ├─ Education → /learning-portal → lms…/learner-dashboard/ → course home → chapters
  ├─ Day Trade Dash → /chat-room-access/ → Enter Platform → ACCEPT disclaimer → widgets
  ├─ Mentors → /trading-course-chat/
  ├─ Excel → /excel-trade-sheet/
  ├─ eSignal → eSignal resource pages
  └─ Support → support.warriortrading.com
```

Re-open later:

```powershell
.\scripts\open_warrior_site.ps1
```

---

## H. Agent recall

When asked about Warrior UI, scanners, LMS courses, or “where is X on Warrior”:

1. Read this note + `docs/warrior-authenticated-access.md`
2. Prefer Graphify / Obsidian over re-scraping
3. Re-open headed profile only when the map is stale or a new page is needed
4. Never commit secrets; never bulk-copy paid lesson bodies into git
