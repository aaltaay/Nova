# Advise rail (TradingAgents-style advisory panel)

Manual **Advise** icon at the bottom of the scanner left rail. It runs a
TradingAgents-style multi-agent debate and writes a book entry. A human
always Places in Nova. Advise never calls IBKR, flatten, close, or the
order SSOT.

Inspired by [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
(Apache-2.0). See `docs/licenses/tradingagents.md`.

## Configure locally

Required for a **new** debate (not for reopening a saved book row):

```text
OPENROUTER_API_KEY=sk-or-...
```

Put it in the repo-root `.env` (Desktop: the sidecar userData `.env`).
Never commit that file. Model is Claude Sonnet latest via OpenRouter
(`~anthropic/claude-sonnet-latest`).

Optional vendor keys (Yahoo still runs without them):

| Key | Role |
|-----|------|
| `FINNHUB_API_KEY` | Richer news for News/Sentiment analysts |
| `ALPHA_VANTAGE_API_KEY` | Optional; unused in MVP (Yahoo covers technicals) |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Optional social sentiment |

## How it spends

- Opening the panel and reading today's book is **free**.
- **Run** starts a subprocess worker (not the IBKR loop).
- Same symbol + session date + model + graph version + depth = book hit unless **Force refresh**.
- **Cancel** kills the worker process.
- Failed runs keep the partial transcript and show why + **Retry**.
- Max 3 workers; one active debate per symbol; extras queue.

## Manual smoke (owner Desktop / Vite)

1. Set `OPENROUTER_API_KEY` in `.env` and restart the API sidecar / uvicorn.
2. Vite: `cd frontend && npm run dev` -- or open Nova Desktop.
3. Click **Advise** at the bottom of the left rail.
4. Confirm the symbol prefills from the desk and the estimate shows before Run.
5. Run -- transcript streams; card shows stance / reasons / risks.
6. Reopen the same symbol the same session -- no second spend.
7. **Open order ticket** prefills only; Place stays human. **Jump to chart** opens Trader.
8. Start a run and **Cancel** -- worker dies; partial + reason remain.

CI cannot call OpenRouter. Pytest uses `ADVISE_STUB=1` for the worker graph.

## Non-goals (this MVP)

Multi-model picker is issue #147. No HOD auto-trigger, overnight batch,
per-analyst toggles, or IBKR L1 into the worker.
