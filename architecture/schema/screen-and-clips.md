# Data schema: Screen recording, graphics and share clips

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: frontend/electron/, backend/screen_record/, backend/clips/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The trading screen is always recorded (ADR 035, operator decision 2026-09-24)

"I always, always, always want the screen that I'm trading to be recorded.
Everything ... That's definitely not negotiable." The desktop app's main
process records every monitor from launch to quit (owner
`frontend/electron/screenRecorder.mjs`; plan `screenRecordPlan.mjs`, files
`screenRecordFiles.mjs`, a hidden recorder page `screenRecorder.html`). There
is no off switch: no button, setting or variable stops it;
`NOVA_SCREEN_RECORD_DIR` only moves the folder. The browser desk cannot record
the screen and says so.

**Files.** `<dir>/<YYYY-MM-DD>/<HHMMSS>-screen<N>.mkv` -- the Eastern date and
start time, monitors numbered left to right from 1 (`.webm` when Chromium has
no H.264 encoder) -- a new file per monitor on every quarter hour, started
before the old one stops. `<dir>` is `NOVA_SCREEN_RECORD_DIR`, else
`F:\Nova\screen` while F: is mounted, else `<userData>\screen` (the view says
`dir_source: "fallback"` and why). Beside them `segments.jsonl`, one JSON
object per line: `{schema_version: 1, event: "start", segment_id, file,
display: {id, index, count, label, primary, scale_factor, bounds}, width,
height, fps, bps, mime, started_ts}` and `{schema_version: 1, event: "end",
segment_id, file, ended_ts, bytes, reason: "rotation" | "quit" |
"display_change" | "stall" | "error" | "suspend" | "recorder_gone", error}`
(epoch seconds). A start with no end is a file cut short by a crash or power
loss; it plays up to its last write. Nothing deletes a recording (operator
decision 2026-09-24: "Keep every screen recording until I say otherwise; just
warn me when F: gets low" -- the drive guard below is that warning).

**The view** (one shape for every reader: the desk over IPC
`nova:screen-record:view` / `nova:screen-record:subscribe`, read-only, and
`POST /api/screen-record` every `SCREEN_RECORD_REPORT_SEC` and on each state
change): `{schema_version: 1, state: "starting" | "recording" | "partial" |
"failed" | "suspended" | "stopped", recording: boolean (every monitor), since:
number | null, error: string | null, dir, dir_source: "env" | "data_drive" |
"fallback", dir_note, dir_error, mime, fps, segment_min, displays: [{index,
count, id, label, primary, scale_factor, width, height, recording, since, file,
bytes, last_data_ts, error, retry_at}], unmatched: [{index, id, label}],
disk: {free_bytes, state: "ok" | "warn" | "fail" | "unknown", error,
checked_ts}, problems: [{at, display_index, reason, detail, resumed_at}]
(newest first, at most 10), restarts, generated_at}`. A monitor that fails,
stalls (no data for 12 s) or ends by itself is started again after 2, 5, 10,
30 s, then every 60 s, forever; a crashed recorder page is replaced; each loss
is a `problems` row until it is back.

`GET /api/screen-record` (owner `backend/screen_record/`, in memory, never
persisted) answers `{schema_version: 1, reported, fresh, age_sec, received_ts,
report: view | null}`; `fresh` is a report younger than
`SCREEN_RECORD_STALE_SEC` (35). `POST` refuses an unknown `schema_version`,
`state` or `dir_source` (422) and a body over 64 KB (413). `/api/diagnostics`
adds the `screen_recorder` row (group `recorder`): `fail` with no desktop app
reporting, a stale report, or any monitor not recording; `warn` while starting
or recording to the system drive; `off` while the PC sleeps; and the
leaderboard's drive guard (warn under 50 GB free, fail under 10 GB, only ever
worse). The header chip (`frontend/src/screen_record/`) is a monitor icon with a
red dot while every monitor records and a red "Screen not recording" the moment
one does not.

## The desk draws with the graphics card (operator decision 2026-10-05, #707)

"Especially when I move the chart left and right with my mouse and hold ... it really feels laggy." The desktop
app drew in software on Windows from the 2026-09-17 black-window fix, which changed three things at once and
never tested the graphics card alone. Dragging the 1-minute chart in Electron 41 on the demo desk (4K at 150%):
about 22 fps in software (frames 40-55 ms at the median, 38-56 ms of main-thread work), and frames of 5 ms at the
median with about 5 ms of work with the graphics card. It draws with the graphics card by default now, with a
safety net (owner `frontend/electron/graphics*.mjs`, wired by `gpuPolicy.mjs` and `graphics.mjs`):

- **The choice** is `graphics.json` in the app's userData: `{schema_version: 1, gpu: "on" | "off", reason:
  "operator" | "gpu_crashed" | "blank_window", at: number | null, detail: string | null, told: boolean}` (`at`
  epoch seconds; `told` once the operator was told why it is off). No file: the graphics card. A file of
  another version, or one Nova cannot read: software, said in the log. `NOVA_ELECTRON_GPU` (1 / 0) wins over
  the file. Occlusion tracking stays off on Windows either way.
- **View > Draw with the graphics card** (native menu, so it works over a blank page) shows the mode and
  switches it after a confirm, which restarts Nova; a note under it says why the safety net turned it off.
- **The graphics process ends abnormally** (`child-process-gone`, type `GPU`, not a clean exit or a kill):
  Chromium starts it again and Nova keeps running; the next start draws in software, and the operator is
  told at once.
- **The window goes blank**: every 5 s, while a desk window is focused, loaded 20 s, not minimised and the
  operator gave input within 15 s, the screen under it is read from the trading screen recording's own
  capture of that monitor (a `sample` command to the recorder page: a 96x54 picture, 75-290 ms; asking
  Windows for a screen picture took 0.9-1.6 s a call). A picture is blank when 97% of it sits within 6 levels
  of its median colour (healthy Trader pages measured 8-18%, a Scanner page 55%, whole monitors 53-81%). Only
  then is the page itself read (`capturePage`); a page as flat as that (over 90%, loading) decides nothing.
  The first blank look asks the window to draw again; three in a row store `blank_window` and restart Nova
  in software, which tells the operator once after it starts. Any look that decides nothing starts over.

## Share clips (ADR 039, operator ask 2026-09-29)

"I want to be able to record videos. Can I have maybe a small red button ... to share with the world?"
Owners: `frontend/electron/clip*.mjs` (the main process: marks, High quality, exports),
`frontend/src/clips/` (the desk), `backend/clips/` (the view for agents and the checklist). Nothing
here places, stages or cancels an order, and nothing deletes a screen recording (ADR 035).

**A clip is marks** on the always-on screen recording: the red ● on every Trader tab strip (and the
symbol menu, and two Nova Actions) opens and closes it; while it is open the main process marks where
its Trader tab is and whether it shows. It has no cap and no time limit, costs nothing while it runs,
and survives a restart: the next start marks the gap (`restart`) and goes on. **Save the last 5 min**
makes a closed clip from the tab's last `CLIP_LAST_N_SEC` (the main process keeps
`CLIP_TAB_HISTORY_SEC` of where each tab was, in memory); a tab that was not on screen then is
refused. A clip opened by hand starts with the same memory written as marks before its start, so the
export can begin up to `CLIP_TAB_HISTORY_SEC` earlier. Nova knows only what it marked: before a
clip's first mark and after it stopped, where the tab was is **not known** (never taken to be shown).
**High quality** adds a 30 fps capture of the tab's window (`desktopCapturer` window source)
in its own hidden page (`clipRecorder.html`), apart from ADR 035's: at most `CLIP_HQ_MAX_CONCURRENT`
(2) at once, each stopped at `CLIP_HQ_MAX_SEC` (30 min; the chip counts down the last minute), after
which the clip goes on as a cut. A capture that fails, stalls or ends by itself is started again with
back-off; after a restart it does not start again by itself. When the screen recording is not seeing
the tab's monitor a new clip records in high quality (else it is refused `CLIP_NO_PICTURE`).

**Files.** `<dir>` = `NOVA_CLIPS_DIR`, else `F:\Nova\clips` while F: is mounted, else
`<userData>\clips` (the view says `dir_source: "fallback"`). `<dir>/clips.jsonl`, one JSON object
per line, `schema_version: 1`, `ts` (epoch seconds) and `event`:
- `open` `{clip_id, started_ts, symbol, origin: "button" | "symbol_menu" | "hotkey" | "last_n",
  picture: "trader_tab", hq: boolean}`; `close` `{clip_id, ended_ts, reason: "operator"}` (a quit
  never closes one); `beat` `{clip_ids}` once a minute while any is open.
- `set` `{clip_id, hq: boolean, reason: "operator" | "limit" | "restart" | "clip_closed"}`.
- `mark` `{clip_id, kind, detail}`: `shown` `{window_id}`; `hidden` `{reason: "symbol" |
  "minimized" | "page" | "document" | "closed" | "not_open", showing: string | null}`; `geometry`
  `{window_id, display_id, content: {x, y, width, height}, inner: {w, h}, pane: {x, y, w, h},
  panels: {charts | level2 | tape | quote | plan | ticket | orders: {x, y, w, h}}}` -- `content` is
  the window's page on the screen in DIP, the rest the page's CSS pixels; `restart` `{down_since}`.
- `hq` `{clip_id, state: "start" | "end", file, window_id, reason: "operator" | "limit" | "error" |
  "window" | "restart" | "quit" | "clip_closed", error}` -- `file` relative to `<dir>`
  (`hq/<date>/<HHMMSS>-<SYMBOL>-hq.mkv`); the frame size is read from each decoded frame, never
  written here.
- `export` `{clip_id, export_id, state: "queued" | "running" | "done" | "failed" | "cancelled",
  file (`<date>/<SYMBOL>-<HHMMSS>.mp4`, relative), bytes, error, settings: {start_ts, end_ts,
  picture: "trader_tab" | "panels" | "window" | "monitor", panels, blur, cut_hidden, counts, out}}`.
- `delete` `{clip_id, files}` -- the clip's own exports and high-quality files only.

A row of another version, an unknown event or an unknown clip is counted and left out, never guessed.
Dates and times in names are Eastern.

**The view** (one shape for every reader: the desk over IPC `nova:clips:view` / `nova:clips:subscribe`,
and `POST /api/clips` every `CLIP_REPORT_MS` and on each change): `{schema_version: 1, generated_at,
dir, dir_source: "env" | "data_drive" | "fallback", dir_note, dir_error, skipped, hq_max, hq_in_use,
hq_max_sec, hq_warn_sec, last_n_sec, open: [{clip_id, symbol, started_ts, state: "ok" | "hidden" |
"hq_lost" | "no_picture", reason, showing, window_id, screen_recording: boolean | null, hq: {since,
ends_at, recording, lost, error, retry_at} | null}], clips: [{clip_id, symbol, origin, picture,
started_ts, ended_ts, length_sec, status: "recording" | "not_exported" | "queued" | "exporting" |
"ready" | "failed" | "cancelled", hq_sec, hidden_sec, gap_sec, export: {export_id, state, file,
bytes, error, note, progress, picture, blur} | null}] (newest first, at most `CLIP_VIEW_MAX`; the
backend keeps 50), exporting: {export_id, clip_id, done_sec, duration} | null, queued, tabs:
[{window_id, symbol, visible, display_id, screen_recording}], disk: {free_bytes, state, error}}`.

**The tab report** (every desk window, `nova:clips:tab`, on each change and every
`CLIP_TAB_REPORT_MS`; `frontend/src/clips/clipTabReport.ts`): `{schema_version: 1, window_id,
visible, reason: "page" | "document" | "draft" | null, symbol, pane: {x, y, w, h} | null, panels,
inner: {w, h}}` -- the active Trader tab's pane (`sv-tab-pane-<SYMBOL>`) and its panels by
data-testid, in CSS pixels (a panel of several parts, such as the rail's quote head and stats, is the
box around them); the main process adds the window's place and whether it is minimized.

**Requests** (`nova:clips:act`, from desk windows only; an answer is `{ok: true, ...}` or `{ok:
false, reason, error}`): `start {symbol, hq, origin}`, `stop {clip_id | symbol}`, `save_last {symbol,
seconds}`, `set_hq {clip_id, on}`, `detail {clip_id, from_ts, to_ts}` (the export dialog's tracks),
`plan {clip_id, settings}` (the export without making it), `export {clip_id, settings}`,
`cancel_export {export_id}`, `preview {clip_id, ts, picture, panels, blur}` (a JPEG data URL),
`delete`, `show`, `play`. Refusals: `CLIP_INVALID`, `CLIP_NO_TAB`, `CLIP_HQ_FULL`,
`CLIP_NO_PICTURE`, `CLIP_NOT_OPEN`, `CLIP_NOT_ON_SCREEN`, `CLIP_UNKNOWN`, `CLIP_OPEN` (stop it
first), `CLIP_EXPORTING`, `CLIP_NOTHING_TO_EXPORT`, `CLIP_NO_FRAME`, `CLIP_EXPORT_UNKNOWN`,
`CLIP_DELETE_FAILED`, `CLIP_NO_FILE`, `CLIP_OPEN_FAILED`, `CLIP_FORBIDDEN`, `CLIP_ERROR`.

**The export** (`clipExportPlan.mjs`, pure; `clipExporter.mjs`; the page `clip-export.html`,
`frontend/src/clips/export_page/`, WebCodecs + mediabunny): the stretch is cut wherever something
changes; each slice takes its picture from a high-quality file that ran in the tab's window, else from
the screen segment of the tab's monitor (ADR 035's `segments.jsonl`), so a lost capture leaves no
hole. Hidden stretches are cut when `cut_hidden` (the default); restart gaps, stretches Nova was not
following the tab (`unknown_sec`, whatever `cut_hidden` says) and stretches with no picture are left
out and counted -- `counts: {hq_sec, screen_sec, hidden_sec, gap_sec, unknown_sec, no_picture_sec}`;
the dialog's tracks add `unknown`. A cut is the monitor's picture: a window over the tab is in it (the
dialog says so; High quality records the tab itself). The blurred panels are the rail's trade card
(`stock-view-open-card`), the plan and the orders dock with its position line; the charts' own
position line is not blurred, and the dialog says that too. A screen crop maps the page's rectangle through `content` onto the
segment's display bounds and size; a window capture's is worked out from each decoded frame (the frame
is the window's visible rectangle, the page at its bottom-left under the title bar; measured on the
desk's monitors at 100% and 150%). The MP4 (H.264) is at a constant rate -- 30 fps with any high
quality, else 15 -- each output frame the source frame showing at that moment, fitted without
stretching, with the chosen panels blurred; at most `CLIP_OUT_MAX_WIDTH` x `CLIP_OUT_MAX_HEIGHT`. The
sandboxed page reads sources and writes the MP4 only through the main process, by the tokens a job
names; the MP4 is written to `.mp4.part` and renamed when done. Frames are walked with the sample
iterator, never looked up one timestamp at a time (mediabunny 1.61's key-packet lookup missed a
keyframe in a real segment on 2026-09-29). Nova never posts a clip.

**The desk.** The red ● (`RecordButton`) opens the Record menu: Market data (the Session Record,
unchanged, stopping is a hold) and Video clip (Start / Stop, Save the last 5 min, High quality), every
lock with its reason. The header's CLIP chips count up beside REC (amber for High quality's last
minute or a lost capture, dimmed for a hidden tab, red only with no picture); pointing at one shows its
card and has the tab draw its red frame; a click stops the clip and a toast offers the export. The
export dialog: the preview, the picture, the panels to blur (the plan, the order ticket and positions
& orders on by default), the trim timeline over the day (moments from the eyes' journal, the screen
recording, high quality, when the tab showed the symbol), the output line and X's 2:20 hint. Records
› Video clips lists every clip by Eastern day with the actions of its state. The Nova Actions
`clip_toggle` and `clip_save_last` ship unbound; `runNovaAction` hands them to the clips feature before
any gate. A browser desk has no clips and says so.

**The backend.** `GET /api/clips` answers `{schema_version: 1, reported, fresh, age_sec,
received_ts, view}` (`fresh`: younger than `CLIPS_STALE_SEC`); `POST` refuses an unknown
`schema_version`, `dir_source` or open-clip `state` (422) and a body over 256 KB (413). The checklist
row `clips` (group `recorder`) is `off` with no desktop app reporting, `unknown` on a stale report,
`ok` in the ordinary run, `warn` on a lost high-quality capture, an unwritable clip list or the system
drive, and `fail` only when an open clip has no picture. The perf recorder (ADR 026) names the two
hidden pages' processes `clip-recorder` (High quality) and `clip-export` in the Electron report's
`processes`, beside `screen-recorder`, and the focus sensor (ADR 033) leaves all three out: they are
never a window the operator sees. Their `cpu_pct` is Electron's, divided by the logical CPUs (24 on
the desk PC), so 3.5 there is about 0.84 of a core.

