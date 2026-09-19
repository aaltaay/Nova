# nova-brain (Windows worker)

Standing OpenRouter decision client for Nova's brain socket. It talks to
localhost only. It never raises Bot Autonomy and never Places except through
allowlisted `NovaActionKind` on the existing bot action door.

Advise never places. Grok Trader / Eyes chats stay arm / watch only.

## How to run on Windows

1. Nova API must already be up (`Run Nova.bat` or Desktop). Brain is started
   by that bat as **Nova -- Brain**, and by the Desktop sidecar.
2. Standalone:

```text
cd backend
py -3 -m nova_brain
```

Or from repo root:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-NovaBrain.ps1
```

Skip the sidecar / bat spawn with `NOVA_BRAIN_DISABLED=1`.

Needs `NOVA_API_KEY` (same key as Desktop). Default base is
`http://127.0.0.1:8000`. Exclusive claim id is `nova-brain`.

The process loads repo-root `.env` via `paths.env_file_path()` (same file
Advise uses).

## Env vars

| Var | Role |
|---|---|
| `NOVA_API_KEY` | Required. Mutating bot routes. Process exits 2 if missing. |
| `NOVA_API_BASE` | Optional. Default `http://127.0.0.1:8000`. |
| `NOVA_BRAIN_SESSION_ID` | Optional. Default `nova-brain`. |
| `OPENROUTER_API_KEY` | Decision key. **Same key Advise already uses.** |
| `NOVA_LLM_API_KEY` | Optional override if you do not want to share Advise's key. |
| `NOVA_LLM_BASE_URL` | Optional. Default `https://openrouter.ai/api/v1`. |
| `NOVA_LLM_MODEL` / `NOVA_BRAIN_MODEL` | Optional. Default `openai/gpt-4o-mini` (cheap / fast v1). |

Do not hard-require Claude Sonnet for the loop. Advise may still use Sonnet
on its own rail. Missing OpenRouter key: **loud log, no place**. Other packs
(`halt-luld`, `quote-spike`, `volume`) still run.

No paid OpenRouter calls in CI. Tests stub HTTP.

## What each tick reads

1. `GET /api/health` -- no Nova heartbeat, no place (loud).
2. `GET /api/bot/session` -- level, armed / Activate, active pack, caps.
3. `GET /api/bot/watch` -- allowlist ∩ live Trader focus.
4. `GET /sensors/snapshot?symbol=` -- 18-sensor L2 Brain / Sensor Board
   compact context for each eligible focus name.

Then, when pack is `llm-decide` and the interval has elapsed, OpenRouter
gets a tight system + user JSON prompt.

## Decision schema

JSON only. Free-text is rejected (loud, no place).

```json
{
  "symbol": "ABCD",
  "side": "BUY",
  "kind": "buy_market",
  "qty_preset": "default",
  "reason": "short reason",
  "confidence": 0.7
}
```

`{"proposals":[<same>]}` is also accepted. `qty_preset` is `default` only
(session `max_shares`). Raw `qty` / `shares` are dropped. `HOLD` or empty
proposals means no action.

## L1 vs L2

| Desk | What nova-brain may do |
|---|---|
| Level 1 Eyes, or L2 with Activate off | `POST /api/bot/proposals` only |
| Level 2 + Active / armed + exclusive claim + fresh heartbeat | `POST /api/bot/action` for an allowlisted kind |

Nova still enforces breakers, BP budget, TTL, symbol allowlist ∩ focus,
and `NOVA_API_KEY`. The brain never PATCHes level and cannot arm.

## Fail-closed

- No `NOVA_API_KEY` -- process does not start.
- No `/api/health` -- tick skipped, no place.
- No OpenRouter key -- llm-decide idle, no place.
- Sensor snapshot error -- no place that tick.
- Bad / free-text JSON -- no place.

See also [bot-localhost-api.md](bot-localhost-api.md) and
[l2-brain-sensors.md](l2-brain-sensors.md).
