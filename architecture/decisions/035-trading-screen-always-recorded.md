# ADR 035 -- The trading screen is always recorded

**Status:** Accepted · **Date:** 2026-09-24
**Builds on:** [[021-desk-self-heal]] (the diagnostics checklist) · [[026-performance-recorder]] (Electron main-process reports) · [[033-focus-and-book-watch-sensors]] (monitors numbered left to right)
**Decided by:** the operator, 2026-09-24 ("moving forward, I always, always, always want the screen that
I'm trading to be recorded. Everything, I want it to be recorded. That's definitely not negotiable.")

## Context

Nova records the market it trades (Session Records, the leaderboard, the tape archive) but not what
the operator saw. When a trade goes wrong, the question is often "what was on my screen when I
clicked?" -- a stale quote, the wrong tab, a toast that covered the ticket -- and nothing can answer
it. The operator wants the screen recorded all the time, with no way for it to be quietly off.

## Decision

1. **The desktop app records every monitor, from launch to quit, with no off switch.** The Electron
   main process owns it (`frontend/electron/screenRecorder.mjs`); a hidden window with its own renderer
   process (`screenRecorder.html`) captures each screen with Chromium's desktop capture and encodes it
   with `MediaRecorder`, so encoding never runs on a desk window's thread. There is no button, setting
   or environment variable that stops it; `NOVA_SCREEN_RECORD_DIR` only moves the folder.
2. **Every monitor, the whole screen.** "Everything": other applications on the screen are recorded
   too. Each monitor is captured at its Windows layout size (a 4K monitor at 150% records at
   2560x1440), 15 fps, H.264 in Matroska (`.mkv`, which Windows plays) when Chromium can encode it,
   else VP9 / VP8 in WebM. The bitrate is a cap of pixels x fps x 0.045 (2.5 Mbps at 1440p). The
   cursor is in the picture; there is no audio.
3. **Files by the quarter hour.** `<dir>/<YYYY-MM-DD>/<HHMMSS>-screen<N>.mkv` (Eastern date and start
   time, monitors numbered left to right) with `segments.jsonl` beside them; a new file starts on each
   quarter hour and is recording before the old one stops, so rotation leaves no gap. `<dir>` is
   `NOVA_SCREEN_RECORD_DIR`, else `F:\Nova\screen` while F: is mounted, else the app's own folder on the
   system drive -- recording on C: beats not recording, and the desk says so.
4. **Resume, then say so** (the Session Record's policy). A monitor whose capture fails, stalls (no
   data for 12 s -- a still screen still sends a frame a second) or ends by itself is started again
   with backoff (2, 5, 10, 30 s, then every 60 s, forever); a crashed recorder process is replaced; a
   display change re-plans (a renumbered monitor keeps its file); sleep pauses and wake resumes; unlocking
   the screen retries at once. Each loss is recorded with its reason and when it came back.
5. **Quiet when recording, loud when not.** The header carries a monitor icon with a red dot while
   every monitor records (details on hover); it turns into a pulsing red "Screen not recording" or
   "Screen: 1 of 2 recorded" the moment that is not true, amber for a recording on the system drive
   or a filling drive. A browser desk cannot record the screen, and its chip says "Screen not recorded".
6. **The checklist fails when nothing says the screen is recorded.** The desktop app posts its status
   to `POST /api/screen-record` every 10 s and on each change; `GET /api/screen-record` answers it for
   agents, and the `screen_recorder` diagnostics row (group `recorder`) fails with no desktop app
   reporting, a report older than 35 s, or a monitor not recording. It guards the drive like the
   leaderboard (#485): warn under 50 GB free, fail under 10 GB.
7. **Keep everything; warn when F: gets low** (operator decision, 2026-09-24: "Keep every screen
   recording until I say otherwise; just warn me when F: gets low"). Nothing deletes a recording. The
   drive guard is the warning: the header chip turns amber under 50 GB free on the recording drive and
   red under 10 GB, and the `screen_recorder` checklist row warns and fails at the same lines. Only the
   operator changes this.
8. **Private by construction.** Recordings stay on this PC. Nothing uploads them, and the issue
   report's dump carries only the status row (paths scrubbed), never a frame.

## Measured (the desk PC, 2026-09-24)

A 30 s probe of all three monitors (2560x1440, 1920x1200, 4K at 150%) with Nova's software-raster GPU
policy: H.264 cost about half a core in the recorder process and a quarter core in the main process
(capture), 273 MB an hour on a quiet after-hours screen; VP9 cost a little less CPU but blurred small
coloured text and took 626 MB an hour. H.264 kept the Focus list and the order grid legible. A busy
trading day approaches the cap: up to about 2.9 GB an hour for the three monitors, so a 16-hour day is
a few GB to tens of GB. With the hardware encoder (GPU on) the recorder was near-free; the desk drew in
software on Windows when this was measured. Since 2026-10-05 (#707) it draws with the graphics card by
default and falls back to software after a graphics-process crash, a blank window or the operator's
choice (`graphicsChoice.mjs`, `graphicsWatch.mjs`; schema in `architecture/schema/screen-and-clips.md`).

## Measured again with the graphics card (the desk PC, 2026-10-09)

From the desk's own performance record (ADR 026, every 5 s), 2026-10-02 to 2026-10-09: software drawing
on v1083-v1099, the graphics card from v1104 on (the safety net never turned it off). Both periods used the
same three monitors, H.264 settings and Electron 41.10.6. The only recorder change between them is the
safety net's `sample` command, which adds work. Only quarter hours in which all three monitors recorded a
full file count. They are matched on market activity, which neither the encoder nor the drawing mode
changes: the market events the backend took in from IBKR (`ib.tape` + `ib.depth` + `ib.l1`), cut into
quartiles over both periods. Bytes written are not a fair match, since each mode has its own encoder and
the same screen comes out a different size. In % of one core:

| Market events per quarter hour | Quarter hours (software / card) | Recorder process, median | Main process, median | Graphics process, mean |
|---|---|---|---|---|
| top quartile, over 55,000 (a busy session) | 31 / 106 | 132 -> 2.4 | 50 -> 19 | 58 -> 35 |
| third quartile, 12,900-55,000 | 5 / 131 | 58 -> 2.4 | 22 -> 25 | 16 -> 17 |

2.4 is the record's smallest step before 2026-10-09; that day's finer readings put the recorder at 1.8%
median. With the graphics card the recorder process sat at 0-3.3% median in every quartile, on this measure
and on the market data sent to visible desk windows, which gives the same busy-quartile result (132 ->
2.4). In the busy quartile the main and graphics processes used less as well, so no other process took
the encoding over. That fits the graphics card's hardware encoder doing it.

What this does not show: the software side's quieter quarter hours are nearly all ones in which the market
sent nothing (overnight and the weekend of 2026-10-03/04, when the screen may have been locked), so quiet
screens are not compared. The twelve builds between the periods also changed the main process (ADR 045's
priority loop, for one), so its numbers are not the recorder's alone.

The real module, run in Electron against the three monitors with a 20 s rotation: every monitor was
recording within 1 s; files rotated with the new one started before the old one ended; a forced
recorder crash was recovered in about 3 s with the loss recorded (2 s of that is the first backoff);
files cut by the crash or the quit played up to their last timeslice, since shortened from 2 s to 1 s.

## Consequences

- The recording cost roughly one CPU core of 24 on the desk PC while the desk drew in software, more in a
  busy session. With the graphics card (the default since 2026-10-05) its own process takes about 2% of a
  core at any market activity (2026-10-09 measurement above). What capture costs inside the main process
  was not separated.
- Disk space grows without end by the operator's choice (decision 7): at the caps a busy day can take
  tens of GB, so F:'s 846 GB free on 2026-09-24 lasts weeks to months of full days, and the drive guard
  says when it runs low.
- A crash, power loss or quit can lose the last timeslice (1 s) of each open file, and a recorder
  crash leaves a gap of a few seconds while it is replaced; both are in the manifest.
- The Windows lock screen and UAC's secure desktop may not be capturable; the desk shows the monitors
  as not recording until the capture comes back.
- Recordings are not linked to Sim playback yet: the manifest's times would let a later change show the
  screen at the replay playhead.
- The browser desk cannot record; the operator trades from the desktop app.

## Rules and maps

- Shapes: AGENTS.md §3 "The trading screen is always recorded".
- Code: `frontend/electron/screenRecord*.mjs`, `screenRecorder.html`, `screenRecorderPreload.cjs`;
  `frontend/src/screen_record/`; `backend/screen_record/`, `backend/diagnostics/collect_screen_record.py`.
