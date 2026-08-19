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
  Auto log off. Phone 2FA may still be required after Sunday security reset.

Never commit `config.ini`. Add to your global gitignore if needed:

```gitignore
**/.nova/ibc/
```

## Launch

Preferred (after local setup under `%USERPROFILE%\.nova\ibc\`):

```powershell
# Edit credentials once:
notepad $env:USERPROFILE\.nova\ibc\config.ini

# Then:
& "$env:USERPROFILE\.nova\ibc\start_gateway.ps1"
```

Use the **local** `StartGateway.bat` in `.nova\ibc\` (not stock `C:\IBC\StartGateway.bat`).
Stock IBC defaults to `Documents\IBC\config.ini` and an outdated `TWS_MAJOR_VRSN`.
The Nova wrapper sets `CONFIG`, `TWS_MAJOR_VRSN=1045`, `TRADING_MODE=live` (match `.env`;
paper 4002 is the fallback), and `TWOFA_TIMEOUT_ACTION=restart`.

Optional template in-repo: `scripts/start_gateway_ibc.ps1.example`.

## Nova behavior after IBC

1. Wait until API port listens (`4001` live / `4002` paper).
2. Confirm `GET http://127.0.0.1:8000/api/ibkr/status` → `"connected": true`.
3. Run `.\scripts\smoke_check.ps1`.

**2FA:** IBC may fill username/password. IBKR Mobile still requires *you*.
Agents must warn loudly and must not store passwords in the chat or the repo
(see `.cursor/rules/ibkr-gateway-login-warning.mdc`). Paper IBC may use
`AutoRestartTime` (week-long token, often no daily 2FA). A Nova **Live**
click clears that AutoRestart so a live login can prompt the phone.

## Switching Paper ↔ Live from Nova's UI

The Stock View header's **Paper / Live** capsule switches which Gateway **port**
Nova dials (`IBKR_GATEWAY_MODE` -> 4002 paper / 4001 live, persisted to `.env`) and
reconnects. One IBC install is one Gateway window. The switch does **not**
arm live spend:

1. Click Live/Paper in Nova -> confirm -> Nova attaches to that port. If that
   Gateway is already logged in, it is **not** closed and 2FA is **not** asked
   again. If it is not running, Nova stops both 4001/4002 listeners, then IBC
   starts that door. IBC fills username/password. A new live login can show
   IBKR Mobile / SECOND FACTOR.
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
| `live` | 4002 paper only | Follow-Gateway heal → paper (refuse, or timeout/probe when preferred dark) |
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
IBKR Mobile 2FA may still require your phone -- that is the only remaining
human morning step once a Phase D channel is configured.

If the PC is asleep at 03:40, enable wake timers in Windows power settings
or rely on the AtLogon / session-unlock triggers when you unlock.

`AutoRestartTime` in `%USERPROFILE%\.nova\ibc\config.ini` must be `11:45 PM`
(AM/PM). A bare `23:45` is ignored by IBC.

## Related

- `scripts/start_gateway_ibc.ps1.example` -- template launcher (no secrets)
- `scripts/Start-NovaDaily.ps1` / `Install-NovaDailyTask.ps1` -- morning auto-start
- `scripts/Invoke-NovaMorningCheck.ps1` -- pre-open self-check + loud alert
- `scripts/smoke_check.ps1` -- post-login API smoke
- `IBKR_GATEWAY_MODE` / `IBKR_LIVE_PORT` / `IBKR_PAPER_PORT` in `.env`
- `.cursor/rules/ibkr-gateway-login-warning.mdc` -- loud-warn vs bidirectional self-heal
