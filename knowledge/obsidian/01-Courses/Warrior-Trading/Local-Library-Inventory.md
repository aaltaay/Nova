---
title: Warrior Trading local library inventory (post-merge)
date: 2026-07-14
status: current
tags: [warrior-trading, library, pinecone, downloads]
---

# Warrior Trading — Local Library Inventory

Updated **2026-07-14** after member-dashboard sync + de-duplication against the existing `downloads/` tree.

**Live member site map (URLs, LMS catalog, Day Trade Dash widgets):** [[Authenticated-Site-Map]] · runbook `docs/warrior-authenticated-access.md`.

## Canonical roots (do not duplicate under `docs/`)

| Root | Purpose |
|------|---------|
| `downloads/warrior-trading-slides/` | LMS slide PDFs + layout packs by course |
| `downloads/warrior-trading-resources/` | Free ebook, Excel trade sheets, eSignal zips |
| `downloads/warrior-trading-caption-notes/` | Official captions + Whisper gap transcripts |
| `downloads/warrior-trading-videos/` | Local MP4s |

`docs/warrior-trading/` was created briefly then **removed** after merging unique files into the roots above (68 exact duplicate slide PDFs discarded).

## What was already present (do not re-download)

- BA101 Basics slides (1pp + 2pp) — already in Pinecone
- SS101 Strategies & Scaling slides ss-01…06, ss-08…15 — already in Pinecone
- Algo Scalping slides — already in Pinecone
- Caption notes / videos / COURSE_INVENTORY under `downloads/`

## What was newly added 2026-07-14

### Free / member resource pages → `warrior-trading-resources/`

- `free/How_To_Day_Trade_eBook.pdf` — public page `warriortrading.com/wt-ebook/`
- `excel/` — trade records templates + Roberto monthly tracker
- `esignal/` — Ross/Mike layout zips + MA-plot indicator zips

### Gaps filled in `warrior-trading-slides/`

| Location | Files |
|----------|-------|
| SS `ss-07 Part 1/2` | Missing `ss-07` 1pp/2pp part PDFs (large) |
| SS Chapter 13–17 | `ss-16`…`ss-20` 1pp/2pp |
| `4. Trader Rehab/` | `trader-rehab-complete.pdf` (replaced stub) |
| `5. Platform Demos & Layouts/` | DAS/TOS/Sterling zips + TOS PDFs (replaced stub) |
| Grad Jess / Danny / Max | `jess-course.pdf`, `danny-course.pdf`, `max-course.pdf` (replaced stubs) |

## LMS courses on the member account

1. Day Trading: The Basics (BA101)  
2. Day Trading: Strategies & Scaling (SS101)  
3. Live Trading Archives (LTA) — no PDF library hits  
4. Trader Rehab — PDF now on disk  
5. Platform Demos & Layouts — layout packs on disk  
6. Trading Psychology — no PDF library hits this sync  
7. Algo Scalping Strategy  
8. Day Trading in an IRA — no PDF hits  
9. Member Interviews — no PDF hits  
10–12. Grad courses (Jess / Danny / Max) — course PDFs on disk  

## Support / access notes

- Free ebook also referenced for Pro members via Strategies & Scaling → Course Handouts (support article 19000121612).
- Session cookies used once for sync; **not stored in repo**. Rotate WT session if cookies were pasted in chat.
- Paid PDFs stay under gitignored `downloads/`; this note is inventory only.

## Pinecone

Index: `nova-warrior-courses` · namespace: `warrior-slides`  
Ingest new slide/course PDFs with `tools/course_memory/ingest.py` (prefer `--layout 1pp`; use `--layout all` for non-`1pp` filenames like rehab/grad/ebook).

See also: [[Course-Index]], [[How-Recall-Works]], [[Memory-Router]]
