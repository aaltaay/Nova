# Phone link: set up the tunnel and measure it (ADR 070)

The phone reaches Nova on the PC over a private Tailscale tunnel. Nothing is opened to the internet. In this first step
the phone is **view-only**: the API refuses every write from it.

## What you do once

Installing Tailscale and signing in are yours to do; Nova never does them.

1. **Install Tailscale on the PC and on the phone**, and sign both in to the same account.
2. **In the Tailscale admin console**, turn on MagicDNS and HTTPS certificates. Note the PC's full name there; it looks
   like `your-pc.tailXXXX.ts.net`. Below it is written `<pc-name>`.
3. **Open that name in Nova.** In the desk `.env`:

   ```text
   NOVA_ALLOWED_HOSTS=<pc-name>
   NOVA_CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,https://<pc-name>
   ```

   The CORS list replaces the default, so the two Vite origins stay in it. Then Reload backend.
4. **Build the page** (in `frontend/`):

   ```bash
   npm run build
   ```

5. **Serve it on the tunnel.** Start Nova's own file server for the built page; leave it running:

   ```bash
   py -3 tools/serve_phone_page.py
   ```

   It serves `frontend\dist` on `127.0.0.1:4181` and nothing else. Then point the tunnel at it and at the API:

   ```bash
   tailscale serve --bg --https=443 http://127.0.0.1:4181
   ```

   ```bash
   tailscale serve --bg --https=8443 http://127.0.0.1:8000
   ```

   `tailscale serve status` shows both. Never use `tailscale funnel`: that one is public.

   Do not put `python -m http.server` behind the tunnel instead. The phone's screens load about eighty files at
   once, and behind that server a share of them came back 502 and the page did not start (measured 2026-11-11:
   69 of 240). Serving the folder straight from Tailscale (`tailscale serve --https=443 "C:\...\frontend\dist"`,
   from an Administrator console) also works.

## Check it before measuring

On the phone, with Tailscale on:

- `https://<pc-name>:8443/livez` answers `{"status": "alive", ...}`. A 400 with `HOST_NOT_ALLOWED` means step 3 is
  missing the name, or the backend was not reloaded.
- The desk's diagnostics row "Pages and names the API refused" names any Host or origin it turned away.

## Measure

1. On the desk, open a busy stock in the Trader so its Level 2 and tape lines are already held.
2. On the phone, open `https://<pc-name>/link-test.html`, type that symbol, press **Start**.
3. Let it run a minute on home Wi-Fi. Press **Copy** and keep the text.
4. Turn Wi-Fi off and repeat on cellular. Repeat at the open on a fast mover if you can: that is the hard case.

The page shows the round trip, the phone's clock against the PC's, how old Level 2 and the tape are when they arrive,
and how much traffic the symbol makes. The verdict is green only when 95 in 100 of both the data and the round trips are
under 500 ms, the same limit the order door uses (ADR 045).

For a long run, leave it going ten minutes or more and do what breaks links: switch Wi-Fi to cellular, walk around.
The page keeps the screen on, dials a dropped feed again, and under **Whole run** counts every sample over 500 ms and
every drop with how long the longest lasted. Copy includes it.

"Round trip" is a read of the order gate, not an order. A real order adds the door's own work (about 10 ms on Paper)
and, on Live, IBKR's answer.

## Nova on the phone: the screens

Once the link passes, open `https://<pc-name>/phone.html` on the phone. In Chrome's menu, **Add to Home screen** puts
it on the home screen, full screen; it opens there from then on.

- **Bottom bar:** Scan, Trade, Home, Top 9, Account. Tap a row for the stock's page; tap the blue ticker chip for the
  Trader.
- **The header** says the desk's venue, how fast the PC answers, and the padlock. Tap the venue for Settings.
- **To use the padlock, cancel or send an order,** the phone asks for your PIN first: the same PIN you type on the
  PC. The unlock lasts 8 hours and ends when the page is reloaded. An order tapped while the phone was locked is
  not sent when the PIN opens it: tap again.
- **Nothing scrolls.** A long list has Prev and Next.
- **Trade** shows one stock: its chart, Level 2, the tape and the order ticket. Tap a blue ticker chip to open a
  stock there; the Trade tab reopens the last one.
  - *Quick:* choose the size (100, 500, 1000 or your own number), then one tap is the order. Each button says what
    it sends: buy at market, buy with a limit 5 cents over the Ask, sell half or all at the Ask (it rests), sell
    half or all into the Bid (it fills now).
  - *Custom:* Buy or Sell; Market, Limit or Stop; the price and the shares with the + and - buttons; one send
    button. **Set a stop...** opens it on a sell stop for the shares you hold.
  - *The banner* answers every tap: Sending, Sent (the desk has it), Filled, or a red NOT SENT with the desk's
    reason, which stays until you tap it.
  - *The two dots* at the right are your position in the stock and your working orders. Tap one to see it; press
    and hold to flatten, or to cancel every order, after a warning. Drag a dot to move it.
  - *The grab handle* under the chart trades chart height for Level 2 rows. Tap the chart for the full chart.
  - *When the padlock is locked* the buttons are grey and a tap sends nothing; tap **Locked** to open it. Flatten
    and Cancel all still work.
  - *When Level 2 reaches the phone late* the buys are held and say so. Sells, Flatten and Cancel still go.
- The big chart opens upright from the round icon in the corner of a stock's chart; its sideways button turns it.
- The venue is changed on the PC. The phone sends orders on Paper only.

After a new build (`npm run build`), reload the page on the phone to get it: the file server tells the phone to
ask for the page again every time, and to keep only the files whose names change when their content does.

## Looking at the whole desk on the phone

Optional, for looking only. Build with the tunnel's API address, then serve as above:

```bash
npx cross-env VITE_API_BASE_URL=https://<pc-name>:8443 npm run build
```

Everything the desk tries to write from the phone is refused with "Nova is view-only from another device", and its own
lag lock reads the phone's uncorrected clock. Use the link test, not the desk, to judge lag.

## Paper orders from the phone

The phone sends Paper orders from its Trade screen, and from the link-test page (buy, sell, flatten, cancel). Never
Live: the order door refuses a phone order whenever the desk is not on Paper, and the phone cannot move the desk's
venue.

1. **The PIN is the one you already use on the PC.** Nothing to set up. To give the phone a different PIN
   instead, run this on the PC (six digits, typed at a hidden prompt; only its hash is stored). While it is set
   the phone takes that one and not the PC's:

   ```bash
   py -3 tools/set_phone_pin.py
   ```

2. **Put the desk on Paper** (the header pill), on the PC.
3. On the phone, open **Trade** on a stock and tap a button: the phone asks for the PIN once, then tap the padlock
   (or **Locked**) to open Paper's padlock. On the link-test page with a run started, the same two steps are under
   **Paper orders**.
4. Send an order. The banner says Sent and how long the desk took to answer, and Nova's own words when it refuses.

An unlock lasts 8 hours, or until you press Lock, unlock from another phone, or the backend restarts. Five wrong PINs
lock the phone for five minutes. An order tapped while the feed is behind or dropped is refused by the same rule the
desk has (a sell, a flatten and a cancel always go).

## Turn it off

```bash
tailscale serve reset
```

Removing the name from `NOVA_ALLOWED_HOSTS` and reloading the backend closes it on Nova's side too.
