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

From PowerShell (after copying the example script):

```powershell
# One-time: copy example → local launcher
Copy-Item scripts\start_gateway_ibc.ps1.example $env:USERPROFILE\.nova\ibc\start_gateway.ps1

# Edit paths inside that local script, then:
& "$env:USERPROFILE\.nova\ibc\start_gateway.ps1"
```

Or run IBC’s own `StartGateway.bat` pointing at your `config.ini`.

## Nova behavior after IBC

1. Wait until API port listens (`4001` live / `4002` paper).
2. Confirm `GET http://127.0.0.1:8000/api/ibkr/status` → `"connected": true`.
3. Run `.\scripts\smoke_check.ps1`.

**2FA:** IBKR Mobile may still require approval. Agents must warn loudly and must
not store passwords in the chat or the repo (see
`.cursor/rules/ibkr-gateway-login-warning.mdc`).

## Related

- `scripts/start_gateway_ibc.ps1.example` — template launcher (no secrets)
- `scripts/smoke_check.ps1` — post-login API smoke
- `IBKR_GATEWAY_MODE` / `IBKR_LIVE_PORT` / `IBKR_PAPER_PORT` in `.env`
