# ADR 038: Who owns the backend the installed desk talks to

**Status:** Accepted (2026-09-29), amended the same day (operator: "1 go")

## Context

The Windows installer ships the Electron desk and a PyInstaller engine
(`nova-api.exe`). The operator does not run that engine: the backend is the
**checkout engine** the localhost watchdog, `scripts/windows/Run Nova.bat` and the morning
script start from `C:\Users\aalta\github\Nova`. Its data sits behind the
checkout's `backend\.cache` (moved to `F:\Nova\cache`), and its `.env` holds the
IBKR settings and the Live PIN hash. The bundled engine reads the app's own
folder (`%APPDATA%\nova\cache`, `%APPDATA%\nova\.env`): a different Paper
account, bot session, kill-switch latch and history.

The two halves update through different channels. The desk updates itself
through the installer. The backend's code comes from git, and it loads only when
the process restarts. So they drift: on 2026-09-29 the title read
`desk v1027 · backend v1025 (older -- restart it)`. The process had outlived its
own checkout, which already held v1027.

The first version of this ADR (pushed as `64a25abe`, released as v1028) made the
bundled engine the owner. At launch it asked about any other engine: retry with
the packaged backend, use the external one for this session, or exit. On this
desk that is wrong in three ways:

- **It treats the operator's real backend as the stranger.** The watchdog's
  checkout engine is the normal case, so the prompt appears at every launch.
  A prompt shown every day teaches click-through.
- **Its default button points at the other Nova.** "Retry with packaged
  backend" leads to the engine with the separate Paper account and bot session.
  On a trading desk that must never be the one-click default.
- **It treats the symptom, not the cause.** A launch prompt does not close the
  gap between the two update channels.

It also had a bug. A healthy port whose identity could not be read in time (the
checklist has a 20 s timeout) was treated as an empty port, so the desk started
a second engine on top of it. That was fixed before the push.

## Decision

1. **Whatever Nova engine answers `:8000` is used as it is.** At launch the desk
   never asks about it, never stops it and never starts a second engine over it.
   The window title keeps naming its revision.
2. **The checkout engine is the owner, and the desk remembers it.** When the
   engine runs from a main checkout (its `.git` is a folder, so never an agent's
   worktree), and that checkout holds a `.env` and `scripts\Start-NovaApi.ps1`,
   the desk records the checkout in `%APPDATA%\nova\engine-owner.json`
   (`{schema_version: 1, repo_root, seen_at}`). An unknown version, an
   unreadable file, or a checkout that lost its start script reads as no owner.
   Deleting the file goes back to the bundled engine.
3. **On an empty port, the desk starts the owner's engine first.** It uses the
   checkout's own `Start-NovaApi.ps1`, the way `scripts/windows/Run Nova.bat` does, so the data,
   the `.env` and the code channel are the operator's usual ones. The engine
   outlives the desk, like a watchdog engine. If it does not answer, the desk
   offers:
   - **Retry** (the default),
   - **Use the bundled backend this session** (the prompt names its separate
     data folder),
   - **Exit**.

   With no owner remembered, the bundled engine starts as before: it holds the
   only data a desk-only install has.
4. **The backend notice.** While the backend runs older code than the desk, a
   strip under the header (beside the update notice) offers the one action
   that helps:
   - **Restart backend now** when its checkout already holds newer code.
   - **Pull master and restart** when the checkout holds nothing newer. The
     desk pulls the owner's checkout fast-forward only, and only on a clean
     `master`. It refuses when master changes `backend/requirements.txt`, whose
     packages must be installed first. Then it restarts the backend onto the
     new code.

   Before either action, the desk asks the backend what a restart would
   interrupt (`GET /api/diagnostics/restart-check`). If nothing is open, one
   click restarts. If anything is open, or the backend is too old to say, the
   desk lists it and restarts only once confirmed. A pull is always confirmed.
5. **Nothing pulls or restarts on a timer** -- except a backend behind the
   desk's own release, which follows it by itself (amendment 2026-10-13,
   below). An unattended nightly pull and
   restart was proposed and is **not built**: it installs recurring automation
   that changes the operator's checkout and restarts the trading backend
   without a per-action approval. It waits for the operator's explicit say-so.
6. `NOVA_SKIP_API_SIDECAR=1` stays attach-only, and a development desk
   (`electron:dev`) keeps its checkout behaviour. The desk never pulls the
   checkout it runs from.

## Consequences

- The normal morning — the watchdog's backend is up, the desk launches — shows
  no prompt, exactly as before ADR 038.
- A version split is visible (title plus notice) and one click fixes it. A
  click never silently interrupts a recording, a position's watch or an order.
- The desk no longer starts a stranger with separate data on an empty port when
  it knows the operator's checkout.
- A leftover packaged engine of another release on `:8000` is used as it is.
  Reload backend cannot restart it, because it has no checkout scripts. Closing
  its `nova-api.exe` is the operator's step. This is rare, and unchanged from
  before ADR 038.
- A future separate backend service would need its own signed, atomic updater
  and a protocol compatibility policy, not implicit port adoption.

## Atomic startup and immediate checkout restart (2026-10-05, #653)

Every API process takes a non-blocking OS-held lock on a separate, never-unlinked
`api-instance.guard` file in a shared per-user Nova runtime directory before
reading or replacing each checkout's diagnostic JSON
`api-instance.lock`. Windows locks byte zero with `msvcrt.locking`; POSIX uses
`flock`. The open handle lives until process exit; stale or malformed JSON never
allows a second process past a held guard. Same-process acquisition is idempotent.
Legacy PID/orphan checks run only after acquiring the guard, and failed claims
release it. Modern holders retain `api_process_guard`'s independent listen
watch: `acquire_or_exit` starts it before the app boots; a dark holder exits
itself after the startup grace and releases the OS guard. A contender never
kills a process based on metadata while another process holds the guard. A failed metadata write refuses startup and releases the guard.

Once an operator-requested checkout restart has verified the old port is free,
Electron immediately starts that checkout's engine, including when the watchdog
runs. No watchdog query or polling interval delays the launch. Concurrent starts
compete for the OS lock; success still requires a different health identity.

### Shared ownership across checkouts and the bundled engine (#653 follow-up)

The exclusion primitive is one per operator, regardless of checkout, cache,
API bind or packaged-engine location: `%LOCALAPPDATA%/Nova/runtime/` on Windows
(home AppData/Local when that variable is absent), `~/.cache/nova/runtime/`
on POSIX. It must not derive from `NOVA_CACHE_DIR`: a watchdog and an attached
engine can have different roots while both use clientId 17. All origins use the
same OS-held `api-instance.guard`; diagnostic JSON remains cache-local for
existing tools. Production offers no separate guard configuration bypass.
Tests patch the guard path explicitly so independent test sessions stay isolated.

For migration from an older cache-scoped holder, claim also refuses an already
occupied API bind under the shared guard even if this cache has no diagnostic
record. It never kills an unidentified listener. A still-unbound old process
cannot participate in the new exclusion protocol; both startup origins need
the shared-guard version before simultaneous starts are protected.

## A backend behind the desk follows by itself (amendment, 2026-10-13)

Operator: "its okay to say 'restart to update' so the user is able to finish their work, my complaint is about manually restarting the backend after an update", then "instead of saying 'restart backend' after an update, it should already know we need to restart the backend and restart it without us having to click on it".

The desk restart stays the operator's (Restart to update, so they can finish
what they are doing). The backend no longer waits for a click once the desk
runs a newer release than it:

- The installed desk looks every 15 s (`engineSync.follow`,
  `ENGINE_FOLLOW_TICK_MS`) whether the owner's backend runs a release older
  than the desk. If it does, Nova does what "Update backend to vNNN" did --
  the checkout fast-forwards to the **desk's own `vNNN` tag** (never master's
  newest commit, never past the desk), then the backend restarts onto it --
  without a button.
- It reads the restart check first, and again after the pull, right before
  the restart (a fetch can take two minutes). A recording does not hold it (it resumes
  by itself after a few seconds' gap). Anything else does: a position, a
  working order, a bot trade, a stock mode, a history download, the opening
  bell (09:25-09:45 ET), or a backend that cannot say. The backend notice then
  lists what holds it, beside **Update backend now** for an operator who wants
  it anyway (confirmed with the list), and Nova goes as soon as it clears.
- It restarts only onto the desk's exact release, read again right before the
  restart. A checkout already past it (master pulled ahead, here or from an
  IDE) would put the backend ahead of the desk, so that is left to the
  operator.
- One pull or restart at a time: the operator's button, Restart to update's
  pull and the restart by itself wait for each other, so a click during the
  automatic one never pulls beside it or restarts the backend twice.
- Each pair of releases (backend, desk) is tried once. A pull it may not make
  (not a clean master, `backend/requirements.txt` changed), a checkout past the
  desk, or a restart that comes back on the same code leaves **Update backend
  to vNNN** to the operator, with the reason, so it can never loop.
- A backend from another checkout, or a bundled engine, is left as before.
- The operator retired the separate unattended nightly pull of master
  (#616) on 2026-10-13. Keep the existing release updates and automatic
  backend follow to a release the operator already installed.

## The backend restarts during the install (amendment, 2026-10-13, evening)

Operator: "Why doesn't the backend restart during installation? Why are we
waiting for the backend to restart after the frontend works?"

Until now Restart to update brought the checkout to the new release, then left
the restart to the new desk (`engine-follow.json`). So the two ran one after
the other: the installer (about a minute), then a backend restart (about half
a minute) on a desk that was already open, disarming it and dropping its IBKR
lines in front of the operator. The 2026-09-30 reason for that order was that
a failed install with no watchdog would leave no backend. But the next launch
of the desk already starts the owner's backend on an empty port (decision 3),
and a failed install leaves no desk either.

Now, once the "Updating Nova" window is up and right before the installer
runs, the old desk restarts the backend onto the release its checkout was just
brought to (`engineSync.handOffForInstall`): the engine's own stop, then the
checkout's `Start-NovaApi.ps1` in a process of its own, without waiting for it
to answer. The backend comes up while the installer runs; the new desk's launch
waits for it like any engine that is starting.

- Same consent as before: the restart check at the Restart to update click.
- Only onto the checkout's exact release, read again right before the restart.
- A restart that fails there is logged and never holds up the install. The
  promise stays, so the new desk restarts the backend as before when it still
  runs other code.
- A reload asked meanwhile (the header's auto-heal) joins this one instead of
  starting another.
- If the installer itself then fails, the backend runs the new release under
  the old desk, and the backend notice offers **Update desk to vNNN**: the
  same state as a backend ahead of the desk, and rare.
