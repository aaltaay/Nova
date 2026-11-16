# ADR 070 -- The phone reaches the desk over a private tunnel, view-only first

**Status:** Accepted (step 1: measure the link) · **Date:** 2026-11-10
**Amends:** `AGENTS.md` §8 (the app UI was local Vite / Desktop only; a second exception beside ADR 043's demo)
**Builds on:** [[045-orders-refuse-a-stale-view]] (the 500 ms rules the phone must meet) · the request guard
(`backend/request_guard/`, security alerts 2026-10-09) · [[007-centralized-trading-execution]] (one order door)
**Decided by:** the operator, 2026-11-10: "Trade from my phone using Nova... The phone is a thin second screen for the
existing Nova, not a new app." -- data and the trade round trip "both under 500 ms. Over that, it's not usable." --
"Never let me trade on stale data." Offered a tunnel spike first, more mockups first, or both, they chose the spike.

## Context

- Nova runs on one PC. The API binds `127.0.0.1:8000`, the browser desk is Vite on `127.0.0.1:5173`, and nothing is
  reachable from another device. `AGENTS.md` §8 says the trading UI is never hosted off the PC.
- The request guard already refuses any Host name or page origin that is not the desk's own, and `NOVA_ALLOWED_HOSTS` /
  `NOVA_CORS_ALLOWED_ORIGINS` already add a name.
- **Reads have no key.** `X-Nova-Api-Key` guards writes only; a GET or a socket needs none.
- **"Loopback" was two different tests.** The API key rule asks whether the *bind* is loopback; the bot and agent routes
  ask whether the *caller's address* is. A tunnel that runs on this PC forwards from `127.0.0.1` to a loopback bind, so
  it passes both: with no rule of its own, a phone would be the desk.
- **The 500 ms rule exists and assumes one clock.** The order door refuses a new entry that arrives more than 500 ms
  after the tap, or whose Level 2 or quote had been replaced for more than 500 ms at the tap (ADR 045). It compares its
  own clock with the tapping device's (`frontend/src/market_view/viewRegistry.ts`: "Desk and backend run on one machine
  ... one clock"). A phone whose clock runs ahead of the PC's would make a late order look on time.
- Nothing has measured the link. Whether a phone on cellular gets Level 2 and an order round trip under 500 ms is
  unknown, and the phone layout is not worth building until it is.

## Decision

1. **A private tunnel, never a public address.** The phone reaches the PC over a WireGuard tunnel between the
   operator's own devices (Tailscale, with its Serve feature on the PC). No port is opened on the router, the API keeps
   binding `127.0.0.1`, and nothing is published to the internet: Tailscale Funnel, a public domain or a port forward
   stay forbidden. The tunnel serves the built page on port 443 and the API, whole, on port 8443 of the PC's tunnel
   name, both over HTTPS.
2. **The tunnel's name is opened by hand.** The PC's tunnel name goes in `NOVA_ALLOWED_HOSTS` and its `https://` origin
   in `NOVA_CORS_ALLOWED_ORIGINS`. Without both, the guard refuses the phone as it refuses any other name.
3. **Another device is told apart from this PC.** A request is from another device when its Host is not a loopback name
   or the bind host, or when it carries a forwarder's header (`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`,
   `Tailscale-User-Login`). The second test is what catches a tunnel that rewrites the Host. The desk, the bots and the
   tools send none of those headers.
4. **Step 1: another device is view-only, and the API enforces it.** The request guard refuses every HTTP write
   (`POST`, `PUT`, `PATCH`, `DELETE`) from another device with 403 `REMOTE_VIEW_ONLY`, before the API key is read, in
   words the screen can show. A key on the phone changes nothing. This holds until decision 6's work lands.
5. **The bot and agent routes stay this PC's alone.** `/bot`, `/api/bot`, `/ws/bot` and `/api/agent` refuse another
   device by any method or socket (403 `REMOTE_LOCAL_ONLY`), because their own check reads the caller's address.
6. **No order from the phone until three things are built**, each its own change with its own approval:
   - the phone corrects its clock against the PC's, so the view an order carries and the door's 500 ms rules read one
     clock again;
   - reads from another device carry proof of who is asking (the tunnel proves the device; nothing yet proves the page);
   - the operator approves the phone's order pad from a mockup.
   Then decision 4 narrows to what the operator chose. Live keeps its PIN, the arm latch and every gate of Invariant #7.
7. **Measure before building.** `link-test.html` is a light page in the same build. For one symbol it opens the desk's
   own Level 2 and Time & Sales sockets and asks the order gate's read route once a second. It shows the round trip, the
   phone's clock against the PC's, how old each frame is on arrival (on the corrected clock), frames and bytes a
   second, and one verdict against 500 ms. It holds no key and sends no order.
8. **The phone is a second screen, not a second system.** Same sockets, same routes, same order door, same build. A
   Level 2 feed thinned for the phone is decided only if the measurement says the phone cannot keep up.

## Why this way

- **Tunnel over a LAN bind or a public host:** the operator trades away from home, so the LAN is not enough; a public
  host puts the order door on the internet behind one key.
- **Serve on the PC over binding the API to the tunnel's address:** the API stays on loopback, HTTPS comes with a real
  certificate (a phone needs a secure page for sockets and to install the page later), and the bind rule is untouched.
  The cost is the caller-address problem in Context, which decisions 3 to 5 close.
- **View-only enforced in the guard, not left to "don't type the key":** the operator's rule is "never let me trade on
  stale data", and until the clock is corrected the door cannot judge a phone's order. A rule that depends on what was
  typed into a phone is not a rule.
- **A separate test page over a readout on the desk:** it loads in a second on cellular, changes nothing the operator
  trades with, and needs no design approval. The desk's own latency readout is part of the phone layout, drawn first.

## Rejected

- **Port forwarding, a public domain, Tailscale Funnel:** public.
- **`NOVA_ALLOWED_HOSTS=*` to get the phone in quickly:** turns off the DNS-rebinding guard for every page.
- **Building the phone layout first:** if cellular cannot hold 500 ms, the layout is wasted.
- **A second backend or a relay in the cloud:** a new system; the operator asked for none.

## Consequences

- The PC and the home internet are a single point of failure for a phone trade. The link test and, later, the phone's
  lock can detect a bad link and hold entries; they cannot fix it. A position opened from the desk still closes from
  the desk, and a broker-side stop does not depend on the phone.
- Opening a symbol's Level 2 or tape from the phone uses the same IBKR lines as the desk (3 books, the tape cap). Test
  with a symbol the desk already shows.
- The unchanged desk can be loaded on the phone to look at (build with `VITE_API_BASE_URL` set to the tunnel's API
  address). Everything it writes is refused, including its own error and lock reports, and its lock arithmetic reads
  the phone's uncorrected clock: it is for looking, not for judging lag. The link test is the judge.
- Whether Tailscale Serve keeps the Host header was not measured on this PC (Tailscale is not installed yet). Decision 3
  holds either way; `docs/phone-link.md` has the check.
- A test's `TestClient` Host (`testserver`) stands for this PC (`backend/tests/conftest.py`), so existing tests' writes
  are not refused.

## Amendment 2026-11-10 -- the phone sends Paper orders, after its own PIN

**Decided by:** the operator, the same day, after the link passed on cellular (round trip p95 102 ms, Level 2 age p95
159 ms) and recovered from two forced drops: "let's run a real end to end test", "all of it, use paper trading". Asked
how Nova should know an order is theirs, they chose a phone PIN; asked what the phone may send, "all major operations
using paper money".

Decision 4 narrows, as decision 6 said it would:

9. **One door for another device's writes: `/api/phone`.** Every other write from another device is still refused
   `REMOTE_VIEW_ONLY`, and decision 5 stands. The phone's routes are opened by the phone PIN, not by
   `X-Nova-Api-Key`: the desk's key never leaves the PC.
10. **A phone PIN, set on the PC.** `py -3 tools/set_phone_pin.py` stores its hash (`NOVA_PHONE_PIN_HASH`, the Live
    PIN's form). A correct PIN buys one session, held in memory: it ends after 8 hours, on Lock, on a newer unlock, or
    when the backend restarts. Five wrong PINs lock the phone for five minutes, counted apart from the Live PIN.
11. **Paper only, held by the order door.** A phone order names Paper as its venue and goes through the desk's own
    handlers, so the door refuses it `VENUE_CHANGED` if the desk is anywhere else when it is sent; the phone's route
    says so first in plain words (`PHONE_NOT_PAPER`). The phone cannot move the desk's venue, so it can never reach
    Live. It sends a buy, a sell, a flatten and a cancel, and works Paper's padlock: no short entry, no bracket, no
    setting.
12. **Same gates as the desk.** The arm latch, the stale-view rules (ADR 045), the order size limit (ADR 064) and the
    loss limit all judge a phone order, because it is the same command. The order's timing and its view are required
    fields: without them the door would not judge lag at all.
13. **One clock.** The phone stamps its tap on the PC's clock, using the offset the link test measures, so the door's
    500 ms rules read one clock again (decision 6's first item). The view carries the Level 2 version the phone last
    received, so the door checks what the phone was shown, not only when it tapped.

What decision 6 still holds back: the phone's order pad. These orders are sent from the link-test page, a measuring
tool with plain buttons; the pad the operator trades from is still drawn and approved first. Reads from another device
still carry no proof of the page; only writes do (the PIN's session).

## Amendment 2026-11-11 -- the phone's screens, drawn first and built on the desk's own data

**Decided by:** the operator, 2026-11-11, after a day of mockups: "I think I'm good to freeze the mobile ui and ready
to implement." -- "I want the desk to be the center of the logic ... It's the same logic as the desk. It's just the UI
is shaped differently." -- "No scrolls allowed." Asked for the order, they confirmed Paper, then Sim, then Live, each
tried on the phone before the next.

Decision 6's last item is met for the screens: the operator approved them from mockups (kept on the operator's disk;
the build is judged against them). What follows is how they are built.

14. **A second page, `phone.html`, in the same build.** It is a React page of its own (`frontend/src/phone/`), not
    the desk shell squeezed onto a phone. Like the link test it works out the API's address from the page's own
    name and holds no API key. It is left out of the demo build for the same reason the link test is.
15. **The desk's providers and hooks, not copies.** The phone mounts the desk's account, settings and scanner
    providers and reads every figure through the hook the desk reads it with: the scanner feed and its chips, the
    Catalyst call, the Top 9 boards and their rank marks, the market board's day read, the practice ledger and its
    two books, the loss limit, the ticker stream, the chart. Where a desk function drew for a desk-sized box, it
    gained a parameter with the desk's value as its default (the Top 9 chart's margins and minutes). The phone
    writes no rule about a rank, a mark, a catalyst, a fill or a limit.
16. **A workspace of its own, with no Trader tabs.** The desk's workspace provider keeps the Trader's tabs and
    tells the bots which Level 2 lines they hold. A second, empty copy of that list from a phone page opened on
    the PC would overwrite the desk's. The phone's workspace reads the desk's config and Gateway status the same
    way and holds no tabs; it posts nothing.
17. **No screen scrolls.** Each screen is drawn for 360 x 720 (the big chart also for 740 x 320, on its side: it
    opens upright, operator 2026-11-12, and a button turns it) and fills anything larger. On anything smaller the whole page shrinks by one factor. A list longer than its box pages.
18. **Every tap is answered.** A banner says Sending, then what the desk answered; a refusal is the desk's own
    words in red and stays until tapped. A control that cannot act yet is disabled and says why when pressed.
19. **Built in steps, each tried on the phone.** Step 1 is every screen but Trade: they read, and they work the
    two locks and cancel a working order, all through the door that already exists. The Trade screen is step 2,
    with the door's additions decided then. Sim, then Live, follow; Live needs decision 11 rewritten first, by
    the operator, and until then the phone cannot move the venue or send anything but Paper.

What step 1 does not do, and says so on the control: change the venue, star a stock, draw on the chart (each is a
write the door has no route for), the 10-second chart (it follows the tape, opened with the Trade screen), and four
of the Scan lists (HOD Momo, Running Up, Volume boost, Setups).

**Level 1 lines.** A screen declares the scanner list it shows, as a desk tab does, so its prices move. The backend
serves the union of every window's lists inside one budget, so a phone on a list the desk is not showing shares that
budget with the desk's.

## Amendment 2026-11-12 -- the Trade screen, on Paper

The operator tried step 1 on the phone ("It's loading and I'm able to see the charts! I think we are good to
continue!"). Step 2 is the Trade screen of the frozen design, on Paper.

20. **The phone's ticket is the desk's ticket code.** Every one-tap button is one of the desk's own actions
    (`hotkeys/runNovaAction`: buy at market, buy with a limit over the Ask, sell a share of the long at the Ask or
    into the Bid, cancel and flatten, cancel every order), run with the numbers on the button. The Custom ticket
    sends through the desk's `placeIbkrOrder`. So the gate, the price read from Level 2, the size read from the
    position and the order body are one piece of code on the desk and on the phone. The phone writes the words on
    a button; it never works out the price an order goes out at.
21. **One seam for the door, one for the clock.** The desk's ticket code posts to the page's order door
    (`ibkr/orderDoor`): `/api/ibkr` on the desk, `/api/phone` with the PIN's session on the phone. Everything that
    compares a moment with the backend's reads the PC's clock (`utils/deskClock`): the page's own clock on the
    desk, plus the offset the phone's heartbeat measures on the phone. Without it a phone would judge a Level 2
    frame's lateness, and stamp an order, on a clock the backend does not share.
22. **The door takes what the ticket sends, and trusts none of it.** `POST /api/phone/order` gains `STP` with
    `stop_price`, and `reference_price`; `DELETE /api/phone/orders` gains `all_symbols=true`. The desk's order
    body also carries a venue, a time in force and, on the desk, short and bracket fields: the phone's route reads
    past them. Every phone order is Paper, DAY, never a short entry, never a bracket.
23. **The book and the tape are the desk's sockets** (`useIbkrDepth`, `useIbkrTape`), so the desk's view registry
    judges whether the phone's view is live, in the desk's words, and the order carries the book version the phone
    drew. A view that is behind holds the buys and says so on them; a sell, a flatten and a cancel still go. Level 2
    is opened only while the Trade screen is up: it takes one of the desk's three books.
24. **A locked padlock sends nothing.** The buttons are greyed under "Locked", and a tap is answered NOT SENT
    with nothing sent; the banner opens the padlock. Flatten and Cancel all are never held by it, as on the desk.
25. **A flatten and a cancel of everything sit behind a warning that fills the screen**, from the two dots (tap,
    or press and hold) and from the ticket. One tap sends an order; one tap never empties a position by accident.
26. **Still Paper only.** Off Paper the ticket is drawn, locked, and says the phone trades Paper only.
27. **One PIN** (operator, 2026-11-12, on meeting the phone's PIN sheet: "Just have the same one as the computer
    one"). The phone unlocks with the desk's own PIN, the one typed on the PC (`NOVA_LIVE_ARM_PIN_HASH`). This
    replaces the 2026-11-10 rule that the phone has a PIN of its own and that it should differ. A separate phone
    PIN can still be set (`tools/set_phone_pin.py`); while one is, the phone takes that one and not the desk's.
    What the PIN opens does not change: the phone's Paper door, for 8 hours. It arms nothing; Live is armed only
    on the PC. Wrong PINs typed on the phone are counted on the phone, apart from those typed on the PC.
28. **An order tapped on a locked phone is not sent when the PIN opens it.** The bid, the ask and the position
    move while a PIN is typed, and a one-tap order sends what its button says at the tap. The banner says the
    phone is unlocked and to tap again. (The padlock and a cancel of one order, which carry no price, still go
    after the PIN.)
29. **A buy that covers a short is never held for lag**, on the ticket as at the door: the desk's own rule
    (`orderCloses`). The phone opens no short; one opened on the desk can be covered from the phone.

Not in step 2, and listed in #1309: the Trade screen on its side (the frozen landscape board is a Live board and
comes with Live), starring and drawing from the phone, the venue switch, the four other Scan lists.

## Amendment 2026-11-13 -- the venue from the phone, Sim, Live to look at, and the Level 2 marks

**Decided by:** the operator, 2026-11-13, from mockups (`F:\Nova\design\phone-l2-venue\` v1 to v3): "the phone version
is not able to switch between paper, sim, and live"; "I want level 2 upgrades to be on the phone as well, so we can
identify big orders, big wall, hidden sellers, and the depth". They picked the Level 2 option with the depth chart
("I really like C because it includes the depth, but maybe when we click on the depth, it opens that screen"), a
dropdown on the venue pill ("Instead of opening a whole page, why don't we just have a dropdown"), and, asked "Build it
with Live look-only and Sim following the desk's replay?", answered "Yes, build it". Decision 11 is rewritten by them
here, as decision 19 required.

30. **The phone moves the desk's venue.** There is one venue, the desk's: a switch on the phone switches the PC too.
    `POST /api/phone/venue` hands the switch to the desk's own route (`POST /api/desk/venue`), and on Live it also
    asks for the live Gateway as the desk's pill does. So it does what a switch on the desk does: it never arms
    (it disarms), the Bot's dial follows the venue, and Nova's working entries on the venue left are cancelled
    first (ADR 042 F). The pill on every screen opens a small menu; one tap on a row switches, as the desk's pill
    does on one click.
31. **The menu says what the switch would cancel before the tap.** `GET /api/phone/venue/effects` reads what the
    desk would lose by leaving its venue, in the desk's own checks: Nova's entries still waiting to fill there
    (`stock_mode.leave`), the Bot when it is on and a trade it holds open (in a switch's words, never a restart's),
    the padlock when it is open. A check that cannot be read is said as
    unknown, never as nothing. The operator's own orders and positions stay on the venue left, and the menu says so.
32. **Orders on Paper and on Sim; Live is look only.** Decision 11 now reads: a phone order names the desk's venue
    when it is Paper or Sim, and goes through the desk's own handlers, so the door refuses it `VENUE_CHANGED` if the
    desk has moved by the time it is sent. On Live the phone shows the account, the positions, the orders and the
    market, and sends nothing: the route says so first (`PHONE_LIVE_LOOK_ONLY`), and the padlock opens from the phone
    on Paper and Sim only. Live is still armed only on the PC, with its PIN.
33. **Sim follows the desk's replay.** The Sim's playhead is the desk's: pause, play, and a step back or forward of
    the desk strip's one minute go through `POST /api/phone/sim/clock` to the desk's own `POST /api/sim/clock`. What
    is loaded (the day, the stock) is chosen on the PC. The Trade screen shows a Sim stock as the desk's Trader does
    with the same sockets: at the live edge, and on a Session Record of that stock (its quote is the recording's,
    `captureQuoteDetail`). Every other Sim state -- nothing loaded, another stock loaded, loading, failed, and a
    Massive-file window, which the desk draws with its own replay panes -- shows the desk's words in place of the
    book and tape, and its ticket sends nothing. The Massive-file window is listed in #1309.
34. **The Level 2 marks are the desk's.** The phone's book draws the book watcher's verdicts with the desk's own
    functions (`ibkr/bookWatch`, `bookWatchHidden`, `bookWatchBig`): a big seller or buyer's block and its banner, a
    hidden seller or buyer, what was pulled. The depth chart is the desk's (`Level2DepthChart`), drawn under the
    rows while ten rows still fit beside it; a tap opens a page of its own (`#/book/SYM`) with the chart large and
    every mark spelled out. Nothing is worked out on the phone, and nothing there is a buy or sell signal. A switch
    in Settings turns the marks and the chart off, kept on the phone.

## Amendment 2026-11-14 -- the desk keeps the phone page built and served

**Decided by:** the operator, 2026-11-14, after a merged phone change sat on the PC unbuilt and the page server was
found stopped: "It needs to get reloaded as a part of the installation. Automatically", and, shown the plan
(rebuild after every release, keep the server running, say so on the desk), "Yes, build it".

35. **The installed desk rebuilds the phone page when its checkout moves.** Once a minute the desk asks the owner's
    checkout (ADR 038: the checkout its backend runs from) whether the phone page is that checkout's code
    (`tools/phone_page.py check`). When it is not -- a release pulled the checkout forward, at Restart to update or
    by the backend following the desk -- the desk runs `tools/phone_page.py update` there, below normal priority so
    the trading path keeps the PC first. Never while the desk is pulling or restarting the backend. A build that
    fails leaves the phone the page it had; the desk tries again after 30 minutes, or at once when the checkout
    moves again. Every outcome goes to `update.log`.
36. **The installed desk keeps the page server running.** Once a minute the desk asks `127.0.0.1:4181` for the
    page; when nothing answers it starts `tools/serve_phone_page.py` from the owner's checkout, with no window, in
    a process of its own that outlives the desk (as the backend does). Nothing else changes: the server listens on
    loopback only and serves the built folder, and Tailscale is still the only way in (decisions 1-4). A server
    already answering is left alone. `NOVA_PHONE_PAGE=0` turns both off.
37. **The desk says so only when the phone is behind.** The update view carries `phone_page`; a strip like the
    backend notice shows only while the page could not be rebuilt or the server could not be started, in plain
    words, and goes away by itself once it is fixed. A dev desk (run from a checkout) does neither.

## Rules and maps

- Shapes: `architecture/schema/desk-ops.md`, "Who may reach the API" (another device) and "The phone link test".
- Setup and the measurement: `docs/phone-link.md`.
- The desk keeping the page built and served: `frontend/electron/phonePageKeeper.mjs`, the strip
  `frontend/src/desktop_update/PhonePageNotice.tsx`; shape `architecture/schema/desk-ops.md`, "Release notes and the
  update notice" (`phone_page`).
- Code: `backend/request_guard/` (`policy.remote_refusal`, `middleware`, `constants_request_guard.py`);
  `frontend/link-test.html`, `frontend/src/phone_link/`; the screens: `frontend/phone.html`, `frontend/src/phone/`
  (shapes: `architecture/schema/desk-ops.md`, "Nova on the phone: the screens").
- The phone's door: `architecture/schema/execution.md`, "Paper and Sim orders from the phone"; `backend/phone/`,
  `tools/set_phone_pin.py`.
- The venue menu and the Sim strip: `frontend/src/phone/VenueMenu.tsx`, `frontend/src/phone/trade/SimStrip.tsx`;
  the Level 2 marks and the read page: `frontend/src/phone/trade/BookMarks.tsx`,
  `frontend/src/phone/screens/BookScreen.tsx`.
- The Trade screen: `frontend/src/phone/screens/TradeScreen.tsx`, `frontend/src/phone/trade/`; the two seams
  `frontend/src/ibkr/orderDoor.ts` and `frontend/src/utils/deskClock.ts`.
