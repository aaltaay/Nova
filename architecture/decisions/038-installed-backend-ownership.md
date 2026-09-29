# ADR 038: The installed desk owns its packaged backend

**Status:** Accepted (2026-09-29)

## Context

A Windows installer already contains both the Electron desk and a PyInstaller
FastAPI engine.  Startup nevertheless reused any healthy Nova API on port 8000.
That made an updated desk silently attach to an older checkout-owned engine, so
one window could report `desk v1027 · backend v1025` and require a Git pull.
Reloading that process correctly reloaded its own checkout, but could not make a
checkout newer than the files it held.

Silently stopping an external engine is not safe: it can be recording, serving a
trading session, or be supervised by the localhost watchdog.  Silently adopting
it is also not safe because the installed desk and API can have different
contracts.

## Decision

The packaged Windows desk owns a packaged engine of the same release.

* With no API on port 8000, it starts its bundled `nova-api.exe`.
* It may reuse an already-running **packaged** engine only when that engine's
  release equals the desk release.
* A checkout-owned engine, an older/newer packaged engine, or an engine whose
  ownership cannot be proved is never adopted silently.  Startup names what is
  running and asks the operator to retry after stopping it, explicitly use that
  external engine for this session, or exit.
* `NOVA_SKIP_API_SIDECAR=1` remains the explicit attach-only development/ops
  override and does not show the ownership prompt.
* Development Electron keeps its existing checkout behavior.

The installer remains the atomic update unit: desk and packaged API ship in the
same NSIS release. Updates may be discovered and downloaded automatically, but
installation remains operator-triggered so Nova never restarts during a trade or
recording without consent.

## Consequences

Normal installed operation no longer depends on `git pull`, and a version split
cannot happen without an explicit one-session operator choice. Development and
the morning watchdog remain possible, but are visibly external modes. A future
separate backend service would need its own signed, atomic updater and protocol
compatibility policy rather than reintroducing implicit port adoption.
