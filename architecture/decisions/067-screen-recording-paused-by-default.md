# ADR 067 -- Screen recording is paused by default

**Status:** Accepted · **Date:** 2026-10-24
**Amends:** [[035-trading-screen-always-recorded]] decisions 1, 5 and 6 (no off switch; loud when not recording; the
checklist fails when nothing says the screen is recorded). Everything else in ADR 035 holds whenever the recording is on.
**Related:** [[039-share-clips]] (clips are cut from the recording) · [[038-installed-backend-ownership]] and the in-app
updates (#347, `AGENTS.md` §8: how the installed desk and its backend get this release)
**Decided by:** the operator, 2026-10-24: "I don't know why it's saving it like that ... let's pause this. All
recordings just have a flag: pause it by default. This feature is useful, but we're really not using it right now."
They then deleted the old screen recordings themselves.

## Context

ADR 035 records every monitor from the moment the desktop app starts until it quits, with no off switch, and keeps
every file. That is why it saved the way it did:

- **A file per monitor every quarter hour, around the clock.** Each monitor gets its own file, and a new one starts on
  every quarter hour: with three monitors that is 12 files an hour, and 288 a day when Nova stays open overnight, as it
  does on the desk. The night and the weekend are recorded too, because nothing stops the recording but a quit.
- **Size.** ADR 035 measured about 0.3 GB an hour for the three monitors on a still screen and up to about 2.9 GB an hour
  on a busy one. A day with Nova open came to about 6 to 20 GB.
- **Nothing deletes a recording** (ADR 035 decision 7). On the desk that came to about 204 GB in 29 days, and the 1 TB
  data drive was down to about 56 GB free on 2026-10-24, just above the drive guard's 50 GB warning.

The recording is useful when a trade needs reviewing, but it is not being used now. The market-data Session Records
(about 0.2 GB a day) are a separate feature and are not changed here.

## Decision

1. **Paused by default; one flag turns it on.** `NOVA_SCREEN_RECORD` is a desk setting: the process environment wins,
   else the desk `.env` (the file the engine reads). The desktop app reads it once, when it starts. `1`, `true`, `yes`
   or `on` (any case) records; unset, empty or anything else is paused. A change takes a restart of Nova.
2. **Paused records nothing.** No hidden recorder window or process, no capture, no file, no manifest, no folder (not
   even `F:\Nova\screen` is created), no check of the drive. Nova does not open, move or delete anything already in the
   folder: the operator manages those files.
3. **On is ADR 035, unchanged.** Every monitor from launch to quit, a new file per monitor every quarter hour,
   `NOVA_SCREEN_RECORD_DIR` else `F:\Nova\screen` while F: is mounted else the app's own folder, resume then say so,
   loud the moment a monitor is not recorded, the drive guard (warn under 50 GB free, fail under 10 GB), and nothing
   deletes a recording.
4. **Paused is said, never silent and never an alarm.** The view every reader gets says `state: "paused"`: the same
   shape, with no monitors and no problems, the drive not read, and `dir` where it would record once on. The header
   chip shows a monitor with a slash and "Screen rec paused" in muted grey, without the red recording dot; pointing at
   it says the recording is off by default and how to turn it on. The `screen_recorder` checklist row is `off`, with
   the same words. With no desktop app reporting, the row is `off` unless the backend's own environment turns the flag
   on; then it fails as before. A browser desk's chip says "Screen not recorded", muted too.
5. **What leans on the recording says so.** A new share clip (ADR 039) records in High quality while the screen
   recording is paused, as it already did for a monitor the recording did not see: at most two at once, each for 30
   minutes, after which the clip has no picture and its chip turns red. "Save the last 5 min" is locked with the reason
   and refused `CLIP_NO_PICTURE`, since there is no recording to cut from; the Record menu and the symbol menu say the
   recording is paused, and the clips view carries `screen_paused`. The graphics card's safety net (#707) reads the
   recording's live picture to spot a blank window: while paused it has no picture and decides nothing. A
   graphics-process crash still switches the desk to software drawing.

## Why a launch flag, not a switch on the desk

- It is how the desk's own settings already work: `NOVA_UPDATE_CHECK`, `NOVA_UPDATE_AUTO_INSTALL`,
  `NOVA_SCREEN_RECORD_DIR`. One line in the desk `.env`, read when the desktop app starts.
- No page can start, stop or pause the recording; ADR 035's status bridge stays read-only for every reader.
- The recorder was built to run from launch to quit. A live switch would add a start-and-stop path to it, and a saved
  setting beside `graphics.json`, for a feature that is not being used now. If the operator wants to flip it often, a
  View-menu item like Draw with the graphics card is the next step.

## Rejected

- **A switch on the desk now:** see above.
- **Keep recording and delete old files by age:** the operator manages the files, and Nova deletes no recording
  (ADR 035 decision 7 stands).
- **Record less (market hours only, the Nova windows only, a lower frame rate):** smaller, but the operator asked to
  pause it.

## Consequences

- While paused nothing is written, so the drive stops filling by about 6 to 20 GB a day.
- While paused, "what was on my screen when I clicked?" (ADR 035's reason) has no answer unless the recording was
  turned on first. The Session Records still record the market.
- The installed desk changes when it installs the release that carries this (the in-app updates, #347: a published
  release installs by itself outside weekday 07:00-16:00 ET once nothing is at stake and the PC has been idle for 5
  minutes, or at Restart to update). Until then the running desk records as before, and quitting the Nova desktop app
  is the only way to stop it.

## Rules and maps

- Shapes: `architecture/schema/screen-and-clips.md`, "The trading screen recording, paused by default".
- Code: `frontend/electron/screenRecordPlan.mjs` (`SCREEN_RECORD_ENV`, `screenRecordOn`, `pausedView`),
  `screenRecorder.mjs` (the paused stand-in), `envMerge.mjs` (`readDeskSetting`), `frontend/src/screen_record/`;
  `backend/diagnostics/collect_screen_record.py`; clips in `frontend/electron/clipService*.mjs`,
  `frontend/src/clips/clipModel.ts`, `backend/diagnostics/collect_clips.py`.
