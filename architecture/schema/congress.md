# Data schema: The Congress page

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/congress/,
frontend/src/congress/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit
as the code (Invariants #1 and #5).

## The Congress page (ADR 066, operator asks 2026-10-14 and 2026-10-21)

"I want a new tab for Congress ... every person and their current trades", from "an accurate source ... and not
bullshit", with "the Congress members' icons" and "the seats ... where they belong" (PNG v1). Owners
`backend/congress/` (read-only; constants in `congress/constants_congress.py`) and `frontend/src/congress/`. Nothing
here places, stages or cancels an order, and nothing here feeds a scanner row, a chart, HOD Momo, a setup lane or a
bot.

**What is real.** Every trade is a row of a member's Periodic Transaction Report, read from the House Clerk's or the
Senate eFD's own site (never an aggregator). An amount is the range the report states; a share count, option or price
appears only as the filer's own words (`description`). A scanned or paper report is listed with its link, never read.
Members and committees are the public-domain `unitedstates/congress-legislators` data. Every member's photo comes
from one source, the Biographical Directory of the United States Congress (`bioguide.congress.gov`, kept by the House
and Senate historians) -- the official record the bioguide id itself belongs to (operator ask, 2026-10-23: "each
person has their official photo ... from a single source, the source of truth"). The one price on the page, a stock's move beside "Most traded", is IBKR's daily bars through the existing
`GET /api/ticker/{symbol}/bars?timeframe=1Day` (no new route). Dates are `YYYY-MM-DD` (the report's own, Eastern);
times are epoch seconds; money is US dollars.

### The agreement before any read

Both sites quote the Ethics in Government Act (5 U.S.C. § 13107(c), formerly app. § 105(c)): a report may not be
obtained or used for an unlawful or commercial purpose (other than by news media), a credit rating, or soliciting
money. Nothing is fetched -- not the roster, not a photo, not a report -- until the operator agrees on the page.

`POST /api/congress/consent` body `{accept: true | false}` (anything else: 400 `CONGRESS_BAD_PARAM`, `field: "accept"`)
answers `{schema_version: 1, consent}`. `true` keeps the agreement and starts the reader; `false` forgets it and stops
the reader (what was read stays). `consent`: `{state: "needed" | "given", accepted_at | null, text, cite}` -- `text`
the rule in the words the Senate site shows (`CONGRESS_CONSENT_TEXT`), `cite` its citation.

Kept in `<cache_dir>/congress/consent.json`: `{schema_version: 1, accepted_at, text_sha256}` (owner
`congress/consent.py`). A file of another version, an unreadable one, or one whose `text_sha256` is not today's text's
reads as "needed" -- the operator agrees again to the text shown.

### The reader

One daemon thread (`congress/refresh.py`), one request at a time, `CONGRESS_REQUEST_GAP_SEC` (1 s) apart, only while
the agreement is given and `NOVA_CONGRESS` is not `0`. It keeps the current and previous calendar year (Eastern).

- **House** (`congress/house.py`): `GET https://disclosures-clerk.house.gov/public_disc/financial-pdfs/<YEAR>FD.zip`
  with `If-Modified-Since` (the Clerk rebuilds it daily), its `<YEAR>FD.txt` index: tab-separated `Prefix, Last,
  First, Suffix, FilingType, StateDst, Year, FilingDate (M/D/YYYY), DocID`; `FilingType` `P` is a PTR. A `DocID`
  starting `8` or `9` is a scanned paper report: listed (`kind: "paper"`), never downloaded. Any other is fetched
  from `.../ptr-pdfs/<YEAR>/<DocID>.pdf` (refused over `CONGRESS_MAX_PDF_BYTES`) and read ("Reading a House report");
  a PDF with no transaction text is kept as `kind: "electronic"`, `read` false, with the reason in `error`.
- **Senate** (`congress/senate.py`): its agreement page (`https://efdsearch.senate.gov/search/home/`, the form's
  `csrfmiddlewaretoken` and `prohibition_agreement=1` -- the agreement the operator gave), then
  `POST /search/report/data/` (`report_types=[11]`, `submitted_start_date` / `submitted_end_date`, 100 a page): rows
  `[first, last, "Last, First (Senator)", <a href=/search/view/ptr|paper/<uuid>/>Title</a>, MM/DD/YYYY]`. The first
  read covers January 1 of the previous year to today, later reads from `CONGRESS_SENATE_OVERLAP_DAYS` before the last
  read. A `/ptr/` page is read ("Reading a Senate report"); a `/paper/` one is listed, never read.
- **Members and photos** (`congress/roster.py`, `congress/photos.py`): `legislators-current.json` and
  `committees-current.json` / `committee-membership-current.json` from `https://unitedstates.github.io/
  congress-legislators/` every `CONGRESS_ROSTER_MAX_AGE_SEC` (a day), `legislators-historical.json` only while a filer
  is unmatched (at most weekly). Portraits: `https://bioguide.congress.gov/photo/<BIOGUIDE>.jpg` and nowhere else
  (`CONGRESS_PHOTO_URL`; no fallback, so a face is never a second source's picture). Only a real JPEG under
  `CONGRESS_MAX_PHOTO_BYTES` (6 MB) declaring at most `CONGRESS_MAX_PHOTO_PIXELS` is decoded; it is kept shrunk to fit
  `CONGRESS_PHOTO_BOX` (240 x 300; the Bioguide's are about 1000 x 1250, up to 2.9 MB). A 404 or an answer that is not
  a JPEG is the member's miss, asked again after `CONGRESS_PHOTO_RETRY_SEC` (a day: a new member's portrait arrives
  weeks after their record); any other failure is the site's -- the source shows `failing` and every portrait waits
  `CONGRESS_RETRY_SEC`. A kept portrait is asked again after `CONGRESS_PHOTO_MAX_AGE_SEC` (30 days), after the members
  without one, so a new official portrait replaces it. Photos of members who reported come first, then every current
  member. An unread report and a portrait take turns, so faces arrive while a long first read goes on; from 09:30 to
  16:00 ET a portrait waits the same `CONGRESS_SESSION_GAP_SEC` as a report.
- **Cadence:** the House index and the Senate search every `CONGRESS_POLL_SEC` (an hour); after a failure,
  `CONGRESS_RETRY_SEC`. A report already read is not read again unless it was read by an older parser
  (`CONGRESS_PARSER_VERSION`). A failure is stated per source, never hidden; what was read stays.

### Reading a House report

pypdf's plain text (`congress/house_pdf.py`), one record per transaction: the asset (an owner code `SP` spouse / `JT`
joint / `DC` dependent child first, none for the member's own; an amended report may put a transaction ID before it),
the asset as filed, `(TICKER) [TT]` -- the ticker and the Clerk's two-letter type (`ST` stock, `OP` option, `GS`
government security, ...); then the type `P` / `S` / `S (partial)` / `E`, the transaction and notification dates
(`MM/DD/YYYY`, run together) and the amount (its upper bound may wrap); then `F S : New | Amended`, optional
`S O : <subholding>` and `D : <the filer's words>` (may wrap). The section labels' letters extract as NUL and read as
spaces. A page break repeats the column header anywhere, even inside a record: lines between a transaction line and its
first field line belong to that record. A ticker counts only directly before its type tag (`(AMI) Labs [OI]` has none).

### Reading a Senate report

The eFD page's table (`congress/senate_html.py`), one row per transaction: `#, Transaction Date (MM/DD/YYYY), Owner
(Self / Spouse / Joint / Child), Ticker ("--" for none), Asset Name, Asset Type (Stock, Stock Option, Municipal
Security, Corporate Bond, Other, ...), Type (Purchase / Sale (Full) / Sale (Partial) / Exchange), Amount, Comment
("--" for none)`. A report titled "... (Amendment N)" is dated by the report it corrects (the date in its title); in
the same store, the report it corrects -- and any older amendment of it -- is marked `amended_by` the newest
amendment, whatever order the search found them in, and their rows are not counted.

### A trade

Kept as filed; these are derived when read (`congress/trades.py`, pure, so a better rule needs no re-reading):

| Field | Rule |
|---|---|
| `kind` | `"stock"` (House `ST`, Senate `Stock`), `"option"` (`OP`, `Stock Option`), else `"other"` |
| `side` | `"buy"` (P, Purchase), `"sell"` (S, S (partial), Sale (Full), Sale (Partial)), `"exchange"` (E, Exchange), `"other"` for any other type a report states; `partial` true for a partial sale |
| `gift` | the filer's words name a contribution, donor-advised fund, gift or donation: shown as a gift, never counted as a sale |
| `amount` | `{text, low, high}`: two dollar figures are the range; one with "Over" is `low` with `high` null; one alone is both |
| `lag_days` | report date minus transaction date (a Senate amendment: the corrected report's date); `late` above `CONGRESS_LATE_DAYS` (45, the law's outer limit) |
| `owner` | `"self"`, `"spouse"`, `"joint"`, `"child"` |
| `bioguide` | the filer matched to a member: the House by chamber, state (`StateDst`), last name (one or two words) and district or first name; the Senate by chamber, last name and first name. Unmatched: null, shown with the name as filed |

A trade counts for "Most traded" only as a stock or option buy or sell, not a gift, with a ticker.

### Persisted files

All under `<cache_dir>/congress/`; none is a source of truth -- a lost file is read again from the sites.

- `filings.sqlite3` (owner `congress/store.py`), `PRAGMA user_version` = `CONGRESS_STORE_VERSION` (1): `reports(id
  PRIMARY KEY -- "H:<year>:<DocID>" | "S:<uuid>", chamber, filer_name, filer_first, filer_last, filer_state,
  filer_district, bioguide, filed, kind, url, title, amends, amended_by, parser, read_at, error, trades)`, `trades(report, n, tx, notified, owner, ticker,
  asset, asset_type, tx_type, amount, status, subholding, description, PRIMARY KEY (report, n))`, `meta(key PRIMARY
  KEY, value)` (each House year's index `Last-Modified`, the Senate's last read). Another version: the file is renamed
  aside and read again from the sites.
- `consent.json` (above), `roster.json` (owner `congress/roster.py`): `{schema_version: 1, read_at,
  historical_read_at, members: [{bioguide, name, first, last, nickname, party, caucus, state, district, chamber,
  current, left, committees: [name]}]}`; another version reads as absent (read again).
- `photos/<BIOGUIDE>.jpg` (the face, JPEG) and `photos/index.json` (owner `congress/photos.py`): `{schema_version: 2,
  source: CONGRESS_PHOTO_URL, kept: {bioguide: fetched_at}, misses: {bioguide: asked_at}}`. Only a portrait the index
  keeps is served: another version, another `source`, or a file it does not list (a `unitedstates/images` portrait
  beside the retired version 1 `misses.json`) reads as not kept, and the member is asked for again.

### Routes (read-only but the agreement; none waits on a site)

Errors are `{detail: {reason, error, field?}}`: 400 `CONGRESS_BAD_PARAM`, 404 `CONGRESS_UNKNOWN_MEMBER`,
`CONGRESS_NO_PHOTO`. A member is `{bioguide, name, party ("D" | "R" | "I"), caucus, state, district, chamber
("senate" | "house"), current, left, photo}` (`photo` true when a portrait is kept; `left` the last day of a member
who left, else null).

`GET /api/congress/board?filter=all&members=` -- `filter`: `all` | `house` | `senate` | `buys` | `sells` | `options` |
`late`; `members`: bioguide ids, comma-separated (the Following tab), counting only their trades -- given but empty
(`members=`), it keeps no member: Following with nobody starred is empty, never everyone. Answers
`{schema_version: 1, generated_at, enabled, today, year, consent, sources[], counts, periods, seats, reported,
just_reported[], most_traded, most_active[], lag}`:

- `enabled` false with `NOVA_CONGRESS=0`. `sources[]`: `{id: "house" | "senate" | "roster" | "photos", name, url,
  state: "off" | "needs_consent" | "waiting" | "reading" | "ok" | "failing", read_at, next_at, error, reports,
  electronic, paper, unread, trades, done, todo}` (`done` / `todo` while reading).
- `periods`: `{ytd, 90d, 30d}`, each `{from}` -- by report date: since January 1, the last 90 or 30 days.
- `counts`: trades reported this year, per filter: `{all, house, senate, buys, sells, options, late}`.
- `seats`: `{senate: [member], house: [member], delegates: [member], former: [member], empty: {senate, house}}` --
  every current member (the House's 435 voting seats; delegates apart), and filers who left.
- `reported`: per period, `{bioguide: "trades" | "paper"}` -- who reported in it: a read report with trades, or only
  paper / unread ones.
- `just_reported[]` (newest report first, `CONGRESS_JUST_REPORTED`): `{id, chamber, member | null, filer, filed,
  kind, read, url, amends, trades, top}` -- `filer` the name as filed; `top` the report's largest trade the filter
  keeps (`{ticker, asset, side, kind, gift, amount, lag_days}`), null for a paper or unread report.
- `most_traded`: per period, up to `CONGRESS_MOST_TRADED` of `{ticker, asset, members, buyers: [bioguide], sellers:
  [bioguide], buys, sells}`, by members then trades.
- `most_active[]`: the last `CONGRESS_ACTIVE_DAYS` (120) days' busiest members, up to `CONGRESS_MOST_ACTIVE`: member +
  `{trades, buys, sells, median_lag_days, late, weeks: {from, buy: [26], sell: [26]}, top: [ticker]}` (`weeks` by
  transaction date, oldest first).
- `lag`: this year's trades by days from trade to report: `{bucket_days: 5, buckets: [25 counts, the last 120+],
  median_days, within_week_pct, after_limit_pct, limit_days: 45, trades}`; nulls with no trades.

`GET /api/congress/members` -- `{schema_version: 1, generated_at, year, members[]}`: every current member and every
filer who left, member + `{committees: [name], ytd: {trades, buys, sells, reports, paper}, last_filed,
median_lag_days, late}`.

`GET /api/congress/member/{bioguide}` -- `{schema_version: 1, generated_at, member, weeks: {from, buy: [52], sell:
[52]}, trades[], reports[]}` (newest first). A trade: `{id, report, chamber, bioguide, filer, filed, tx, notified,
lag_days, late, owner, ticker, asset, asset_type, kind, side, partial, gift, amount, description, status, url}`; a
report: `{id, chamber, filed, kind, read, error, url, amends, amended_by, trades}`.

`GET /api/congress/trades?ticker=AAPL` -- `{schema_version: 1, generated_at, ticker, asset, buyers, sellers, trades[]}`
(each trade with its `member`); `ticker` 1-10 of `A-Z0-9.-`, else 400.

`GET /api/congress/photo/{bioguide}` -- the kept portrait (`image/jpeg`, the Bioguide's), or 404 `CONGRESS_NO_PHOTO`;
never fetched on the request.

### The page

Rail item `Congress` after Cryptos; the focus report's `page` `"congress"` (`constants_sensors.FOCUS_PAGES`). Tabs:
Trades (the overview), Members, Following. The topic tabs (All, House, Senate, Bought, Sold, Options, Reported late,
Following) set `filter` / `members`. The seat maps' and Most traded's period switches, and the members starred,
persist in localStorage `nova.congress.prefs.v1`: `{schema_version: 1, seats_period, traded_period, following:
[bioguide]}` (owner `frontend/src/congress/prefs.ts`; an unknown version or value falls back to `ytd` / none). The
sample desk shows Nova Marketing Sample Data (invented members, initials only) and writes nothing.
