# ADR 039 -- Share clips: a red button that cuts video from the screen recording

**Status:** Proposed (2026-09-29) -- accepted when the operator approves mockup v1
**Builds on:** [[035-trading-screen-always-recorded]] (the screen recording every clip is cut from) ·
[[033-focus-and-book-watch-sensors]] (which tab and symbol each window shows) · the Session Record
(AGENTS.md §3 "Recording persistence and coverage", whose Record choice this sits beside)
**Decided by:** the operator, 2026-09-29, in seven multiple-choice answers (below)

## Context

The operator wants to record videos to share with the world: "maybe for one chart, maybe for two
charts ... maybe I want Level 2 and Time & Sales, so I guess that would be the entire screen". They
asked for it to be independent and chosen by hand, easy to find, perhaps grouped with the Level 2 /
Time & Sales recording. They also asked what happens when they look away, how many recordings can run
and how they would know which ones are on.

ADR 035 already records every monitor from launch to quit (15 fps, H.264, quarter-hour files under
`F:\Nova\screen`, nothing deleted). A clip therefore does not need a new camera.

## Decision

1. **A clip is a cut from the screen recording by default.** The red button marks a start and a stop
   on the recording that is already running, and an export cuts, crops and encodes the stretch. Cut
   clips cost nothing while the operator trades, have no cap and no time limit, and survive a Nova
   restart (the gap is marked). **Save the last 5 min** makes a finished clip ending now, since a trade
   is rarely known to be worth sharing until it is over. At export the start and end can move anywhere
   in the day.
2. **High quality on demand.** A switch on the button also starts a live 30 fps capture of the Nova
   window for that one clip. It runs in its **own hidden recorder process**, separate from ADR 035's,
   so a crash there can never stop the always-on recording. The live capture records the whole window;
   the crop happens at export. Wherever it has no frames (it failed, or restarted), the export takes
   that stretch from the cut, so a clip never has a hole. **At most 2 high-quality captures at once;
   each stops itself after 30 minutes**, with the chip counting down its last minute, and the clip
   then goes on as a cut.
3. **The picture is the symbol's Trader tab, header left out** by default: the charts, Level 2,
   Time & Sales and the plan, without the global bar and the tab strip (account id, Day's P&L, TAV).
   The export can choose panels, the whole Nova window or the whole monitor, and warns when the
   picture shows the header. It can blur a panel (the plan card carries the operator's size).
4. **Looking away does not stop a clip.** Nova marks the stretches when the tab was hidden, showed
   another symbol, or Nova was minimized, and the export offers to cut them. Nova cannot tell when
   another application covers the window; a cut shows whatever the monitor showed.
5. **One Record menu per symbol, two independent choices.** The Trader tab's red button and the symbol
   menu (right-click any ticker) offer **Market data** (the Session Record, unchanged: Level 2 and
   Time & Sales for Sim, one of the three Level 2 lines) and **Video clip**, each with its own start
   and stop. A video clip never uses a Level 2 line. The header shows a `CLIP` chip beside each `REC`
   chip; the Records page gets a **Video clips** list beside Session Records.
6. **No audio** for now.
7. **Quiet while it works, loud only when a clip has no picture** (neither source sees the tab), the
   rule REC and the screen chip already follow. A clip never stops or deletes the screen recording;
   deleting a clip deletes its exported file only. Nova never posts a clip: sharing the file is the
   operator's act, so ADR 035's "nothing uploads" holds.

The keys are two Nova Actions, "Start / stop clip" and "Save the last 5 min", acting on the focused
Trader tab and shipped unbound. The browser desk cannot see the screen (ADR 035), so its Record menu
locks Video clip and says why. A Sim replay desk can clip the replay; it has nothing live for Market
data.

## Shapes (proposed; AGENTS.md §3 confirms them in the implementing change)

- **Where.** `<dir>` = `NOVA_CLIPS_DIR`, else `F:\Nova\clips` while F: is mounted, else
  `<userData>\clips`. A clip's manifest is `<dir>/clips.jsonl`, one JSON object per line with
  `schema_version: 1` and `event`:
  - `open` `{clip_id, symbol, window_id, started_ts, origin: "button" | "symbol_menu" | "hotkey" |
    "last_n", picture: "trader_tab", display}`;
  - `mark` `{clip_id, ts, kind: "hidden" | "shown" | "symbol" | "geometry" | "screen_gap" |
    "restart", detail}` -- `geometry` carries the tab's rectangle on its monitor, in the layout
    pixels ADR 035 records at;
  - `hq` `{clip_id, ts, state: "start" | "end" | "lost" | "back", reason: "operator" | "limit" |
    "error" | "restart" | null, file}`;
  - `close` `{clip_id, ended_ts, reason: "operator" | "quit"}`;
  - `export` `{clip_id, export_id, state: "running" | "done" | "failed" | "cancelled", file, bytes,
    error, settings: {picture, start_ts, end_ts, cut: [[start, end], ...], blur: [panel, ...]}}`;
  - `delete` `{clip_id, file}`.

  An unknown version is refused and named, never guessed. A clip with an `open` and no `close` is
  still open after a restart.
- **The view**, one shape for every reader (the desk over IPC, and `POST /api/clips` for agents and
  the checklist, as ADR 035 does): `{schema_version: 1, generated_at, dir, dir_source, hq_max,
  hq_in_use, open: [{clip_id, symbol, started_ts, state: "ok" | "hidden" | "hq_lost" |
  "no_picture", hq: {since, ends_at} | null}], clips: [...], disk: {free_bytes, state}}`.
- **Exports** are MP4 (H.264) under `<dir>/<YYYY-MM-DD>/<SYMBOL>-<HHMMSS>.mp4`, the Eastern date and
  start time.
- **Constants** (`screenRecordPlan.mjs`'s neighbour): `CLIP_HQ_MAX_CONCURRENT = 2`,
  `CLIP_HQ_MAX_SEC = 1800`, `CLIP_HQ_WARN_SEC = 60`, `CLIP_LAST_N_SEC = 300`, `CLIP_HQ_FPS = 30`.

## Rejected

- **Live capture only** (a recorder per clip): an encoder for every open clip, a cap on how many, and
  no "save the last 5 minutes". It is kept as the high-quality option.
- **Always together with the Session Record**: every clip would cost one of the three Level 2 lines.
- **Recording a chart's canvas** (`canvas.captureStream`): charts only. Level 2 and Time & Sales are
  page elements, not a canvas.
- **Rendering from the recorded market data in Sim**: crisp at any size and free of personal details,
  but only for symbols with a Session Record, and without the operator's own orders, cursor or desk.
  It is a later add-on (clip a replay), not the base.

## Consequences

- A cut clip adds no load while trading. A high-quality capture is one more software encoder (ADR 035
  measured about half a core for three monitors at 15 fps; one window at 30 fps is to be measured).
- Cut clips are review quality: 15 fps at the monitor's layout size. The 4K monitor at 150% records at
  2560x1440, so a crop there is softer than on the 100% monitors.
- A clip's size counts toward the F: drive guard ADR 035 already warns on.

## To verify before building

- Whether the 15 fps picture is good enough to share (cut a 30 s sample from a real recording).
- The export path: WebCodecs in a hidden page (demux the Matroska, crop and blur on a canvas, encode,
  mux MP4; no new binary) against a bundled ffmpeg (fast, one binary; its licence and about 80 MB of
  installer).
- What a window capture sends while Nova is minimized, on the desk's mixed-DPI monitors.

## Rules and maps

- Mockup v1: the Share Clips design canvas (five boards: the Record menu, a clip recording, every
  state, export, Records › Video clips).
- Code to come: `frontend/electron/clip*.mjs` (the manifest, the high-quality recorder, the export),
  `frontend/src/clips/` (the Record menu, the chips, the Records list), `backend/clips/` (the view
  and a `clips` checklist row).
