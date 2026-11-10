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

5. **Serve it on the tunnel**, from an Administrator console (serving a folder needs one on Windows). Use the full path
   of `frontend\dist`:

   ```bash
   tailscale serve --bg --https=443 "C:\path\to\Nova\frontend\dist"
   ```

   ```bash
   tailscale serve --bg --https=8443 http://127.0.0.1:8000
   ```

   `tailscale serve status` shows both. Never use `tailscale funnel`: that one is public.

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

"Round trip" is a read of the order gate, not an order. A real order adds the door's own work (about 10 ms on Paper)
and, on Live, IBKR's answer.

## Looking at the whole desk on the phone

Optional, for looking only. Build with the tunnel's API address, then serve as above:

```bash
npx cross-env VITE_API_BASE_URL=https://<pc-name>:8443 npm run build
```

Everything the desk tries to write from the phone is refused with "Nova is view-only from another device", and its own
lag lock reads the phone's uncorrected clock. Use the link test, not the desk, to judge lag.

## Paper orders from the phone

The phone can send Paper orders from the link-test page: buy, sell, flatten, cancel. Never Live: the order door refuses
a phone order whenever the desk is not on Paper, and the phone cannot move the desk's venue.

1. **Set a phone PIN, once, on the PC.** Six digits, typed at a hidden prompt; only its hash is stored. Use a
   different one from your Live PIN.

   ```bash
   py -3 tools/set_phone_pin.py
   ```

2. **Put the desk on Paper** (the header pill), on the PC.
3. On the phone, on the link-test page with a run started: enter the PIN under **Paper orders**, unlock, then open
   Paper's padlock.
4. Send an order. The page shows the time from your tap to Nova's answer, and Nova's own words when it refuses.

An unlock lasts 8 hours, or until you press Lock, unlock from another phone, or the backend restarts. Five wrong PINs
lock the phone for five minutes. An order tapped while the feed is behind or dropped is refused by the same rule the
desk has (a sell, a flatten and a cancel always go).

## Turn it off

```bash
tailscale serve reset
```

Removing the name from `NOVA_ALLOWED_HOSTS` and reloading the backend closes it on Nova's side too.
