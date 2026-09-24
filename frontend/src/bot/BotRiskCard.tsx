/**
 * What each bot order may risk (the small-cap sleeve) and the two locked loss
 * breakers (approved mockup v4). The sleeve is the session's `caps`, PATCHed
 * when a slider is let go; the breakers are product thresholds with no PATCH
 * field. Advise's budget stays here, folded away -- it reads, it never places.
 */
import {
  BOT_BP_BUDGET_HARD_MAX_USD,
  BOT_BP_BUDGET_MIN_USD,
  BOT_BP_BUDGET_STEP_USD,
  BOT_DEFAULT_MAX_SHARES,
  BOT_MAX_SHARES_CAP,
  BOT_WORKING_TTL_MAX_SEC,
  BOT_WORKING_TTL_MIN_SEC,
} from '../constants';
import {
  BOTS_ADVISE_TITLE,
  BOTS_BUSY_WHY,
  BOTS_EH_HINT,
  BOTS_EH_LABEL,
  BOTS_EH_OFF,
  BOTS_EH_ON,
  BOTS_RISK_SUB,
  BOTS_RISK_TITLE,
} from '../constantGroups/bots_page';
import { BotBreakerBar } from './BotBreakerBar';
import { BotSleeveSlider } from './BotSleeveSlider';
import type { BotSession } from './types';

type Patch = (body: Record<string, unknown>) => Promise<unknown>;

const usd = (v: number) => `$${v.toFixed(2)}`;

export function BotRiskCard({ session, patch, busy, dayPnl }: {
  session: BotSession;
  patch: Patch;
  busy: boolean;
  dayPnl: number | null;
}) {
  const caps = session.caps;
  return (
    <section className="bots-card" data-testid="bots-risk">
      <header className="bots-card__head">
        <h3>{BOTS_RISK_TITLE}</h3>
        <span className="bots-card__sub">{BOTS_RISK_SUB}</span>
      </header>
      <div className="bots-sleeve">
        <BotSleeveSlider label="Max shares" testId="bot-strategy-max-shares" value={caps.max_shares}
          min={BOT_DEFAULT_MAX_SHARES} max={BOT_MAX_SHARES_CAP} step={1} format={v => String(v)}
          minLabel={String(BOT_DEFAULT_MAX_SHARES)} maxLabel={String(BOT_MAX_SHARES_CAP)}
          onCommit={v => void patch({ caps: { max_shares: v } })} />
        <BotSleeveSlider label="Buying-power budget" testId="bot-strategy-bp-budget" value={caps.bp_budget_usd}
          min={BOT_BP_BUDGET_MIN_USD} max={BOT_BP_BUDGET_HARD_MAX_USD} step={BOT_BP_BUDGET_STEP_USD} format={usd}
          minLabel={usd(BOT_BP_BUDGET_MIN_USD)} maxLabel={`hard max $${BOT_BP_BUDGET_HARD_MAX_USD}`}
          onCommit={v => void patch({ caps: { bp_budget_usd: v } })} />
        <BotSleeveSlider label="Working order TTL" testId="bot-strategy-ttl" value={caps.working_ttl_sec}
          min={BOT_WORKING_TTL_MIN_SEC} max={BOT_WORKING_TTL_MAX_SEC} step={1} format={v => `${v} s`}
          minLabel={`${BOT_WORKING_TTL_MIN_SEC} s`} maxLabel={`${BOT_WORKING_TTL_MAX_SEC} s`}
          onCommit={v => void patch({ caps: { working_ttl_sec: v } })} />
        <div className="bots-slider bots-slider--toggle">
          <span className="bots-slider__head"><span>{BOTS_EH_LABEL}</span><b>{caps.extended_hours ? BOTS_EH_ON : BOTS_EH_OFF}</b></span>
          <label className="bots-switch">
            <input type="checkbox" role="switch" data-testid="bot-strategy-eh" checked={caps.extended_hours}
              aria-checked={caps.extended_hours} disabled={busy} data-why={busy ? BOTS_BUSY_WHY : undefined}
              onChange={e => void patch({ caps: { extended_hours: e.target.checked } })} />
            <span className="bots-switch__track" aria-hidden="true" />
            <span className="bots-muted">{BOTS_EH_HINT}</span>
          </label>
        </div>
      </div>

      <BotBreakerBar dayPnl={dayPnl} />

      <details className="bots-advise">
        <summary>{BOTS_ADVISE_TITLE}</summary>
        <label className="bots-switch">
          <input type="checkbox" role="switch" data-testid="bot-strategy-advise-enabled" checked={session.advise.enabled}
            aria-checked={session.advise.enabled} onChange={e => void patch({ advise: { enabled: e.target.checked } })} />
          <span className="bots-switch__track" aria-hidden="true" />
          <span>Enable Advise for the bot</span>
        </label>
        <div className="bots-advise__caps">
          <label>
            <span>USD cap</span>
            <input type="number" data-testid="bot-strategy-advise-usd" min={0} step={0.25} defaultValue={session.advise.usd_cap}
              key={`usd-${session.advise.usd_cap}`}
              onBlur={e => { const v = Number(e.target.value); if (Number.isFinite(v) && v >= 0 && v !== session.advise.usd_cap) void patch({ advise: { usd_cap: v } }); }} />
          </label>
          <label>
            <span>Call cap</span>
            <input type="number" data-testid="bot-strategy-advise-calls" min={0} step={1} defaultValue={session.advise.call_cap}
              key={`calls-${session.advise.call_cap}`}
              onBlur={e => { const v = Number(e.target.value); if (Number.isInteger(v) && v >= 0 && v !== session.advise.call_cap) void patch({ advise: { call_cap: v } }); }} />
          </label>
          <span className="bots-muted">Spent ${session.advise.usd_spent.toFixed(2)} · {session.advise.calls_used} calls</span>
        </div>
      </details>
    </section>
  );
}
