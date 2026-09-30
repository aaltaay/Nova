# ADR 039 -- Share clips: a red button that cuts video from the screen recording

**Status:** Accepted (2026-09-29; the operator approved mockup v1: "1 go")
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
   is rarely known to be worth sharing until it is over. At export the start and end can move as far
   as Nova followed the tab: from up to 30 minutes before the clip (the desk keeps that much of where
   each tab was) to its stop. Outside that Nova does not know where the tab was, so the export leaves
   it out and says so, rather than guessing a crop.
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
   picture shows the header. It can blur a panel (the plan card, the trade card and the orders dock
   carry the operator's size and P&L); the charts' position line is not blurred, and the export says so.
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

## Shapes

Confirmed in AGENTS.md §3, "Share clips": the manifest rows (`open`, `set`, `mark`, `hq`, `close`,
`beat`, `export`, `delete` in `<dir>/clips.jsonl`), the view every reader gets, the tab report each
desk window sends, the requests and their refusals, and `GET` / `POST /api/clips`. The numbers live in
`frontend/electron/clipPlan.mjs` (`CLIP_HQ_MAX_CONCURRENT = 2`, `CLIP_HQ_MAX_SEC = 1800`,
`CLIP_HQ_WARN_SEC = 60`, `CLIP_LAST_N_SEC = 300`, `CLIP_HQ_FPS = 30`) and `backend/constants_clips.py`.

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

## Measured before building (the desk PC, 2026-09-29)

- **The export path.** WebCodecs H.264 encodes and decodes in a hidden Electron 39 page with the GPU
  off, as the desk runs it. mediabunny reads the screen recorder's own Matroska (a real 15-minute
  segment: 2,453 packets, keyframes every ~40 s); a 10 s crop of it encoded in 0.46 s. No ffmpeg, no
  new binary; mediabunny (MPL-2.0) is bundled into the export page by Vite. Its key-packet lookup
  missed a keyframe in that segment (no frame for 895 s though one at 864 s decoded), so the page walks
  frames with the iterator from each piece's start instead.
- **A window capture on the mixed-DPI desk.** On all three monitors (100% and 150%) the captured frame
  is the window's visible rectangle, the page at its bottom-left at the monitor's scale under the title
  bar; a covered window still captures its own content; a minimized one sends no frames (the chip says
  hidden and the export fills from the screen recording or cuts it). The frame size a capture reports
  at start is the requested maximum, not the frame's, so the crop is worked out per decoded frame.
- **End to end,** with the real service and export page against the desk's live screen recording on F:
  (a test window standing in for a Trader tab): a 12 s high-quality clip (11.9 s high quality, the first
  0.2 s from the screen recording while the capture started) and a "last 14 s" cut both exported as
  playable MP4s (984 x 594; 30 fps and 15 fps); the header was out of both, and the blurred plan card's
  pixel variance fell from 1,625 to 42.
- **Through the desk itself** (the built desk in sample mode, the real preload, bridge and service, driven
  by clicks on the red button, the menu, the CLIP chip, the toast and the dialog): a 9.7 s clip exported
  as a playable 1246 x 778 MP4 at 15 fps. It caught two faults the unit tests had not: the order ticket's
  blur named an element no component renders (the ticket stayed readable; a test now checks every blur
  target against the components), and the trim timeline took the tab to be shown before the clip's
  first mark. It also showed a window of another app over the desk in the cut, as decision 4 says.
- **Still the operator's to judge:** whether the 15 fps cut is sharp enough to post.

## Rules and maps

- Mockup v1: the Share Clips design canvas (five boards: the Record menu, a clip recording, every
  state, export, Records › Video clips).
- Shapes: AGENTS.md §3 "Share clips".
- Code: `frontend/electron/clip*.mjs`, `clipRecorder.html`, `clipRecorderPreload.cjs`,
  `clipExportPreload.cjs`; `frontend/clip-export.html` and `frontend/src/clips/` (with `export_page/`);
  `backend/clips/`, `backend/diagnostics/collect_clips.py`.
