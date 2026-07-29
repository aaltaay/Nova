# 2026-07-29 -- Quote panel News collapses to one header

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / quote UI
- **Related:** `CHANGELOG.md` §2026-07-29 -- Quote panel News collapses to one header

## Task

Wrap the quote-panel bump/impact block and news headline chips under one collapsible **News** header; default collapsed with only the lead headline visible.

## Goal

Reclaim vertical space in the side quote panel while keeping the most important headline glanceable without expanding.

## Why it mattered

Impact factors + multiple headline cards were always expanded and crowded Level 2 / fundamentals. The user still needs the headline at a glance when scanning tickers.

## What we changed

- `NewsHeadlineSection` owns expand state; single "News" toggle header with chevron + truncated preview when collapsed.
- Expanded body shows `NewsImpactPanel` + horizontal chips (removed nested "News Headline" sub-header).
- `NewsPanel` remounts the section on `detail.symbol` so expand state resets per ticker.
- Constants: `NEWS_SECTION_TITLE`, `NEWS_SECTION_DEFAULT_EXPANDED`.
- CSS for toggle/preview; nested impact panel loses its outer box so it sits inside the one News border.
- Vitest: collapsed-by-default + expand reveals impact/list.

## How it works now

One `.cq-news-section` container. Collapsed: header row only (`News` + preview from `news_impact.headline` else first article + count). Expanded: full impact verdict + chip strip. Symbol change remounts collapsed.

## Why this approach

- Kept collapse state in the section component (not localStorage) so default-collapsed stays predictable and symbol switches reset cleanly via `key={symbol}`.
- Rejected nesting impact outside News -- user asked for one container.
- Rejected making the collapsed preview a link (would fight the expand click); article links remain on expanded chips / impact headline.
- Native `<details>` was rejected so we control preview-in-header layout and `data-news-expanded` for tests.

## Verification

`npm test -- --run src/modules/quotePanels.test.tsx` (13 passed).

## Follow-ups

Optional: persist expand preference; browser click-path on live quote panel if layout needs tuning after HMR.

## Keywords

news, collapse, quote panel, NewsHeadlineSection, news impact, headline preview
