# ADR 043 -- A public demo of the desk: sample data, its backend inside the page

**Status:** Accepted · **Date:** 2026-10-01
**Builds on:** [[005-frontend-feature-slices]] · the sample desk (`?view=sample`, #357, #449, and its network gate) ·
AGENTS.md §8 ("Do not host the trading SPA on the public domain")
**Decided by:** the operator, 2026-10-01 ("I want the demo to be live ... It's just not going to have a data feed, so we
would need to populate it with something ... to show the world the full power of it ... I just care about the interface,
really, with fake data")

## Context

Since 2026-08-31 the public domain serves a static marketing page, and §8 forbids hosting the trading SPA there. The
reason holds: the desk talks to a Nova API on `127.0.0.1:8000`, and a public page that runs the desk could reach a
visitor's own Nova, which places orders.

The sample desk (`?view=sample`) already runs without a backend, but it is a thin shell: its charts say "no candles
here", and Level 2, the plan, the bot and the account pages are missing or empty. The README screenshots show the real
desk instead, driven by a fake backend in a headless browser.

## Decision

1. **A demo build.** `npm run build:demo` builds the real desk with `VITE_NOVA_DEMO=1` and the base path `/demo/`. It
   adds an in-page backend (`frontend/src/demo/`) that answers every API call and every socket with **Nova Marketing
   Sample Data**: one coherent morning (Wednesday 2026-09-30, from 09:41:27 ET). A normal build contains none of it:
   the flag is compiled to `false` and the module is a dynamic import in a dead branch.
2. **No path to a backend.** Before any app module loads, the demo replaces `fetch`, `WebSocket` and
   `navigator.sendBeacon`. The API base is `http://nova-demo.invalid`, a reserved name that never resolves.
   - A request to that origin, to a loopback host on any port, or to an `/api`, `/ws` or `/__nova` path is answered
     in the page and never sent.
   - Any other request that is not a GET is refused in the page.
   - Every socket is an object in the page; none connects to anything.
3. **Nothing is placed or changed.** An order, an arm, a bot level, a stock's mode or a recording is refused with the
   demo's reason. Paper and Sim can be switched to (in memory); Live is refused, because the demo has no broker.
4. **A clock that runs.** The page's clock starts at the sample morning and runs forward. Freshness stamps follow it,
   so nothing reads stale. The open symbol's tape, book and last trade tick in the page around the sample price.
5. **It says what it is.** A strip under the header reads "Live demo · Nova Marketing Sample Data" on every page, with
   a link to the repository. The screen-recording chip is hidden: the demo records nothing.
6. **Hosted at `nova.altaystudio.com/demo/`**, as static files under `site/demo/` in `aaltaay/nova-site`, copied from
   `frontend/dist-demo/` by hand for now.

## Consequences

- §8 keeps its rule and its reason, and names this one exception.
- The demo data follows the wire shapes by hand (`frontend/src/demo/data/`). When a shape changes, a demo panel can go
  stale or empty until the data is updated. The desk's own types do not check it.
- The demo on the site is a copy. It shows the desk as of its last build until someone rebuilds and copies it again.
- Nothing about the trading desk, its gates or its order path changes.
