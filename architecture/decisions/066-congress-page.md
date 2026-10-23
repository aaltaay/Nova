# ADR 066 -- The Congress page: what members of Congress reported trading, from their own filings

**Status:** Accepted · **Date:** 2026-10-21
**Builds on:** [[040-cryptos-page]] (a read-only page on labelled public sources, never a price source) ·
[[053-market-page]] · [[005-frontend-feature-slices]]
**Decided by:** the operator, 2026-10-14: "I want a new tab for Congress ... every person and their current trades",
"Before you create the UX, I just want to make sure we have an accurate source for this information and not
bullshit"; then "I actually want to see the Congress members' icons too", "I want them to see the seats ... their own
seats too, where they belong", and PNG v1 (`F:\Nova\design\congress\v1\`); 2026-10-21: "start building this
end-to-end!" (#1136).

## Context

Members of Congress, their spouses and dependent children report every trade over $1,000 in a stock, bond, option or
other security on a Periodic Transaction Report (STOCK Act, 2012): within 30 days of learning of it, and never later
than 45 days after it (a late report costs $200). The House passed a ban on members buying new stocks on 2026-07-22;
the Senate blocked it 53-47 on 2026-09-30, so the rules stand. Measured on 2026-10-14 over every report filed in
2026: a trade becomes public about 25-28 days after it happened, 6% within a week; an amount is a range
("$1,001 - $15,000"), never shares or a price, unless the filer writes them in a note ("Sold 20,000 shares").

The reports are public on two official sites: the House Clerk (a yearly index plus one PDF per report; e-filed PDFs
hold text, scanned paper ones do not) and the Senate's eFD (e-filed reports as HTML tables, paper ones as images).
Aggregators (Capitol Trades, Quiver and others) re-type the same reports; on 2026-10-14 Capitol Trades showed "N/A"
for four tickers the filing named and a price column no filing holds. Both sites quote the Ethics in Government Act:
a report may not be obtained or used for a commercial purpose (other than news), a credit rating or soliciting money
(5 U.S.C. § 13107(c), formerly app. § 105(c); civil penalty up to $10,000). The Senate site asks the reader to agree
before it shows any report.

## Decision

1. **A `Congress` page on the nav rail, after Cryptos** (`frontend/src/congress/`, backend `backend/congress/`).
   Read-only: it places, stages and cancels nothing, and feeds no scanner row, chart, HOD Momo, setup lane or bot.
   It is for watching: a trade is weeks old when it is public (the private lab found no edge in copying them).
2. **The official filings are the only source of trades.** The House Clerk's index and e-filed PDFs (read with
   `pypdf`, a pinned dependency) and the Senate eFD's e-filed tables. A scanned or paper report is listed with its
   link and marked as not read -- never guessed, never read by a person's eye or OCR here. Amounts stay ranges; a
   share count or option term shows only as the filer's own words. A gift ("Contribution ... to Donor-Advised Fund")
   is not a sale. A Senate amendment is dated by the report it corrects. No aggregator is read.
3. **Nothing is fetched until the operator agrees, once, to the statute's use rule,** shown on the page in the words
   the Senate site uses. The agreement is kept on the desk (`congress/consent.json`); the reader then sends the
   Senate site the same agreement its own page sends. Withdrawing it stops the reader and keeps what was read.
4. **Members are matched by official ID** (the bioguide id) from the public-domain `unitedstates/congress-legislators`
   data, with their party, state, district, chamber and committees; their photos are the official portraits from
   one source, the Biographical Directory of the United States Congress (`bioguide.congress.gov`), kept on the desk
   shrunk to a face. A member without one shows initials, said as such. A filer who left Congress stays, marked with
   the day they left. *Amended 2026-10-23:* the photos were `unitedstates/images` (public domain) with the Bioguide
   behind it; that mirror had no portrait for 15 of 545 current members seated since 2025, and two sources meant a
   face could come from either. The operator asked for "a single source, the source of truth": the Bioguide is the
   historians' official record the bioguide id belongs to. Its member-supplied portraits are marked for restricted
   reuse, so Nova keeps them only in the desk's cache -- never in the repository or the demo build.
5. **What the page shows** (PNG v1): both chambers' seat maps -- every seat, seated by party (the House has no
   assigned seats; it is not the floor chart), a senator who reported trades in the period shown with their photo,
   a representative as a lit seat; the newest reports; the most traded stocks with the members who bought and sold
   them; the most active members; how late trades are reported against the 45-day limit. Members, Following
   (members the operator stars), each member's page (every trade, the filer's words, a link to the filing) and a
   stock's page (who traded it).
6. **Prices only from IBKR.** The one price on the page -- a stock's move over the period beside "Most traded" -- is
   read from the desk's own daily bars (`/api/ticker/{symbol}/bars`), as every chart is. No price is estimated for
   a trade; none is shown for a filing.
7. **The reader is slow and polite.** One daemon thread, one request at a time, at least a second apart; the House
   index is asked hourly with `If-Modified-Since`, the Senate search hourly; reports already read are not read again
   unless the parser changed. The current and previous calendar year are kept. `NOVA_CONGRESS=0` turns it off.

## Consequences

- The operator sees every member's reported trades within hours of the report, with the report one click away.
- Scanned paper reports (about 12% of the House's, 7% of the Senate's in 2026) are listed, not read.
- A stock IBKR has no daily bars for (a foreign share, a renamed ticker) shows no move.
- `backend/requirements.txt` gains `pypdf`; a desk that follows releases by itself asks for the one-time install.

## Rejected

- **An aggregator's feed** (Quiver, Capitol Trades, Unusual Whales, FMP): the same filings re-typed, with errors and
  estimated prices the filings do not hold.
- **OCR of scanned reports:** a read nobody can check is a guess styled as data.
- **A price per trade** (the stock's close on the trade date as "the price paid"): no filing states it.
- **Copy-trading or alerts on reports:** not asked for; the edge lab found none (2023-2025 filings, 0 of 12).
