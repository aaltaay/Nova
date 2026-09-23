/**
 * What each bot order may risk (the small-cap sleeve) and the two locked loss
 * breakers. The sleeve is the session's `caps`; the breakers are product
 * thresholds with no PATCH field. Advise stays here, off by default -- it
 * reads, it never places.
 */
import {
  BOT_ADVISE_DEFAULT_CALL_CAP,
  BOT_ADVISE_DEFAULT_USD_CAP,
  BOT_BP_BUDGET_HARD_MAX_USD,
  BOT_BP_BUDGET_MIN_USD,
  BOT_BP_BUDGET_STEP_USD,
  BOT_BREAKER_HINT,
  BOT_DEFAULT_MAX_SHARES,
  BOT_HARD_BREAKER_USD,
  BOT_MAX_SHARES_CAP,
  BOT_SOFT_BREAKER_USD,
  BOT_WORKING_TTL_MAX_SEC,
  BOT_WORKING_TTL_MIN_SEC,
} from '../constants';
import { fmtUsd } from './botsPageFormat';
import type { BotSession } from './types';

type Patch = (body: Record<string, unknown>) => Promise<unknown>;

export function BotRiskCard({ session, patch }: { session: BotSession; patch: Patch }) {
  const caps = session.caps;
  return (
    <section className="bots-card" data-testid="bots-risk">
      <header className="bots-card__head">
        <h3>Risk sleeve</h3>
        <span className="bots-card__sub">per bot order</span>
      </header>
      <div className="bots-sleeve">
        <label>
          <span>Max shares</span>
          <input type="number" data-testid="bot-strategy-max-shares" min={BOT_DEFAULT_MAX_SHARES} max={BOT_MAX_SHARES_CAP}
            value={caps.max_shares} onChange={e => void patch({ caps: { max_shares: Number(e.target.value) } })} />
          <small>1 to {BOT_MAX_SHARES_CAP}</small>
        </label>
        <label>
          <span>Buying-power budget</span>
          <input type="number" data-testid="bot-strategy-bp-budget" min={BOT_BP_BUDGET_MIN_USD} max={BOT_BP_BUDGET_HARD_MAX_USD}
            step={BOT_BP_BUDGET_STEP_USD} value={caps.bp_budget_usd}
            onChange={e => void patch({ caps: { bp_budget_usd: Number(e.target.value) } })} />
          <small>hard max ${BOT_BP_BUDGET_HARD_MAX_USD}</small>
        </label>
        <label>
          <span>Working order TTL (s)</span>
          <input type="number" data-testid="bot-strategy-ttl" min={BOT_WORKING_TTL_MIN_SEC} max={BOT_WORKING_TTL_MAX_SEC}
            value={caps.working_ttl_sec} onChange={e => void patch({ caps: { working_ttl_sec: Number(e.target.value) } })} />
          <small>{BOT_WORKING_TTL_MIN_SEC} to {BOT_WORKING_TTL_MAX_SEC} s, then Nova cancels</small>
        </label>
        <label className="bots-sleeve__check">
          <input type="checkbox" data-testid="bot-strategy-eh" checked={caps.extended_hours}
            onChange={e => void patch({ caps: { extended_hours: e.target.checked } })} />
          <span>Extended hours</span>
          <small>needed for pre-market setups (the window opens 07:00)</small>
        </label>
      </div>

      <div className="bots-breakers" data-testid="bot-strategy-breakers" title={BOT_BREAKER_HINT}>
        <div className="bots-breakers__head"><b>Loss breakers</b><span>locked</span></div>
        <div className="bots-breakers__row">
          <span><b>{fmtUsd(BOT_HARD_BREAKER_USD)}</b> all-stop · day lock</span>
          <span><b>{fmtUsd(BOT_SOFT_BREAKER_USD)}</b> bot trip</span>
        </div>
        <p className="bots-muted">{BOT_BREAKER_HINT}</p>
      </div>

      <details className="bots-advise">
        <summary>Advise (never places)</summary>
        <label className="bots-sleeve__check">
          <input type="checkbox" data-testid="bot-strategy-advise-enabled" checked={session.advise.enabled}
            onChange={e => void patch({ advise: { enabled: e.target.checked } })} />
          <span>Enable Advise for the bot</span>
        </label>
        <div className="bots-sleeve">
          <label>
            <span>USD cap</span>
            <input type="number" data-testid="bot-strategy-advise-usd" min={0} step={0.25} value={session.advise.usd_cap}
              onChange={e => void patch({ advise: { usd_cap: Number(e.target.value) } })} />
          </label>
          <label>
            <span>Call cap</span>
            <input type="number" data-testid="bot-strategy-advise-calls" min={0} value={session.advise.call_cap}
              onChange={e => void patch({ advise: { call_cap: Number(e.target.value) } })} />
          </label>
        </div>
        <p className="bots-muted">
          Spent ${session.advise.usd_spent.toFixed(2)} / {session.advise.calls_used} calls
          {` (defaults $${BOT_ADVISE_DEFAULT_USD_CAP} / ${BOT_ADVISE_DEFAULT_CALL_CAP} calls)`}
        </p>
      </details>
    </section>
  );
}
