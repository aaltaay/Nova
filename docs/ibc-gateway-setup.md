# IBC (IB Controller) — local Gateway auto-login

IBC can type username/password into IB Gateway so Nova does not sit on an empty
scanner after a reboot. **Credentials never belong in git.**

## Prerequisites

1. Install [IBC](https://github.com/IbcAlpha/IBC/releases) somewhere local, e.g.
   `C:\IBC\`.
2. Install IB Gateway under `C:\Jts\ibgateway\<version>\` (Nova defaults to `1045`).
3. Create a secrets directory **outside the repo**:

```text
%USERPROFILE%\.nova\ibc\
  config.ini          # IBC config (Login, Password, TradingMode, …)
  start_gateway.ps1   # optional local launcher (copy from scripts/start_gateway_ibc.ps1.example)
```

## Minimal `config.ini` keys

Use IBC’s sample config as a base. Set at least:

- `IbLoginId` / `IbPassword` — IBC types these into Gateway (local file only)
- `IbLoginIdLive` / `IbLoginIdPaper` — Nova copies the matching one onto `IbLoginId` on a Paper/Live click. Live and paper are different IBKR usernames.
- `TradingMode=live` or `paper` — must match `IBKR_GATEWAY_MODE` in Nova `.env`
- `IbDir` — path to the Gateway install folder
- `AcceptIncomingConnectionAction=accept` (or prompt -- your choice)
- `AutoRestartTime=11:45 PM` -- must be `HH:MM AM/PM` (a bare `23:45` is
  ignored). IBC sets Gateway **Auto restart** (week-long token path), not
  Auto log off, for **both** Live and Paper. Phone 2FA is still required
  after IBKR's own weekly forced re-auth **and after anything that ends the
  Gateway process** -- see "What the saved login survives" below.
- `ReloginAfterSecondFactorAuthenticationTimeout=no` -- an unanswered 2FA
  prompt sits inert instead of IBC auto-retrying (that retry loop hit
  IBKR's own login rate limit twice on 2026-08-20). Use Nova's "Start fresh
  login" CTA to restart the login on purpose.

Never commit `config.ini`. Add to your global gitignore if needed:

```gitignore
**/.nova/ibc/
```

## What the saved login survives

The week-long token is not a file you can keep. Gateway writes an
`autorestart` marker only while it restarts **itself** at `AutoRestartTime`,
and the relaunched Gateway consumes it at once; otherwise the login lives only
inside the running process. So:

| Event | Phone login? |
|---|---|
| Gateway's own 11:45 PM restart | No -- IBC logs `autorestart file found ...: authentication will not be required` |
| IBKR's weekly re-auth (weekend) | Yes |
| **PC restart** (Windows Update, the Start menu, a power cut) | **Yes** |
| Gateway closed, crashed, or killed | Yes |
| Nova's "Start fresh login" | Yes (on purpose) |

Every one of those shows `autorestart file not found: full authentication will
be required` in the IBC log. Nova now says which it was:
`py -3 tools/premarket_verify.py relogin` prints one line (a Windows restart,
who asked for it and when you next signed in -- or a fresh Gateway start), the
morning scripts log it as `WHY:` / `why:`, and `/api/diagnostics` puts it at
the front of the "IBC login / 2FA" row while a prompt is open.

On 2026-09-23 Windows Update restarted the desk at 02:29 ET to install an
optional preview update. The 11:45 PM restart had worked; the reboot ended it.
To keep Windows from doing that, see `docs/live-desk-sync.md`, "Keep Windows
from restarting the desk".

## Open live / Open paper from Nova

Those buttons start IBC (`%USERPROFILE%\.nova\ibc\start_gateway.ps1`) after
copying `IbLoginIdLive` / `IbLoginIdPaper` onto `IbLoginId`. IBC types
username/password into Gateway. They do **not** start raw `ibgateway.exe` --
that leaves the login form empty and looks like a no-op. If `config.ini` or
the launcher is missing, Nova shows the error instead of opening an empty
login. IBKR Mobile 2FA still needs you.

## Launch

Preferred (after local setup under `%USERPROFILE%\.nova\ibc\`):

```powershell
# Edit credentials once:
notepad $env:USERPROFILE\.nova\ibc\config.ini

# Then:
& "$env:USERPROFILE\.nova\ibc\start_gateway.ps1"
```

Use the **local** `StartGateway.bat` in `.nova\ibc\` (not stock `C:\IBC\StartGateway.bat`).

**IBC log names on Windows 11.** IBC names its log after the weekday it reads
from `wmic` (`C:\IBC\scripts\getDayOfWeek.bat`), and Windows 11 no longer
ships `wmic`. The name became `IBC-3.24.1_GATEWAY-1045_.txt`, and each cold
start deleted it, so no login history outlived the day. IBC keeps an inherited
`DAYOFWEEK` when `wmic` prints nothing, so both Nova launchers
(`Start-NovaDaily.ps1` and `POST /api/ibkr/launch-gateway`) set it; the logs
are `..._MONDAY.txt` ... `..._SUNDAY.txt` again. A Gateway you start by hand
outside Nova still writes `_.txt`.
Stock IBC defaults to `Documents\IBC\config.ini` and an outdated `TWS_MAJOR_VRSN`.
The Nova wrapper sets `CONFIG`, `TWS_MAJOR_VRSN=1045`, `TRADING_MODE=live` (match `.env`;
the paper Gateway on 4002 is legacy, by hand only -- ADR 020), and `TWOFA_TIMEOUT_ACTION=restart`.

Optional template in-repo: `scripts/start_gateway_ibc.ps1.example`.

## Nova behavior after IBC

1. Wait until API port listens (`4001` live / `4002` paper).
2. Confirm `GET http://127.0.0.1:8000/api/ibkr/status` → `"connected": true`.
3. Run `.\scripts\smoke_check.ps1`.

**2FA:** IBC may fill username/password. IBKR Mobile still requires *you*.
Agents must warn loudly and must not store passwords in the chat or the repo
(see `.cursor/rules/ibkr-gateway-login-warning.mdc`). Both Live and Paper IBC
use `AutoRestartTime` (week-long token, no daily cold 2FA) -- see
PROBLEM_LOG 2026-08-25: a live 2FA prompt approved more than
`SecondFactorAuthenticationTimeout` (180s) after Log In is silently
discarded by IBC and re-tried, and Nova's nightly logoff used to guarantee
that window was missed every morning. A routine door launch/attach never
clears the `jts.ini` `Restart=OK` token that makes this possible. Only the
explicit "Start fresh login" recovery (`force_fresh_login=true` on
`POST /api/ibkr/launch-gateway`, offered by the UI when
`GET /api/ibkr/status` reports `second_factor_stale: true`) clears it and
forces a genuinely new login/2FA. Set local `config.ini`
`ReloginAfterSecondFactorAuthenticationTimeout=no` so an unattended stale
prompt sits inert instead of retry-looping into IBKR's own login rate limit
(it hit that limit twice on 2026-08-20).

## Switching Paper ↔ Live from Nova's UI

The Stock View header's **Paper / Live** capsule switches which Gateway **port**
Nova dials (`IBKR_GATEWAY_MODE` -> 4002 paper / 4001 live, persisted to `.env`) and
reconnects. One IBC install is one Gateway window. The switch does **not**
arm live spend:

1. Click Live/Paper in Nova -> confirm -> Nova attaches to that port. If that
   Gateway is already logged in, it is **not** closed and 2FA is **not** asked
   again. If it is not running, Nova stops both 4001/4002 listeners, then IBC
   starts that door on its existing week-long `AutoRestartTime` token -- no
   2FA in the common case. IBKR's own mandatory weekly re-auth (or an
   explicit "Start fresh login") is what shows IBKR Mobile / SECOND FACTOR.
2. One Gateway process is still one IB account. Fast flipping without 2FA
   only works when the target port is already listening. A second IBC +
   `IbDir` would be needed to keep both logged in at once.
3. If the live port answers but the logged-in account is actually paper
   (`DU…`/`DF…`), Nova disconnects and refuses rather than pretending Live.
4. Live spend (`IBKR_LIVE_TRADING_CONFIRMED`) is a **separate** key — the switch
   never sets it. Orders stay `locked_live_unconfirmed` until you arm it in `.env`.

See `backend/ibkr/client.py::request_gateway_mode` and
`POST /api/ibkr/gateway-mode`.

## Gateway green ≠ Nova connected

IB Gateway can show farms ON / “API connected” while Nova stays **Disconnected**
when the wrong local API port is listening:

| Nova `IBKR_GATEWAY_MODE` | Listening port | Result |
|---|---|---|
| `live` | 4002 paper only | No heal by default -- the paper Gateway is legacy (read-only beside a live login, no tape; ADR 020). Stay disconnected, log into live. `IBKR_PAPER_GATEWAY_FALLBACK=true` opts back in. |
| `paper` | 4001 live only | Follow-Gateway heal → live (refuse, or timeout/probe when preferred dark) |
| either | preferred still listening, connect times out | No heal (wedged / Error 326) — auth backoff |
| either | both down | Stay disconnected — loud-warn login blocker |

Account kind must match the mode being established after heal. Spend gates
(`IBKR_ORDERS_ENABLED` / `IBKR_LIVE_TRADING_CONFIRMED`) are never auto-unlocked.
Healed mode is persisted to `.env` so the next dial matches today's Gateway.

`GET /api/ibkr/status` exposes `preferred_port`, `preferred_port_reachable`,
`alternate_port_reachable`, and `disconnect_hint` (e.g.
`paper_port_refused_live_listening`) while reconnect / heal is in flight.

After pulling a build that adds `POST /api/ibkr/gateway-mode`, **restart the
Nova API** (stale uvicorn returns 404; the capsule then says “Restart Nova API”).
Smoke: open `http://127.0.0.1:8000/openapi.json` and confirm `/api/ibkr/gateway-mode`.

## Daily auto-start (pre-04:00 ET)

Gappers only hydrate 04:00-09:30 ET (ADR 008). Default `Install-NovaDailyTask.ps1`
registers:

- **03:40** local -- `Start-NovaDaily.ps1` (Gateway + API + UI)
- **03:55** local -- `Invoke-NovaMorningCheck.ps1` (ports, health, IBKR session,
  gappers `feed_error`/`table_state`, loop lag). A failed leg POSTs
  `/api/alerts/system-event` (Discord/Telegram if configured). If the API is
  down it falls back to a direct Discord/webhook POST from `alerts_channels.json`.
- **06:00** local -- backstop start
- AtLogon + session unlock -- wake-from-sleep backstop

```powershell
# Register all of the above (machine should be on Eastern Time)
.\scripts\Install-NovaDailyTask.ps1

# Or only 6am / only logon:
.\scripts\Install-NovaDailyTask.ps1 -Trigger Daily -AtTime 06:00
.\scripts\Install-NovaDailyTask.ps1 -Trigger AtLogon

# Run once now (no scheduler):
.\scripts\Start-NovaDaily.ps1
.\scripts\Invoke-NovaMorningCheck.ps1
# or double-click: Start Nova Daily.bat

# Remove both NovaDailyStart and NovaMorningCheck:
.\scripts\Install-NovaDailyTask.ps1 -Unregister
```

`Start-NovaDaily.ps1` is idempotent (skips healthy API/UI/Gateway). Logs:
`backend/logs/daily-start.log` and `backend/logs/morning-check.log`.
With the week-long `AutoRestartTime` token on both doors, a routine 03:40
start should NOT need IBKR Mobile 2FA most mornings -- only IBKR's own
mandatory weekly re-auth does, **provided the Gateway ran all night**. A PC
restart overnight costs a phone login (see "What the saved login survives"). If the prompt sits unanswered past 180s, it
goes stale (see PROBLEM_LOG 2026-08-25); use Nova's "Start fresh login" CTA
rather than approving a dead prompt.

If the PC is asleep at 03:40, enable wake timers in Windows power settings
or rely on the AtLogon / session-unlock triggers when you unlock.

The tasks use the Interactive logon type: they run only while you are signed
in to Windows. After a restart, Windows waits at the sign-in screen and
**nothing runs** -- no 03:40 start, no 03:55 check, no alert -- until someone
signs in. (The Gateway is a desktop window, so running the tasks without a
session would not help; and it would still need your phone after a restart.)

`AutoRestartTime` in `%USERPROFILE%\.nova\ibc\config.ini` must be `11:45 PM`
(AM/PM). A bare `23:45` is ignored by IBC.

## Related

- `scripts/start_gateway_ibc.ps1.example` -- template launcher (no secrets)
- `scripts/Start-NovaDaily.ps1` / `Install-NovaDailyTask.ps1` -- morning auto-start
- `scripts/Invoke-NovaMorningCheck.ps1` -- pre-open self-check + loud alert
- `scripts/smoke_check.ps1` -- post-login API smoke
- `tools/premarket_verify.py` -- #14 evidence; `relogin` says why the Gateway last needed your phone
- `IBKR_GATEWAY_MODE` / `IBKR_LIVE_PORT` / `IBKR_PAPER_PORT` in `.env`
- `.cursor/rules/ibkr-gateway-login-warning.mdc` -- loud-warn vs bidirectional self-heal
