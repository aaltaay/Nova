# Course Index

| # | Course | PDFs on disk | In Pinecone |
|---|---|---|---|
| 1 | Day Trading - The Basics | Yes | Yes (ingested) |
| 2 | Day Trading - Strategies & Scaling | Yes | Yes (ingested) |
| 3 | Live Trading Archives | No slides found | — |
| 4 | Trader Rehab | No slides found | — |
| 5 | Platform Demos & Layouts | No slides found | — |
| 6 | Trading Psychology | No slides found | — |
| 7 | Algo Scalping Strategy | Yes | Yes (ingested) |
| 8–12 | IRA / Interviews / Grad courses | No slides found | — |

PDF root: `downloads/warrior-trading-slides/`  
Video root: `downloads/warrior-trading-videos/` (local only — gitignored under `downloads/`)  
**Full transcripts (local only):** `downloads/warrior-trading-caption-notes/{BA101,SS101,LTA,DE101}/`  
Pinecone index: `nova-warrior-courses` · namespace: `warrior-slides` · slide PDFs (transcript ingest optional)

### Timestamped transcripts (match the video)

Full transcripts stay under `downloads/` (gitignored) so paid course text is not committed.

| Course | Units | How transcript was produced |
|---|---|---|
| BA101 | 12 | Official LMS captions where available; Whisper on local MP4 audio for Ch2.2–2.3, Ch3.2–3.3, Ch4.1–4.3 |
| SS101 | 3 | Official LMS English caption tracks |
| LTA | 9 | Official LMS English caption tracks |
| DE101 | 1 | Official LMS English caption track (`mentor-session-on-warrior-sim.md`) |

Rebuild: `downloads/warrior-trading-caption-notes/_export_official_transcripts.py` and `_whisper_local_videos.py`.  
Inventory: `downloads/warrior-trading-caption-notes/COURSE_INVENTORY.md`.

See also: [[Warrior-Trading/BA101-Timestamped-Notes]], [[Warrior-Trading/SS101-Timestamped-Notes]], [[Warrior-Trading/LTA-Timestamped-Notes]], [[Warrior-Trading/DE101-Timestamped-Notes]] (pointers only).

### LMS inventory

The authenticated dashboard currently exposes 12 courses. BA101 has 35 video units; the 11 additional courses contain 176 chapter sequences and 573 units. Across the additional courses, 13 Wistia videos expose English captions. No caption tracks were exposed by Trader Rehab, Trading Psychology, Algo Scalping, Day Trading in an IRA, Member Interviews, or the three graduate courses.

### Day Trading: The Basics — videos on disk

| File | Lesson |
|---|---|
| `Day-Trading-The-Basics/Ch01_Becoming_a_Day_Trader.mp4` | Chapter 1 |
| `Day-Trading-The-Basics/Ch02_Part1_Different_Account_Types_for_Traders.mp4` | Ch 2 Part 1 |
| `Day-Trading-The-Basics/Ch02_Part2_Choosing_a_Broker.mp4` | Ch 2 Part 2 |
| `Day-Trading-The-Basics/Ch02_Part3_Emergency_Plan.mp4` | Ch 2 Part 3 |
| `Day-Trading-The-Basics/Ch03_Part1_Large_Cap_vs_Small_Cap_vs_Penny_Stocks.mp4` | Ch 3 Part 1 |
| `Day-Trading-The-Basics/Ch03_Part2_Long_vs_Short_Selling.mp4` | Ch 3 Part 2 |
| `Day-Trading-The-Basics/Ch03_Part3_What_Makes_a_Strong_Stock.mp4` | Ch 3 Part 3 |
| `Day-Trading-The-Basics/Ch04_Part1_Fundamental_Analysis.mp4` | Ch 4 Part 1 |
| `Day-Trading-The-Basics/Ch04_Part2_SEC_Filings.mp4` | Ch 4 Part 2 |
| `Day-Trading-The-Basics/Ch04_Part3_News_Catalysts.mp4` | Ch 4 Part 3 |
