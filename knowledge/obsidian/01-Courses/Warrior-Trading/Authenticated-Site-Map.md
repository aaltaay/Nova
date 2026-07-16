---
title: Warrior Trading authenticated site map
date: 2026-07-16
status: current
tags: [warrior-trading, site-map, day-trade-dash, lms, access]
---

# Warrior Trading — Authenticated Site Map

Durable navigation map for future agent questions. Access runbook:
`docs/warrior-authenticated-access.md`.  
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
| Scanner Resources | Support article scanners how-to |
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

HOD also exposes **Select strategies**.  
Running Up may show burst annotations such as `(3 in 5sec)` and flame/news icons on symbols.

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

### My Courses (visible catalog, 2026-07-16)

| Course |
|--------|
| 1. Day Trading: The Basics |
| 2. Day Trading: Strategies & Scaling |
| 3. Live Trading Archives |
| 4. Trader Rehab |
| _Platform Demos & Layouts_ |
| _Trading Psychology: Developing the Trader's Mindset_ |
| Algo Scalping Strategy |
| Day Trading in an IRA |
| Member Interviews |
| { Grad Course: High Volatility Momentum Trading (Jess) } |
| { Grad Course: Momentum Trading with Thinkorswim (Danny) } |
| ~ Grad Course: Scalping Small Cap Momentum (Max) ~ |

Course home URL pattern:  
`https://lms.warriortrading.ai/learning/course/course-v1:WarriorTrading+{CODE}+2026/home`  
Example: `…+BA101+2026/home`.

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
