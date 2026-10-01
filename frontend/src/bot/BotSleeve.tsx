/**
 * One venue's sleeve (ADR 042 E): every automatic Nova buy on that venue -- the bot
 * and Auto-entry -- is sized and capped by it, and your Stage sizes by its risk per
 * trade. Each row says what it binds on hover; each slider PATCHes
 * `{caps: {venue, field}}` once let go. The order kinds are the localhost bot API's,
 * read-only here.
 */
import {
  BOT_ACTION_KINDS,
  BOT_BP_BUDGET_HARD_MAX_USD,
  BOT_BP_BUDGET_MIN_USD,
  BOT_BP_BUDGET_STEP_USD,
  BOT_DEFAULT_MAX_SHARES,
  BOT_ENTRIES_PER_DAY_MAX,
  BOT_ENTRIES_PER_DAY_MIN,
  BOT_MAX_SHARES_CAP,
  BOT_RISK_DEFAULT_USD,
  BOT_RISK_MIN_USD,
  BOT_RISK_SLIDER_MAX_USD,
  BOT_WORKING_TTL_MAX_SEC,
  BOT_WORKING_TTL_MIN_SEC,
} from '../constantGroups/bot';
import {
  BOTS_BUDGET_LABEL,
  BOTS_BUDGET_TIP,
  BOTS_BUSY_WHY,
  BOTS_EH_HINT,
  BOTS_EH_LABEL,
  BOTS_EH_OFF,
  BOTS_EH_ON,
  BOTS_ENTRIES_LABEL,
  BOTS_ENTRIES_SLIDER_TIP,
  BOTS_KINDS_LABEL,
  BOTS_KINDS_TIP,
  BOTS_RISK_LABEL,
  BOTS_RISK_SLIDER_TIP,
  BOTS_SHARES_LABEL,
  BOTS_SHARES_TIP,
  BOTS_TTL_LABEL,
  BOTS_TTL_TIP,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import { BotSleeveSlider } from './BotSleeveSlider';
import type { BotCaps, BotCapsBounds } from './types';

type Patch = (body: Record<string, unknown>) => Promise<unknown>;

const usd = (v: number) => `$${v.toFixed(2)}`;
const whole = (v: number) => `$${v.toLocaleString('en-US')}`;

/** The backend's bounds, else the fallbacks this build ships (the backend checks again). */
function bounds(b: BotCapsBounds | undefined): BotCapsBounds {
  return {
    risk_usd: [b?.risk_usd?.[0] ?? BOT_RISK_MIN_USD, Math.min(b?.risk_usd?.[1] ?? BOT_RISK_SLIDER_MAX_USD, BOT_RISK_SLIDER_MAX_USD)],
    max_shares: b?.max_shares ?? [BOT_DEFAULT_MAX_SHARES, BOT_MAX_SHARES_CAP],
    bp_budget_usd: b?.bp_budget_usd ?? [BOT_BP_BUDGET_MIN_USD, BOT_BP_BUDGET_HARD_MAX_USD],
    working_ttl_sec: b?.working_ttl_sec ?? [BOT_WORKING_TTL_MIN_SEC, BOT_WORKING_TTL_MAX_SEC],
    entries_per_day: b?.entries_per_day ?? [BOT_ENTRIES_PER_DAY_MIN, BOT_ENTRIES_PER_DAY_MAX],
  };
}

interface Props {
  venue: string;
  caps: BotCaps;
  capsBounds?: BotCapsBounds;
  busy: boolean;
  patch: Patch;
}

export function BotSleeve({ venue, caps, capsBounds, busy, patch }: Props) {
  const b = bounds(capsBounds);
  const save = (field: string, value: unknown) => void patch({ caps: { venue, [field]: value } });
  const kinds = caps.api_kinds.length ? caps.api_kinds : [...BOT_ACTION_KINDS];
  const risk = caps.risk_usd ?? BOT_RISK_DEFAULT_USD;
  const entries = caps.entries_per_day ?? BOT_ENTRIES_PER_DAY_MIN;
  return (
    <div className="bots-sleeve" data-testid={`bots-sleeve-${venue}`}>
      <BotSleeveSlider label={BOTS_RISK_LABEL} tip={BOTS_RISK_SLIDER_TIP} testId="bot-strategy-risk" value={risk}
        min={b.risk_usd[0]} max={b.risk_usd[1]} step={1} format={whole}
        minLabel={whole(b.risk_usd[0])} maxLabel={whole(b.risk_usd[1])}
        onCommit={v => save('risk_usd', v)} />
      <BotSleeveSlider label={BOTS_ENTRIES_LABEL} tip={BOTS_ENTRIES_SLIDER_TIP} testId="bot-strategy-entries" value={entries}
        min={b.entries_per_day[0]} max={b.entries_per_day[1]} step={1} format={v => String(v)}
        minLabel={String(b.entries_per_day[0])} maxLabel={String(b.entries_per_day[1])}
        onCommit={v => save('entries_per_day', v)} />
      <BotSleeveSlider label={BOTS_SHARES_LABEL} tip={BOTS_SHARES_TIP} testId="bot-strategy-max-shares" value={caps.max_shares}
        min={b.max_shares[0]} max={b.max_shares[1]} step={1} format={v => String(v)}
        minLabel={String(b.max_shares[0])} maxLabel={String(b.max_shares[1])}
        onCommit={v => save('max_shares', v)} />
      <BotSleeveSlider label={BOTS_BUDGET_LABEL} tip={BOTS_BUDGET_TIP} testId="bot-strategy-bp-budget" value={caps.bp_budget_usd}
        min={b.bp_budget_usd[0]} max={b.bp_budget_usd[1]} step={BOT_BP_BUDGET_STEP_USD} format={usd}
        minLabel={usd(b.bp_budget_usd[0])} maxLabel={`hard max ${usd(b.bp_budget_usd[1])}`}
        onCommit={v => save('bp_budget_usd', v)} />
      <BotSleeveSlider label={BOTS_TTL_LABEL} tip={BOTS_TTL_TIP} testId="bot-strategy-ttl" value={caps.working_ttl_sec}
        min={b.working_ttl_sec[0]} max={b.working_ttl_sec[1]} step={1} format={v => `${v} s`}
        minLabel={`${b.working_ttl_sec[0]} s`} maxLabel={`${b.working_ttl_sec[1]} s`}
        onCommit={v => save('working_ttl_sec', v)} />
      <div className="bots-slider bots-slider--toggle">
        <span className="bots-slider__head"><span>{BOTS_EH_LABEL}</span><b>{caps.extended_hours ? BOTS_EH_ON : BOTS_EH_OFF}</b></span>
        <label className="bots-switch">
          <input type="checkbox" role="switch" data-testid="bot-strategy-eh" checked={caps.extended_hours}
            aria-checked={caps.extended_hours} disabled={busy} data-why={busy ? BOTS_BUSY_WHY : undefined}
            onChange={e => save('extended_hours', e.target.checked)} />
          <span className="bots-switch__track" aria-hidden="true" />
          <span className="bots-muted">{BOTS_EH_HINT}</span>
        </label>
      </div>
      <div className="bots-sleeve__kinds" data-testid="bots-sleeve-kinds">
        <span className="bots-slider__head" {...tipProps(BOTS_KINDS_TIP, BOTS_KINDS_LABEL)}><span>{BOTS_KINDS_LABEL}</span></span>
        <span className="bots-muted">{kinds.join(' · ')}</span>
      </div>
    </div>
  );
}
