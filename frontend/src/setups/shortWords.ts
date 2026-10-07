/**
 * A short setup's words on a board row (ADR 049): its trigger, buy stop and cover, the context it grew from and the
 * distance to its trigger, said the short way. `setupWords.ts` asks here for a short row; a long row never reaches
 * this. Pure: rows in, words out.
 */
import { isShortSetup, SHORT_TAPE_VERDICT_TIPS } from '../constantGroups/short_setups';
import { fmtCents, fmtPx } from './setupsFormat';
import type { SetupLevels, SetupRow } from './types';

/** The row's side: the wire's word, else its setup's. */
export function isShortRow(row: { side?: string | null; setup_type?: string | null } | null | undefined): boolean {
  if (row?.side === 'short') return true;
  if (row?.side === 'long') return false;
  return isShortSetup(row?.setup_type);
}

const TRIGGER: Record<string, string> = {
  backside_lower_high: 'the last bounce candle\'s low',
  bear_flag: 'the last flag candle\'s low',
  failed_breakout: 'the low of the candle that closed back under the flat top',
  lost_vwap: 'the low of the retest that failed at VWAP',
  ssr_bounce: 'the resting short, 1c under the level the bounce runs into',
};

const STOP: Record<string, string> = {
  backside_lower_high: '1c over the bounce',
  bear_flag: '1c over the flag',
  failed_breakout: '1c over the poke',
  lost_vwap: '1c over the retest, or over VWAP when VWAP is higher',
  ssr_bounce: '2% over the entry, at least 5c',
};

/** The short whose entry rests over the price (ADR 049: the SSR bounce); every other short breaks down into it. */
function rests(row: SetupRow): boolean {
  return row.setup_type === 'ssr_bounce';
}

function pct(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '';
  const v = Math.abs(x) * 100;
  return `−${v.toFixed(v >= 10 ? 0 : 1)}%`;
}

/** The context the short grew from, in one line ("Fade −9.2% off the 6.01 high of day, to 5.46."). */
export function shortContextLine(row: SetupRow): string {
  const leg = row.leg;
  if (!leg) return '';
  switch (row.setup_type) {
    case 'backside_lower_high':
      return `Fade ${pct(leg.pct)} off the ${fmtPx(leg.high)} high of day, to ${fmtPx(leg.low)}.`;
    case 'bear_flag': {
      const n = leg.bars ? `${leg.bars} red candle${leg.bars === 1 ? '' : 's'}, ` : '';
      return `Pole: ${n}${pct(leg.pct)} to ${fmtPx(leg.low)} (from ${fmtPx(leg.high)}).`;
    }
    case 'failed_breakout':
      return `Flat top ${fmtPx(leg.low)} · poked to ${fmtPx(leg.high)}, then closed back under it.`;
    case 'lost_vwap':
      return `Lost VWAP ${fmtPx(leg.high)} · the loss candle's low ${fmtPx(leg.low)}.`;
    case 'ssr_bounce': {
      const level = row.setup?.detail?.level;
      const under = typeof level === 'number' ? ` · rests under the ${fmtPx(level)} ${row.setup?.detail?.level_kind ?? 'level'}` : '';
      return `Dropped ${pct(leg.pct)} to a low of day ${fmtPx(leg.low)} (from ${fmtPx(leg.high)}) under SSR${under}.`;
    }
    default:
      return '';
  }
}

/** A short's state chip where it says more than the label: its fade, its pole, its flag. */
export function shortStateText(row: SetupRow, base: string): string | null {
  const s = row.setup;
  if (row.state === 'leg') {
    if (row.setup_type === 'backside_lower_high') return `${base} ${pct(row.leg?.pct)}`.trim();
    if (row.setup_type === 'bear_flag') return row.leg?.bars ? `${base} · ${row.leg.bars} red` : base;
    return base;
  }
  if (row.state === 'armed') {
    if (row.setup_type === 'bear_flag') return `${base} · ${s?.detail?.flag_bars ?? s?.pullback_bars ?? '?'} bars`;
    if (row.setup_type === 'backside_lower_high') return `${base} · ${s?.pullback_bars ?? '?'} bars`;
    if (row.setup_type === 'ssr_bounce' && typeof s?.detail?.level === 'number') return `${base} under ${fmtPx(s.detail.level)}`;
    return base;
  }
  return null;
}

/** The trigger cell's lines for a short: the trigger, the entry, the buy stop and the cover. */
export function shortTriggerLines(row: SetupRow, s: SetupLevels): string[] {
  const type = row.setup_type ?? '';
  const lines = rests(row)
    ? [`Trigger ${fmtPx(s.trigger)}: ${TRIGGER[type]}. A buyer lifting the offer to it fills it, above the bid as SSR `
      + 'requires.', `Entry ${fmtPx(s.entry)}: the resting short's limit.`]
    : [`Trigger ${fmtPx(s.trigger)}: ${TRIGGER[type] ?? 'the level'}. Trading under it starts the short.`,
      `Entry ${fmtPx(s.entry)} (the trigger −1c, the short's limit).`];
  lines.push(`Buy stop ${fmtPx(s.stop)}: ${STOP[type] ?? 'over the pattern'}. Risk ${fmtCents(s.risk)} a share.`);
  lines.push(`Cover 1 ${fmtPx(s.target1)}: R x the risk under the entry. Half is covered there and the buy stop moves `
    + 'to the entry.');
  return lines;
}

/** How far a short is from its trigger: over it for a breakdown, under the resting short for the SSR bounce. */
export function shortToGoTip(row: SetupRow, cents: number, s: SetupLevels): string {
  const last = `(last ${fmtPx(row.last_price)})`;
  if (cents <= 0) return `At the ${fmtPx(s.trigger)} trigger now ${last}.`;
  if (rests(row)) return `${cents}¢ under the resting short at ${fmtPx(s.trigger)} ${last}. A buyer lifting it fills it.`;
  return `${cents}¢ over the ${fmtPx(s.trigger)} trigger ${last}. Within a few cents it reads Near, and the tape is read `
    + 'there.';
}

/** A short's tape verdict hover head (the reasons and numbers follow). */
export function shortTapeTip(verdict: string): string | null {
  return SHORT_TAPE_VERDICT_TIPS[verdict] ?? null;
}

/** "the cover first (+1.8R)" / "the buy stop first (−1.0R)" for a scored short. */
export function shortOutcome(outcome: string | null, r: string | null): string | null {
  if (outcome === 'target_first') return `the cover first${r ? ` (${r})` : ''}`;
  if (outcome === 'stop_first') return `the buy stop first${r ? ` (${r})` : ''}`;
  return null;
}
