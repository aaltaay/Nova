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

- `IbLoginId` / `IbPassword` — your IBKR credentials (local file only)
- `TradingMode=live` or `paper` — must match `IBKR_GATEWAY_MODE` in Nova `.env`
- `IbDir` — path to the Gateway install folder
- `AcceptIncomingConnectionAction=accept` (or prompt — your choice)

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
The Nova wrapper sets `CONFIG`, `TWS_MAJOR_VRSN=1045`, `TRADING_MODE=paper` (match `.env`),
and `TWOFA_TIMEOUT_ACTION=restart`.

Optional template in-repo: `scripts/start_gateway_ibc.ps1.example`.

## Nova behavior after IBC

1. Wait until API port listens (`4001` live / `4002` paper).
2. Confirm `GET http://127.0.0.1:8000/api/ibkr/status` → `"connected": true`.
3. Run `.\scripts\smoke_check.ps1`.

**2FA:** IBKR Mobile may still require approval. Agents must warn loudly and must
not store passwords in the chat or the repo (see
`.cursor/rules/ibkr-gateway-login-warning.mdc`).

## Switching Paper ↔ Live from Nova's UI

The Stock View header's **Paper / Live** capsule switches which Gateway **port**
Nova dials (`IBKR_GATEWAY_MODE` → 4002 paper / 4001 live, persisted to `.env`) and
reconnects. It does **not** log you into Gateway and does **not** arm live spend:

1. **You** must already have IB Gateway running and logged into the account that
   matches the mode you're switching to, with the API enabled on that port —
   IBC above, or manual login. Nova never types credentials.
2. Click Live/Paper in Nova → confirm → Nova persists the mode and reconnects.
   If the target port refuses or times out, the capsule shows the error inline
   (e.g. "start IB Gateway logged into the live account…") instead of quietly
   reappearing as Paper.
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
| `live` | 4002 paper only | Self-heal → paper (refuse only; never on timeout) |
| `paper` | 4001 live only | Self-heal → live (refuse only; never on timeout) |
| either | both down | Stay disconnected — loud-warn login blocker |

Account kind must match the mode being established after heal. Spend gates
(`IBKR_ORDERS_ENABLED` / `IBKR_LIVE_TRADING_CONFIRMED`) are never auto-unlocked.

`GET /api/ibkr/status` exposes `preferred_port`, `preferred_port_reachable`,
`alternate_port_reachable`, and `disconnect_hint` (e.g.
`paper_port_refused_live_listening`) while reconnect / heal is in flight.

After pulling a build that adds `POST /api/ibkr/gateway-mode`, **restart the
Nova API** (stale uvicorn returns 404; the capsule then says “Restart Nova API”).
Smoke: open `http://127.0.0.1:8000/openapi.json` and confirm `/api/ibkr/gateway-mode`.

## Daily auto-start (boot / 6am)

To start Gateway (via IBC) + Nova API + UI automatically:

```powershell
# Register: daily 6:00 AM local + every Windows logon (default)
.\scripts\Install-NovaDailyTask.ps1

# Or only 6am / only logon:
.\scripts\Install-NovaDailyTask.ps1 -Trigger Daily -AtTime 06:00
.\scripts\Install-NovaDailyTask.ps1 -Trigger AtLogon

# Run once now (no scheduler):
.\scripts\Start-NovaDaily.ps1
# or double-click: Start Nova Daily.bat

# Remove:
.\scripts\Install-NovaDailyTask.ps1 -Unregister
```

`Start-NovaDaily.ps1` is idempotent (skips healthy API/UI/Gateway). Log:
`backend/logs/daily-start.log`. IBKR Mobile 2FA may still require your phone.

If the PC is asleep at 6am, either enable wake timers in Windows power
settings or rely on the AtLogon trigger when you unlock.

## Related

- `scripts/start_gateway_ibc.ps1.example` — template launcher (no secrets)
- `scripts/Start-NovaDaily.ps1` / `Install-NovaDailyTask.ps1` — morning auto-start
- `scripts/smoke_check.ps1` — post-login API smoke
- `IBKR_GATEWAY_MODE` / `IBKR_LIVE_PORT` / `IBKR_PAPER_PORT` in `.env`
- `.cursor/rules/ibkr-gateway-login-warning.mdc` — loud-warn vs bidirectional self-heal
