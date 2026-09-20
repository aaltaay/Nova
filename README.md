# Nova

Local-first Interactive Brokers trading workstation. Scanner, charts, Trader View, and gated orders run on your machine. The public site is marketing only. This repository is the source.

[![CI](https://github.com/aaltaay/Nova/actions/workflows/deploy.yml/badge.svg)](https://github.com/aaltaay/Nova/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-0f172a.svg)](LICENSE)

**Site:** [nova.altaystudio.com](https://nova.altaystudio.com) · **Releases:** [GitHub Releases](https://github.com/aaltaay/Nova/releases)

## What it is

Nova is a single-operator desk for US equities:

- Persistent IBKR scanner rosters (Gappers, Gainers, Afterhours, Large Cap)
- HOD Momo alerts from names already on the desk
- Store-first IBKR charts
- Trader View with Level 2, Time & Sales, and a ticket (depth-plan cap)
- News: on-roster catalysts plus an AI-in-trading desk
- Optional paper or live orders through one execution command

It is not a hosted brokerage, not a cloud scanner, and not an unattended trading bot.

## Safety

| Gate | Default |
|------|---------|
| Market data | Interactive Brokers only |
| Alpaca | News and listing metadata only |
| Orders | Off until `IBKR_ENABLED` and `IBKR_ORDERS_ENABLED` |
| Live money | Also requires `IBKR_LIVE_TRADING_CONFIRMED` |
| Short entry | Off until `IBKR_SHORT_ENABLED` plus an explicit `short_entry` on the command |
| `auto_live` | Rejected in code. Do not enable it. |

The API binds to `127.0.0.1:8000`. Do not expose it to the internet.

## Requirements

- Windows for the supported desktop and `Run Nova.bat` path
- Python 3.13 and Node.js 20
- [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) logged in (live port 4001, paper 4002)
- Alpaca keys only if you want news and listing flags
- Optional: Finnhub (Earnings calendar), Discord/Telegram (alerts)

## Quick start (Windows)

1. Clone this repository.
2. Copy `.env.example` to `.env`. Leave secrets out of git.
3. In `frontend/`, run `npm install` once.
4. Double-click `Run Nova.bat`.

Expected local endpoints:

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- UI: [http://localhost:5173](http://localhost:5173)

Desktop (Electron + local API sidecar):

```bat
cd frontend
npm install
npm run electron:dev
```

Installer and portable EXE:

```bat
cd frontend
npm run electron:pack
```

Output: `frontend/release/Nova-Setup-vNNN.exe` and `frontend/release/Nova-Portable-vNNN.exe`. The packaged app stores keys and cache under `%APPDATA%\Nova\`.

## Releases

Public revision is **`vNNN`**: `v` plus the git commit count, at least three digits. `VERSION` is the source of truth. `frontend/package.json` keeps `0.1.N` because electron-builder requires semver.

A green push to `master` creates tag `vNNN` and a GitHub Release with both EXEs. The automatic Source code zip is not the app. Pull requests upload the same EXEs as workflow artifacts.

Install git hooks once: `powershell -File tools/install_git_hooks.ps1`.

## Configuration

All secrets go in `.env`. The tracked file is `.env.example` (empty placeholders only).

| Variable | Role |
|----------|------|
| `NOVA_DISCOVERY_PROVIDER` | Must stay `ibkr` |
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | Alpaca news and listing metadata |
| `IBKR_ENABLED` / `IBKR_ORDERS_ENABLED` | Connect and spend |
| `IBKR_LIVE_TRADING_CONFIRMED` | Live money |
| `IBKR_SHORT_ENABLED` | Short entry (Phase K) |
| `NOVA_API_KEY` | Required for `POST /api/config` even on loopback; required for all mutating `/api/*` off loopback |
| `FINNHUB_API_KEY` | Earnings calendar |

Gateway default is live (4001). Paper (4002) is the fallback when live is dark. Port 4001 listening is not proof of a live account.

## Architecture

| Layer | Location |
|-------|----------|
| Constitution | [AGENTS.md](AGENTS.md) |
| ADRs | [architecture/decisions/](architecture/decisions/) |
| Backend | FastAPI modules under `backend/` (`main.py` is the app factory only) |
| Frontend | React + Vite under `frontend/src/` (`App.tsx` is the shell only) |
| Execution | `execution.service.execute` -- sole broker mutation entry (ADR 007) |
| Feed | IBKR scanner, L1, charts, depth, tape. See `.cursor/rules/single-market-data-feed.mdc` |

## Development

```text
# API
cd backend && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

# UI
cd frontend && npm run dev

# Tests
pytest backend/ -q
cd frontend && npm test -- --run && npm run build
python3 tools/doc_invariants.py
```

## Deploy

- **Desk:** local only -- `Run Nova.bat`, Desktop sidecar, or uvicorn on loopback. There is no cloud API host.
- **Marketing:** `nova.altaystudio.com` serves `site/` (Vercel Root Directory = `site`). It does not run the scanner. The public AI-in-trading product is [`/news`](https://nova.altaystudio.com/news) (50+ ranked rows). The homepage is a tease that links there, not a 6-card digest.
- **App UI:** local Vite or the Desktop installer. Do not host the trading SPA on the public domain.

The older `Nova-public` repository is a private archive. It is not the source home.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests must be ready (not draft) and include verification evidence. GitHub Actions merges when gating CI is green.

## Security

See [SECURITY.md](SECURITY.md). Report vulnerabilities through GitHub Security Advisories. Do not commit `.env` files or tokens.

## License

[MIT](LICENSE). Copyright (c) 2026 Ahmi Altaay.

Not investment advice. Not a hosted brokerage. You are responsible for IBKR permissions, keys, and every order.
